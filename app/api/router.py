from fastapi import APIRouter

from app.api.v1.admin import router as admin_router
from app.api.v1.auth import router as auth_router
from app.api.v1.internal import router as internal_router
from app.api.v1.public import router as public_router
from app.api.v1.student import router as student_router
from app.api.v1.teacher import router as teacher_router
from app.api.v1.tg import router as tg_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
api_router.include_router(teacher_router, prefix="/teacher", tags=["teacher"])
api_router.include_router(student_router, prefix="/student", tags=["student"])
api_router.include_router(tg_router, prefix="/tg", tags=["tg"])
api_router.include_router(public_router, prefix="/public", tags=["public"])
api_router.include_router(internal_router, prefix="/internal", tags=["internal"])
