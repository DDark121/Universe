from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from tg_service.backend import BackendClient, BackendClientError
from tg_service.config import TGServiceSettings, get_settings
from tg_service.logging import configure_logging, get_logger
from tg_service.messages import render_event_message
from tg_service.middleware import RequestContextMiddleware
from tg_service.security import (
    InitDataValidationError,
    TelegramWebAppUser,
    validate_init_data,
    verify_backend_token,
)

logger = get_logger(__name__)


class SendMessageRequest(BaseModel):
    telegram_id: int
    event_type: str
    payload: dict = {}
    idempotency_key: str


class WebAppBootstrapRequest(BaseModel):
    init_data: str


class WebAppBindingRequest(BaseModel):
    init_data: str
    full_name: str | None = None
    group_code: str | None = None
    note: str | None = None


@dataclass(slots=True)
class AppServices:
    settings: TGServiceSettings
    backend: BackendClient
    bot: BotServiceProtocol


class BotServiceProtocol:
    async def start(self) -> None:  # pragma: no cover - protocol signature
        raise NotImplementedError 

    async def stop(self) -> None:  # pragma: no cover - protocol signature
        raise NotImplementedError

    async def send_event_message(self, telegram_id: int, event_type: str, payload: dict) -> dict:
        raise NotImplementedError


