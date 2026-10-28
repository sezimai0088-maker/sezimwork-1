from aiogram import Router

from bot.handlers import admin, attendance, start


def build_router() -> Router:
    router = Router()
    # Порядок важен: сначала подключение и команды, потом кнопки и геолокация.
    router.include_router(start.router)
    router.include_router(admin.router)
    router.include_router(attendance.router)
    return router
