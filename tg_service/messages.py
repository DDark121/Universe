from __future__ import annotations

STATUS_LABELS = {
    "present": "присутствие",
    "late": "опоздание",
    "absent": "отсутствие",
}


def render_event_message(event_type: str, payload: dict | None = None) -> str:
    payload = payload or {}
    if event_type == "attendance_window_open":
        return "Окно отметки на занятии открыто."
    if event_type == "attendance_window_close_soon":
        return "Окно отметки скоро закроется."
    if event_type == "attendance_marked":
        status = STATUS_LABELS.get(str(payload.get("status")), "отметка")
        return f"Посещаемость зафиксирована: {status}."
    if event_type == "attendance_late_detected":
        return "Зафиксировано опоздание на занятие."
    if event_type == "absence_reason_requested":
        return "Вы пропустили занятие. Откройте приложение и укажите причину отсутствия."
    if event_type == "reason_moderation_result":
        status = str(payload.get("status") or "updated")
        return f"Статус причины отсутствия обновлен: {status}."
    if event_type in {"risk_warning", "risk_warning_manual"}:
        return "Внимание: вы находитесь в зоне риска. Проверьте посещаемость и причины отсутствий."
    if event_type == "tutor_risk_warning":
        return "У студента вашей группы сработал риск-порог. Проверьте карточку студента в системе."
    if event_type == "lesson_rescheduled":
        return "Занятие было перенесено. Проверьте обновленное расписание."
    if event_type == "lesson_canceled":
        return "Занятие отменено."
    if event_type == "teacher_broadcast":
        message = str(payload.get("message") or "").strip()
        return f"Сообщение от преподавателя:\n\n{message}" if message else "У вас новое сообщение от преподавателя."
    if event_type == "tutor_broadcast":
        message = str(payload.get("message") or "").strip()
        return f"Сообщение от тьютора:\n\n{message}" if message else "У вас новое сообщение от тьютора."
    return "У вас новое уведомление в системе."
