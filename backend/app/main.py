from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from .core.safety import validate_id, contained_path
import re
from contextlib import asynccontextmanager
from .core.safety import file_lock
from .services.storage.episode_store import recover_interrupted_jobs
from pathlib import Path

from .api.assets import router as assets_router
from .api.context import router as context_router
from .api.vault import router as vault_router
from .api.library import router as library_router
from .api.segment_production import router as segment_production_router
from .api.segments import router as segments_router
from .api.production import router as production_router
from .api.social import router as social_router
from .api.social_slideshow import router as slideshow_router
from .api.social_adcards import router as adcards_router
from .api.system import router as system_router
from .api.qwen_studio import router as qwen_studio_router
from .api.conversation import router as conversation_router
from .api.ads import router as ads_router
from .api.obs import router as obs_router
from .api.mixer import router as mixer_router
from .api.planning import router as planning_router
from .core.settings import load_project_config
from .core.paths import PROJECT_ROOT
from .websockets.manager import manager


def create_app(runtime_root: Path | None = None, recover_jobs: bool = True) -> FastAPI:
    config = load_project_config()
    @asynccontextmanager
    async def lifespan(app):
        with file_lock((runtime_root or PROJECT_ROOT / "staging") / "studio-runtime", timeout=0):
            if recover_jobs:
                recover_interrupted_jobs()
            watcher = None
            if runtime_root is None:
                from .services.storage.vault_store import DandyVault, VaultWatcher
                vault = DandyVault()
                if vault.config.get('enabled', True):
                    watcher = VaultWatcher(vault)
                    watcher.start()
            try:
                yield
            finally:
                if watcher:
                    watcher.stop()

    app = FastAPI(
        lifespan=lifespan,
        title="Phil and Jim Dandy Show Studio",
        version="0.1.0",
        description="Private internal React/Vite + FastAPI studio for Phil and Jim Dandy production.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    async def root():
        return {
            "project": config.get("project", {}).get("name", "Phil and Jim Dandy Show"),
            "mode": config.get("project", {}).get("mode", "private_internal_studio"),
            "dashboard_reference": config.get("dashboard", {}).get("ui_reference_source"),
            "message": "FastAPI shell is live for the merged private studio build.",
        }

    @app.exception_handler(ValueError)
    async def invalid_value(request, exc):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.middleware("http")
    async def validate_request(request, call_next):
        try:
            for segment in re.findall(r"/(?:episodes|ads)/([^/]+)", request.url.path):
                validate_id(segment)
            for key in ("episode_id", "job_id", "slide_id", "card_id"):
                if key in request.query_params:
                    validate_id(request.query_params[key])
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"detail": str(exc)})
        return await call_next(request)

    app.include_router(system_router)
    app.include_router(system_router, prefix="/api")
    app.include_router(qwen_studio_router)
    app.include_router(qwen_studio_router, prefix="/api")
    app.include_router(library_router)
    app.include_router(library_router, prefix="/api")
    app.include_router(vault_router)
    app.include_router(vault_router, prefix="/api")
    app.include_router(context_router)
    app.include_router(context_router, prefix="/api")
    app.include_router(assets_router)
    app.include_router(assets_router, prefix="/api")

    # Compatibility alias delegates to the unified production handler.
    app.include_router(segment_production_router)
    app.include_router(segment_production_router, prefix="/api")
    app.include_router(segments_router)
    app.include_router(segments_router, prefix="/api")
    app.include_router(production_router)
    app.include_router(production_router, prefix="/api")

    app.include_router(social_router)
    app.include_router(social_router, prefix="/api")
    app.include_router(ads_router)
    app.include_router(ads_router, prefix="/api")
    app.include_router(obs_router)
    app.include_router(obs_router, prefix="/api")
    app.include_router(mixer_router)
    app.include_router(planning_router)
    app.include_router(planning_router, prefix="/api")
    app.include_router(mixer_router, prefix="/api")
    app.include_router(conversation_router)
    app.include_router(conversation_router, prefix="/api")
    app.include_router(slideshow_router)
    app.include_router(adcards_router)

    renders_dir = PROJECT_ROOT / "social" / "renders"
    renders_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/renders", StaticFiles(directory=str(renders_dir)), name="renders")

    @app.websocket("/ws/{channel}")
    async def websocket_channel(websocket: WebSocket, channel: str):
        await manager.connect(websocket, channel)
        await manager.broadcast(
            channel,
            {"type": "connected", "channel": channel, "message": "WebSocket shell connected"},
        )
        try:
            while True:
                text = await websocket.receive_text()
                await manager.broadcast(channel, {"type": "echo", "channel": channel, "text": text})
        except WebSocketDisconnect:
            manager.disconnect(websocket, channel)

    frontend_dist = PROJECT_ROOT / "frontend" / "dist"
    if (frontend_dist / "index.html").is_file():
        app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="frontend-assets")

        @app.get("/dandy-show-phil-jim.png", include_in_schema=False)
        async def studio_brand_image():
            return FileResponse(contained_path(frontend_dist, "dandy-show-phil-jim.png"))

        @app.get("/studio", include_in_schema=False)
        async def studio_page():
            return FileResponse(contained_path(frontend_dist, "index.html"))

    return app


app = create_app()