class BotService(BotServiceProtocol):
    STUDENT_BUTTONS = {
        "Расписание": "student_schedule",
        "Сводка": "student_summary",
        "Рейтинг": "student_rating",
        "Предупреждения": "student_warnings",
        "Причина отсутствия": "student_reason_help",
        "FAQ": "assistant_faq",
    }
    TEACHER_BUTTONS = {
        "Мои занятия": "teacher_lessons",
        "QR": "teacher_qr_help",
        "Посещаемость": "teacher_attendance_help",
        "Причины": "teacher_reasons",
        "Рассылка": "teacher_broadcast_help",
        "FAQ": "assistant_faq",
    }

    def __init__(self, settings: TGServiceSettings, backend: BackendClient):
        self.settings = settings
        self.backend = backend
        self._bot: Any | None = None
        self._dispatcher: Any | None = None

    def _preview_text(self, value: str | None, *, limit: int = 120) -> str | None:
        if not value:
            return None
        return value[:limit] if len(value) <= limit else f"{value[:limit]}..."

    def _message_context(self, message: Any) -> dict[str, Any]:
        from_user = getattr(message, "from_user", None)
        chat = getattr(message, "chat", None)
        return {
            "telegram_id": getattr(from_user, "id", None),
            "chat_id": getattr(chat, "id", None),
            "chat_type": getattr(chat, "type", None),
            "message_id": getattr(message, "message_id", None),
        }

    async def _ensure_runtime(self) -> tuple[Any, Any]:
        if not self.settings.tg_bot_token:
            raise RuntimeError("TG_BOT_TOKEN is not configured")

        from aiogram import Bot, Dispatcher, F, Router
        from aiogram.filters import Command, CommandObject, CommandStart

        if self._bot is None:
            self._bot = Bot(token=self.settings.tg_bot_token)

        if self._dispatcher is None:
            dispatcher = Dispatcher()
            router = Router()

            @router.message(CommandStart())
            async def handle_start(message, command: CommandObject | None = None):
                await self._handle_start(message, command.args if command else None)

            @router.message(Command("schedule"))
            async def handle_schedule_command(message):
                await self._handle_student_schedule(message)

            @router.message(Command("summary"))
            async def handle_summary_command(message):
                await self._handle_student_summary(message)

            @router.message(Command("rating"))
            async def handle_rating_command(message):
                await self._handle_student_rating(message)

            @router.message(Command("warnings"))
            async def handle_warnings_command(message):
                await self._handle_student_warnings(message)

            @router.message(Command("faq"))
            async def handle_faq_command(message, command: CommandObject | None = None):
                await self._handle_assistant(message, command.args if command else "FAQ")

            @router.message(Command("reason"))
            async def handle_reason_command(message, command: CommandObject | None = None):
                await self._handle_reason_command(message, command.args if command else None)

            @router.message(Command("predeclare"))
            async def handle_predeclare_command(message, command: CommandObject | None = None):
                await self._handle_reason_command(message, command.args if command else None, is_predeclared=True)

            @router.message(Command("lessons"))
            async def handle_lessons_command(message):
                await self._handle_teacher_lessons(message)

            @router.message(Command("qr"))
            async def handle_qr_command(message, command: CommandObject | None = None):
                await self._handle_teacher_qr(message, command.args if command else None)

            @router.message(Command("attendance"))
            async def handle_attendance_command(message, command: CommandObject | None = None):
                await self._handle_teacher_attendance(message, command.args if command else None)

            @router.message(Command("reasons"))
            async def handle_reasons_command(message):
                await self._handle_teacher_reasons(message)

            @router.message(Command("moderate"))
            async def handle_moderate_command(message, command: CommandObject | None = None):
                await self._handle_teacher_moderation(message, command.args if command else None)

            @router.message(Command("broadcast"))
            async def handle_broadcast_command(message, command: CommandObject | None = None):
                await self._handle_teacher_broadcast(message, command.args if command else None)

            @router.message(Command("activity"))
            async def handle_activity_command(message, command: CommandObject | None = None):
                await self._handle_teacher_activity(message, command.args if command else None)

            @router.message(F.chat.type == "private", F.text)
            async def handle_private_text(message):
                await self._handle_private_text(message)

            dispatcher.include_router(router)
            self._dispatcher = dispatcher

        return self._bot, self._dispatcher

    def _safe_parse_datetime(self, value: Any) -> datetime | None:
        if not value or not isinstance(value, str):
            return None
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None

    def _format_window(self, starts_at: Any, ends_at: Any) -> str:
        start_dt = self._safe_parse_datetime(starts_at)
        end_dt = self._safe_parse_datetime(ends_at)
        if not start_dt:
            return "время не указано"
        start_label = start_dt.strftime("%d.%m %H:%M")
        if not end_dt:
            return start_label
        return f"{start_label} - {end_dt.strftime('%H:%M')}"

    def _short_id(self, value: Any) -> str:
        return str(value).split("-")[0]

    async def _bootstrap(self, telegram_id: int) -> dict:
        try:
            return await self.backend.get_bootstrap(telegram_id)
        except BackendClientError as exc:
            if exc.status_code == status.HTTP_404_NOT_FOUND:
                return {"status": "link_required"}
            raise

    def _role_set(self, bootstrap: dict) -> set[str]:
        user = bootstrap.get("user") or {}
        roles = user.get("roles") or []
        return {str(role) for role in roles}

    async def _build_private_keyboard(self, bootstrap: dict | None = None) -> Any:
        from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, WebAppInfo

        if not bootstrap:
            buttons = [
                [KeyboardButton(text="FAQ")],
                [KeyboardButton(text="Открыть приложение", web_app=WebAppInfo(url=self.settings.student_app_url))],
            ]
            return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

        roles = self._role_set(bootstrap)
        if "teacher" in roles:
            rows = [
                [KeyboardButton(text="Мои занятия"), KeyboardButton(text="QR")],
                [KeyboardButton(text="Посещаемость"), KeyboardButton(text="Причины")],
                [KeyboardButton(text="Рассылка"), KeyboardButton(text="FAQ")],
            ]
        elif "student" in roles:
            rows = [
                [KeyboardButton(text="Расписание"), KeyboardButton(text="Сводка")],
                [KeyboardButton(text="Рейтинг"), KeyboardButton(text="Предупреждения")],
                [KeyboardButton(text="Причина отсутствия"), KeyboardButton(text="FAQ")],
            ]
        else:
            rows = [[KeyboardButton(text="FAQ")]]
        rows.append([KeyboardButton(text="Открыть приложение", web_app=WebAppInfo(url=self.settings.student_app_url))])
        return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

    async def _send_private_message(
        self,
        chat_id: int,
        text: str,
        *,
        bootstrap: dict | None = None,
    ) -> None:
        bot, _dispatcher = await self._ensure_runtime()
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=await self._build_private_keyboard(bootstrap),
                disable_web_page_preview=True,
            )
        except Exception:
            logger.exception(
                "telegram_send_message_failed",
                chat_id=chat_id,
                bootstrap_status=(bootstrap or {}).get("status"),
            )
            raise

    async def _send_welcome(self, chat_id: int, telegram_id: int, first_name: str | None = None) -> None:
        bootstrap = await self._bootstrap(telegram_id)
        status_value = str(bootstrap.get("status") or "link_required")
        roles = self._role_set(bootstrap)
        greeting = first_name or (bootstrap.get("user") or {}).get("full_name") or "пользователь"
        if status_value == "linked" and "teacher" in roles:
            text = (
                f"Здравствуйте, {greeting}.\n\n"
                "Бот готов для преподавателя. Доступны список занятий, генерация QR, просмотр посещаемости, "
                "модерация причин и рассылки."
            )
        elif status_value == "linked" and "student" in roles:
            text = (
                f"Здравствуйте, {greeting}.\n\n"
                "Бот готов для студента. Доступны расписание, сводка по посещаемости, рейтинг, предупреждения, "
                "причины отсутствия и FAQ."
            )
        elif status_value == "pending":
            text = (
                f"Здравствуйте, {greeting}.\n\n"
                "Заявка на привязку уже отправлена. Пока можно открыть mini app и задать вопрос FAQ-помощнику."
            )
        elif status_value == "rejected":
            text = (
                f"Здравствуйте, {greeting}.\n\n"
                "Последняя заявка на привязку была отклонена. Откройте mini app и отправьте новую заявку "
                "с корректными данными."
            )
        else:
            text = (
                f"Здравствуйте, {greeting}.\n\n"
                "Сначала привяжите Telegram к учетной записи через mini app. После этого бот сможет помочь "
                "с расписанием, посещаемостью и FAQ."
            )
        await self._send_private_message(chat_id, text, bootstrap=bootstrap)

    async def _handle_qr_start(self, chat_id: int, telegram_id: int, qr_token: str) -> None:
        logger.info(
            "telegram_qr_start_received",
            chat_id=chat_id,
            telegram_id=telegram_id,
        )
        try:
            result = await self.backend.mark_attendance(telegram_id=telegram_id, qr_token=qr_token)
            status_text = result.get("status", "marked")
            bootstrap = await self._bootstrap(telegram_id)
            await self._send_private_message(
                chat_id,
                f"Посещаемость зафиксирована: {status_text}.",
                bootstrap=bootstrap,
            )
        except BackendClientError as exc:
            bootstrap = await self._bootstrap(telegram_id)
            await self._send_private_message(
                chat_id,
                f"Не удалось отметить посещаемость: {exc.detail}",
                bootstrap=bootstrap,
            )

    async def _handle_start(self, message: Any, args: str | None) -> None:
        telegram_id = int(message.from_user.id)
        logger.info(
            "telegram_start_received",
            telegram_id=telegram_id,
            chat_id=message.chat.id,
            start_args=self._preview_text(args),
        )
        if args and args.startswith("qr_"):
            await self._handle_qr_start(message.chat.id, telegram_id, args[3:])
            return
        await self._send_welcome(message.chat.id, telegram_id, getattr(message.from_user, "first_name", None))

    async def _require_student(self, message: Any) -> dict | None:
        bootstrap = await self._bootstrap(int(message.from_user.id))
        if bootstrap.get("status") != "linked" or "student" not in self._role_set(bootstrap):
            await self._send_private_message(
                message.chat.id,
                "Эта команда доступна только студенту после привязки аккаунта.",
                bootstrap=bootstrap,
            )
            return None
        return bootstrap

    async def _require_teacher(self, message: Any) -> dict | None:
        bootstrap = await self._bootstrap(int(message.from_user.id))
        if bootstrap.get("status") != "linked" or "teacher" not in self._role_set(bootstrap):
            await self._send_private_message(
                message.chat.id,
                "Эта команда доступна только преподавателю после привязки аккаунта.",
                bootstrap=bootstrap,
            )
            return None
        return bootstrap

    async def _handle_backend_error(self, message: Any, exc: BackendClientError) -> None:
        logger.warning(
            "telegram_backend_error",
            **self._message_context(message),
            status_code=exc.status_code,
            detail=exc.detail,
        )
        bootstrap = await self._bootstrap(int(message.from_user.id))
        await self._send_private_message(message.chat.id, f"Запрос не выполнен: {exc.detail}", bootstrap=bootstrap)

    async def _handle_student_schedule(self, message: Any) -> None:
        bootstrap = await self._require_student(message)
        if not bootstrap:
            return
        try:
            lessons = await self.backend.get_student_schedule(int(message.from_user.id))
        except BackendClientError as exc:
            await self._handle_backend_error(message, exc)
            return
        if not lessons:
            await self._send_private_message(message.chat.id, "В расписании пока нет занятий.", bootstrap=bootstrap)
            return
        lines = ["Ближайшие занятия:"]
        for lesson in lessons[:8]:
            lines.append(
                f"{self._format_window(lesson.get('starts_at'), lesson.get('ends_at'))} | "
                f"{lesson.get('discipline_name')} | {lesson.get('group_name')} | id `{lesson.get('id')}`"
            )
        await self._send_private_message(message.chat.id, "\n".join(lines), bootstrap=bootstrap)

    async def _handle_student_summary(self, message: Any) -> None:
        bootstrap = await self._require_student(message)
        if not bootstrap:
            return
        try:
            summary = await self.backend.get_student_summary(int(message.from_user.id))
        except BackendClientError as exc:
            await self._handle_backend_error(message, exc)
            return
        text = (
            "Сводка по посещаемости за период:\n"
            f"Присутствовал: {summary.get('present', 0)}\n"
            f"Опозданий: {summary.get('late', 0)}\n"
            f"Пропусков: {summary.get('absent', 0)}\n"
            f"Уважительных: {summary.get('excused_absent', 0)}\n"
            f"Неуважительных: {summary.get('unexcused_absent', 0)}"
        )
        await self._send_private_message(message.chat.id, text, bootstrap=bootstrap)

    async def _handle_student_rating(self, message: Any) -> None:
        bootstrap = await self._require_student(message)
        if not bootstrap:
            return
        try:
            rows = await self.backend.get_student_rating(int(message.from_user.id))
        except BackendClientError as exc:
            await self._handle_backend_error(message, exc)
            return
        if not rows:
            await self._send_private_message(message.chat.id, "Рейтинг еще не рассчитан.", bootstrap=bootstrap)
            return
        latest = rows[0]
        text = (
            "Последний рейтинг:\n"
            f"Балл: {latest.get('score')}\n"
            f"Посещаемость: {latest.get('attendance_pct')}%\n"
            f"Опоздания: {latest.get('late_count')}\n"
            f"Неуважительные пропуски: {latest.get('unexcused_absence_count')}\n"
            f"Период: {latest.get('period_start')} - {latest.get('period_end')}"
        )
        await self._send_private_message(message.chat.id, text, bootstrap=bootstrap)

    async def _handle_student_warnings(self, message: Any) -> None:
        bootstrap = await self._require_student(message)
        if not bootstrap:
            return
        try:
            rows = await self.backend.get_student_warnings(int(message.from_user.id))
        except BackendClientError as exc:
            await self._handle_backend_error(message, exc)
            return
        if not rows:
            await self._send_private_message(message.chat.id, "Предупреждений пока нет.", bootstrap=bootstrap)
            return
        lines = ["Последние предупреждения:"]
        for row in rows[:5]:
            lines.append(
                f"{row.get('created_at')} | статус: {row.get('status')} | причина: {row.get('reason')}"
            )
        await self._send_private_message(message.chat.id, "\n".join(lines), bootstrap=bootstrap)

    async def _handle_reason_help(self, message: Any) -> None:
        bootstrap = await self._require_student(message)
        if not bootstrap:
            return
        try:
            lessons = await self.backend.get_student_schedule(int(message.from_user.id))
        except BackendClientError as exc:
            await self._handle_backend_error(message, exc)
            return
        lines = [
            "Чтобы указать причину отсутствия, используйте:",
            "`/reason <lesson_id> <sick|study|personal|other> [комментарий]`",
            "Чтобы заявить заранее, используйте:",
            "`/predeclare <lesson_id> <sick|study|personal|other> [комментарий]`",
        ]
        if lessons:
            lines.append("")
            lines.append("Доступные занятия:")
            for lesson in lessons[:5]:
                lines.append(
                    f"{self._format_window(lesson.get('starts_at'), lesson.get('ends_at'))} | "
                    f"{lesson.get('discipline_name')} | id `{lesson.get('id')}`"
                )
        await self._send_private_message(message.chat.id, "\n".join(lines), bootstrap=bootstrap)

    async def _handle_reason_command(self, message: Any, args: str | None, *, is_predeclared: bool = False) -> None:
        bootstrap = await self._require_student(message)
        if not bootstrap:
            return
        parts = (args or "").split(maxsplit=2)
        if len(parts) < 2:
            await self._handle_reason_help(message)
            return
        lesson_id, reason_type = parts[0], parts[1]
        comment = parts[2] if len(parts) > 2 else None
        try:
            result = await self.backend.submit_student_absence_reason(
                telegram_id=int(message.from_user.id),
                lesson_id=lesson_id,
                reason_type=reason_type,
                comment=comment,
                is_predeclared=is_predeclared,
            )
        except BackendClientError as exc:
            await self._handle_backend_error(message, exc)
            return
        mode = "заявлена заранее" if is_predeclared else "сохранена"
        await self._send_private_message(
            message.chat.id,
            f"Причина отсутствия {mode}. Статус модерации: {result.get('status')}.",
            bootstrap=bootstrap,
        )

    async def _handle_teacher_lessons(self, message: Any) -> None:
        bootstrap = await self._require_teacher(message)
        if not bootstrap:
            return
        try:
            lessons = await self.backend.get_teacher_lessons(int(message.from_user.id))
        except BackendClientError as exc:
            await self._handle_backend_error(message, exc)
            return
        if not lessons:
            await self._send_private_message(message.chat.id, "У вас пока нет занятий.", bootstrap=bootstrap)
            return
        lines = ["Ваши занятия:"]
        for lesson in lessons[:8]:
            lines.append(
                f"{self._format_window(lesson.get('starts_at'), lesson.get('ends_at'))} | "
                f"{lesson.get('discipline_name')} | {lesson.get('group_name')} | id `{lesson.get('id')}`"
            )
        await self._send_private_message(message.chat.id, "\n".join(lines), bootstrap=bootstrap)

    async def _handle_teacher_qr_help(self, message: Any) -> None:
        bootstrap = await self._require_teacher(message)
        if not bootstrap:
            return
        try:
            lessons = await self.backend.get_teacher_lessons(int(message.from_user.id))
        except BackendClientError as exc:
            await self._handle_backend_error(message, exc)
            return
        lines = ["Чтобы сгенерировать QR, используйте `/qr <lesson_id>`."]
        for lesson in lessons[:5]:
            lines.append(
                f"{self._format_window(lesson.get('starts_at'), lesson.get('ends_at'))} | "
                f"{lesson.get('discipline_name')} | {lesson.get('group_name')} | id `{lesson.get('id')}`"
            )
        await self._send_private_message(message.chat.id, "\n".join(lines), bootstrap=bootstrap)

    async def _handle_teacher_qr(self, message: Any, args: str | None) -> None:
        bootstrap = await self._require_teacher(message)
        if not bootstrap:
            return
        lesson_id = (args or "").strip()
        if not lesson_id:
            await self._handle_teacher_qr_help(message)
            return
        try:
            payload = await self.backend.generate_teacher_qr(
                telegram_id=int(message.from_user.id),
                lesson_id=lesson_id,
            )
        except BackendClientError as exc:
            await self._handle_backend_error(message, exc)
            return
        text = (
            f"QR для занятия готов.\n"
            f"Ссылка: {payload.get('deeplink')}\n"
            f"Действует до: {payload.get('expires_at')}"
        )
        await self._send_private_message(message.chat.id, text, bootstrap=bootstrap)

    async def _handle_teacher_attendance_help(self, message: Any) -> None:
        bootstrap = await self._require_teacher(message)
        if not bootstrap:
            return
        try:
            lessons = await self.backend.get_teacher_lessons(int(message.from_user.id))
        except BackendClientError as exc:
            await self._handle_backend_error(message, exc)
            return
        lines = ["Чтобы посмотреть посещаемость, используйте `/attendance <lesson_id>`."]
        for lesson in lessons[:5]:
            lines.append(
                f"{self._format_window(lesson.get('starts_at'), lesson.get('ends_at'))} | "
                f"{lesson.get('discipline_name')} | {lesson.get('group_name')} | id `{lesson.get('id')}`"
            )
        await self._send_private_message(message.chat.id, "\n".join(lines), bootstrap=bootstrap)

    async def _handle_teacher_attendance(self, message: Any, args: str | None) -> None:
        bootstrap = await self._require_teacher(message)
        if not bootstrap:
            return
        lesson_id = (args or "").strip()
        if not lesson_id:
            await self._handle_teacher_attendance_help(message)
            return
        try:
            payload = await self.backend.get_teacher_lesson_attendance(
                telegram_id=int(message.from_user.id),
                lesson_id=lesson_id,
            )
        except BackendClientError as exc:
            await self._handle_backend_error(message, exc)
            return
        lesson = payload.get("lesson") or {}
        students = payload.get("students") or []
        lines = [
            f"Посещаемость: {lesson.get('discipline_name')} | {lesson.get('group_name')} | {lesson.get('starts_at')}"
        ]
        if not students:
            lines.append("Список студентов пуст.")
        for student in students[:15]:
            lines.append(
                f"{student.get('full_name')} | статус: {student.get('status') or 'нет отметки'}"
                f" | активность: {student.get('activity_score')}"
            )
        await self._send_private_message(message.chat.id, "\n".join(lines), bootstrap=bootstrap)

    async def _handle_teacher_reasons(self, message: Any) -> None:
        bootstrap = await self._require_teacher(message)
        if not bootstrap:
            return
        try:
            rows = await self.backend.get_teacher_absence_reasons(int(message.from_user.id))
        except BackendClientError as exc:
            await self._handle_backend_error(message, exc)
            return
        if not rows:
            await self._send_private_message(message.chat.id, "Причин для модерации пока нет.", bootstrap=bootstrap)
            return
        lines = [
            "Последние причины отсутствия:",
            "Для модерации используйте `/moderate <reason_id> <approved|rejected> [комментарий]`.",
        ]
        for row in rows[:8]:
            lines.append(
                f"{row.get('student_name')} | {row.get('discipline_name')} | {row.get('reason_type')} | "
                f"статус: {row.get('status')} | id `{row.get('id')}`"
            )
        await self._send_private_message(message.chat.id, "\n".join(lines), bootstrap=bootstrap)

    async def _handle_teacher_moderation(self, message: Any, args: str | None) -> None:
        bootstrap = await self._require_teacher(message)
        if not bootstrap:
            return
        parts = (args or "").split(maxsplit=2)
        if len(parts) < 2:
            await self._handle_teacher_reasons(message)
            return
        reason_id, status_value = parts[0], parts[1]
        comment = parts[2] if len(parts) > 2 else None
        try:
            result = await self.backend.moderate_teacher_reason(
                telegram_id=int(message.from_user.id),
                reason_id=reason_id,
                status=status_value,
                comment=comment,
            )
        except BackendClientError as exc:
            await self._handle_backend_error(message, exc)
            return
        await self._send_private_message(
            message.chat.id,
            f"Причина обновлена. Новый статус: {result.get('status')}.",
            bootstrap=bootstrap,
        )

    async def _handle_teacher_broadcast_help(self, message: Any) -> None:
        bootstrap = await self._require_teacher(message)
        if not bootstrap:
            return
        try:
            lessons = await self.backend.get_teacher_lessons(int(message.from_user.id))
        except BackendClientError as exc:
            await self._handle_backend_error(message, exc)
            return
        seen: set[str] = set()
        lines = ["Чтобы отправить рассылку, используйте `/broadcast <group_id> <текст>`."]
        for lesson in lessons:
            group_id = str(lesson.get("group_id"))
            if group_id in seen:
                continue
            seen.add(group_id)
            lines.append(f"{lesson.get('group_name')} | group_id `{group_id}`")
            if len(seen) >= 8:
                break
        await self._send_private_message(message.chat.id, "\n".join(lines), bootstrap=bootstrap)

    async def _handle_teacher_broadcast(self, message: Any, args: str | None) -> None:
        bootstrap = await self._require_teacher(message)
        if not bootstrap:
            return
        parts = (args or "").split(maxsplit=1)
        if len(parts) < 2:
            await self._handle_teacher_broadcast_help(message)
            return
        group_id, broadcast_message = parts
        try:
            result = await self.backend.teacher_broadcast(
                telegram_id=int(message.from_user.id),
                group_id=group_id,
                message=broadcast_message,
            )
        except BackendClientError as exc:
            await self._handle_backend_error(message, exc)
            return
        await self._send_private_message(
            message.chat.id,
            f"Рассылка поставлена в очередь. Получателей: {result.get('recipients', 0)}.",
            bootstrap=bootstrap,
        )

    async def _handle_teacher_activity(self, message: Any, args: str | None) -> None:
        bootstrap = await self._require_teacher(message)
        if not bootstrap:
            return
        parts = (args or "").split(maxsplit=3)
        if len(parts) < 3:
            await self._send_private_message(
                message.chat.id,
                "Используйте `/activity <lesson_id> <student_id> <score> [комментарий]`.",
                bootstrap=bootstrap,
            )
            return
        lesson_id, student_id, score_raw = parts[:3]
        comment = parts[3] if len(parts) > 3 else None
        try:
            score = float(score_raw)
        except ValueError:
            await self._send_private_message(message.chat.id, "Оценка активности должна быть числом.", bootstrap=bootstrap)
            return
        try:
            result = await self.backend.upsert_activity_score(
                telegram_id=int(message.from_user.id),
                lesson_id=lesson_id,
                student_id=student_id,
                score=score,
                comment=comment,
            )
        except BackendClientError as exc:
            await self._handle_backend_error(message, exc)
            return
        await self._send_private_message(
            message.chat.id,
            f"Активность сохранена: {result.get('score')}.",
            bootstrap=bootstrap,
        )

    async def _handle_assistant(self, message: Any, query: str | None = None) -> None:
        logger.info(
            "telegram_assistant_request",
            **self._message_context(message),
            query_preview=self._preview_text((query or message.text or "").strip()),
        )
        try:
            bootstrap = await self._bootstrap(int(message.from_user.id))
            reply = await self.backend.assistant_reply(
                telegram_id=int(message.from_user.id),
                message=(query or message.text or "").strip() or "FAQ",
            )
        except BackendClientError as exc:
            await self._handle_backend_error(message, exc)
            return
        await self._send_private_message(message.chat.id, str(reply.get("message") or ""), bootstrap=bootstrap)

    async def _handle_private_text(self, message: Any) -> None:
        text = (message.text or "").strip()
        if not text:
            return
        logger.info(
            "telegram_private_text_received",
            **self._message_context(message),
            text_preview=self._preview_text(text),
        )
        if text in self.STUDENT_BUTTONS:
            action = self.STUDENT_BUTTONS[text]
            logger.info("telegram_private_route", **self._message_context(message), route=action)
            if action == "student_schedule":
                await self._handle_student_schedule(message)
                return
            if action == "student_summary":
                await self._handle_student_summary(message)
                return
            if action == "student_rating":
                await self._handle_student_rating(message)
                return
            if action == "student_warnings":
                await self._handle_student_warnings(message)
                return
            if action == "student_reason_help":
                await self._handle_reason_help(message)
                return
        if text in self.TEACHER_BUTTONS:
            action = self.TEACHER_BUTTONS[text]
            logger.info("telegram_private_route", **self._message_context(message), route=action)
            if action == "teacher_lessons":
                await self._handle_teacher_lessons(message)
                return
            if action == "teacher_qr_help":
                await self._handle_teacher_qr_help(message)
                return
            if action == "teacher_attendance_help":
                await self._handle_teacher_attendance_help(message)
                return
            if action == "teacher_reasons":
                await self._handle_teacher_reasons(message)
                return
            if action == "teacher_broadcast_help":
                await self._handle_teacher_broadcast_help(message)
                return
        logger.info("telegram_private_route", **self._message_context(message), route="assistant_fallback")
        await self._handle_assistant(message, text)

    async def _configure_menu(self) -> None:
        from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo

        bot, _dispatcher = await self._ensure_runtime()
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Главное меню"),
                BotCommand(command="schedule", description="Расписание студента"),
                BotCommand(command="summary", description="Сводка по посещаемости"),
                BotCommand(command="rating", description="Рейтинг студента"),
                BotCommand(command="lessons", description="Занятия преподавателя"),
                BotCommand(command="faq", description="FAQ помощник"),
            ]
        )
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="Открыть приложение", web_app=WebAppInfo(url=self.settings.student_app_url))
        )

    async def start(self) -> None:
        if not self.settings.tg_polling_enabled or not self.settings.tg_bot_token:
            logger.info("telegram_polling_skipped", polling_enabled=self.settings.tg_polling_enabled)
            return
        bot, dispatcher = await self._ensure_runtime()
        if self.settings.tg_delete_webhook_on_start:
            await bot.delete_webhook(drop_pending_updates=self.settings.tg_drop_pending_updates_on_start)
        await self._configure_menu()
        logger.info("telegram_polling_started")
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())

    async def stop(self) -> None:
        if self._bot is not None:
            await self._bot.session.close()
            logger.info("telegram_polling_stopped")

    async def send_event_message(self, telegram_id: int, event_type: str, payload: dict) -> dict:
        logger.info(
            "telegram_internal_event_send",
            telegram_id=telegram_id,
            event_type=event_type,
        )
        bootstrap = await self._bootstrap(telegram_id)
        await self._send_private_message(telegram_id, render_event_message(event_type, payload), bootstrap=bootstrap)
        return {"status": "sent"}


