from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.db import init_db
from app.routers.auth import router as auth_router
from app.routers.pages import router as pages_router
from app.routers.port_battle_api import router as port_battle_api_router
from app.routers.port_battle_roster_api import router as port_battle_roster_api_router
from app.routers.profile_api import router as profile_api_router
from app.routers.repair_reimbursement import router as repair_reimbursement_router
from app.services.discord_voice_tracker import start_voice_tracker, stop_voice_tracker


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    settings = get_settings()
    await start_voice_tracker(settings)
    try:
        yield
    finally:
        await stop_voice_tracker()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.app_name, lifespan=lifespan)
    application.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        max_age=settings.session_max_age_seconds,
        same_site="lax",
        https_only=False,
    )

    base_dir = Path(__file__).resolve().parent.parent
    application.mount("/static", StaticFiles(directory=str(base_dir / "static")), name="static")

    application.include_router(auth_router, prefix="/auth")
    application.include_router(pages_router)
    application.include_router(port_battle_api_router)
    application.include_router(port_battle_roster_api_router)
    application.include_router(profile_api_router)
    application.include_router(repair_reimbursement_router)

    return application


app = create_app()