def _services_from_request(request: Request) -> AppServices:
    return request.app.state.services


def _validated_user(init_data: str, settings: TGServiceSettings) -> TelegramWebAppUser:
    try:
        return validate_init_data(
            init_data,
            bot_token=settings.tg_bot_token,
            ttl_seconds=settings.tg_init_data_ttl_seconds,
        )
    except InitDataValidationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


def create_app(
    *,
    settings: TGServiceSettings | None = None,
    backend_client: BackendClient | None = None,
    bot_service: BotServiceProtocol | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    owns_backend = backend_client is None
    owns_bot = bot_service is None
    backend = backend_client or BackendClient(app_settings)
    bot = bot_service or BotService(app_settings, backend)
    services = AppServices(settings=app_settings, backend=backend, bot=bot)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging()
        app.state.services = services
        logger.info("tg_service_startup")
        polling_task: asyncio.Task | None = None
        if owns_bot and app_settings.tg_polling_enabled and app_settings.tg_bot_token:
            polling_task = asyncio.create_task(bot.start())
        try:
            yield
        finally:
            if polling_task is not None:
                polling_task.cancel()
                with suppress(asyncio.CancelledError):
                    await polling_task
            await bot.stop()
            if owns_backend:
                await backend.aclose()
            logger.info("tg_service_shutdown")

    app = FastAPI(title=app_settings.app_name, debug=app_settings.app_debug, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in app_settings.cors_allow_origins.split(",") if origin.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)
    app.state.services = services

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/webapp/bootstrap")
    async def webapp_bootstrap(payload: WebAppBootstrapRequest, request: Request):
        services = _services_from_request(request)
        user = _validated_user(payload.init_data, services.settings)
        logger.info(
            "tg_webapp_bootstrap_request",
            correlation_id=getattr(request.state, "correlation_id", None),
            telegram_id=user.telegram_id,
        )

        try:
            bootstrap = await services.backend.get_bootstrap(user.telegram_id)
        except BackendClientError as exc:
            logger.warning(
                "tg_webapp_bootstrap_failed",
                correlation_id=getattr(request.state, "correlation_id", None),
                telegram_id=user.telegram_id,
                status_code=exc.status_code,
                detail=exc.detail,
            )
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        if bootstrap.get("status") != "linked":
            logger.info(
                "tg_webapp_bootstrap_resolved",
                correlation_id=getattr(request.state, "correlation_id", None),
                telegram_id=user.telegram_id,
                status=bootstrap.get("status"),
            )
            return bootstrap

        try:
            exchange = await services.backend.exchange_auth(user.telegram_id)
        except BackendClientError as exc:
            if exc.status_code == status.HTTP_403_FORBIDDEN:
                logger.warning(
                    "tg_webapp_bootstrap_exchange_denied",
                    correlation_id=getattr(request.state, "correlation_id", None),
                    telegram_id=user.telegram_id,
                    detail=exc.detail,
                )
                return {"status": "link_required", "message": exc.detail}
            logger.warning(
                "tg_webapp_bootstrap_exchange_failed",
                correlation_id=getattr(request.state, "correlation_id", None),
                telegram_id=user.telegram_id,
                status_code=exc.status_code,
                detail=exc.detail,
            )
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

        logger.info(
            "tg_webapp_bootstrap_resolved",
            correlation_id=getattr(request.state, "correlation_id", None),
            telegram_id=user.telegram_id,
            status="linked",
        )
        return {
            "status": "linked",
            "tokens": {
                "access_token": exchange["access_token"],
                "refresh_token": exchange["refresh_token"],
                "token_type": exchange.get("token_type", "bearer"),
                "access_expires_at": exchange["access_expires_at"],
                "refresh_expires_at": exchange["refresh_expires_at"],
                "password_change_required": exchange["password_change_required"],
            },
            "user": exchange["user"],
        }

    @app.post("/webapp/binding-request")
    async def webapp_binding_request(payload: WebAppBindingRequest, request: Request):
        services = _services_from_request(request)
        user = _validated_user(payload.init_data, services.settings)
        full_name = (payload.full_name or user.full_name or "").strip() or None
        logger.info(
            "tg_webapp_binding_request_received",
            correlation_id=getattr(request.state, "correlation_id", None),
            telegram_id=user.telegram_id,
            has_group_code=bool(payload.group_code),
            has_note=bool(payload.note),
        )
        try:
            response = await services.backend.create_binding_request(
                telegram_id=user.telegram_id,
                telegram_username=user.username,
                full_name=full_name,
                group_code=payload.group_code,
                note=payload.note,
            )
        except BackendClientError as exc:
            logger.warning(
                "tg_webapp_binding_request_failed",
                correlation_id=getattr(request.state, "correlation_id", None),
                telegram_id=user.telegram_id,
                status_code=exc.status_code,
                detail=exc.detail,
            )
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        logger.info(
            "tg_webapp_binding_request_created",
            correlation_id=getattr(request.state, "correlation_id", None),
            telegram_id=user.telegram_id,
        )
        return {"status": "pending", **response}

    @app.post("/internal/messages/send")
    async def send_internal_message(
        payload: SendMessageRequest,
        request: Request,
        x_service_token: str = Header(...),
    ):
        services = _services_from_request(request)
        try:
            verify_backend_token(x_service_token, services.settings)
        except InitDataValidationError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

        logger.info(
            "tg_internal_message_send_request",
            correlation_id=getattr(request.state, "correlation_id", None),
            telegram_id=payload.telegram_id,
            event_type=payload.event_type,
            idempotency_key=payload.idempotency_key,
        )
        try:
            result = await services.bot.send_event_message(payload.telegram_id, payload.event_type, payload.payload)
        except RuntimeError as exc:
            logger.warning(
                "tg_internal_message_send_failed",
                correlation_id=getattr(request.state, "correlation_id", None),
                telegram_id=payload.telegram_id,
                event_type=payload.event_type,
                detail=str(exc),
            )
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover - defensive path for provider errors
            logger.exception(
                "tg_internal_message_send_exception",
                correlation_id=getattr(request.state, "correlation_id", None),
                telegram_id=payload.telegram_id,
                event_type=payload.event_type,
            )
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        logger.info(
            "tg_internal_message_sent",
            correlation_id=getattr(request.state, "correlation_id", None),
            telegram_id=payload.telegram_id,
            event_type=payload.event_type,
            idempotency_key=payload.idempotency_key,
        )
        return {"idempotency_key": payload.idempotency_key, **result}

    return app


app = create_app()
