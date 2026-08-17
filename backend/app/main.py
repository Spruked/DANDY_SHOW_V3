from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api.assets import router as assets_router
from .api.library import router as library_router
from .api.segment_production import router as segment_production_router
from .api.production import router as production_router
from .api.social import router as social_router
from .api.social_slideshow import router as slideshow_router
from .api.social_adcards import router as adcards_router
from .api.system import router as system_router
from .api.conversation import router as conversation_router
from .api.ads import router as ads_router
from .api.obs import router as obs_router
from .api.mixer import router as mixer_router
from .core.settings import load_project_config
from .core.paths import PROJECT_ROOT
from .websockets.manager import ConnectionManager


manager = ConnectionManager()


def create_app() -> FastAPI:
    config = load_project_config()
    app = FastAPI(
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

    app.include_router(system_router)
    app.include_router(system_router, prefix="/api")
    app.include_router(library_router)
    app.include_router(library_router, prefix="/api")
    app.include_router(assets_router)
    app.include_router(assets_router, prefix="/api")

    # Segment production is registered first so 1-15 minute targets bypass the
    # legacy 5,000-word floor and automatic in-segment ad insertion. The segment
    # route delegates targets above 15 minutes back to the legacy handler.
    app.include_router(segment_production_router)
    app.include_router(segment_production_router, prefix="/api")
    app.include_router(production_router)
    app.include_router(production_router, prefix="/api")

    app.include_router(social_router)
    app.include_router(social_router, prefix="/api")
    app.include_router(ads_router)
    app.include_router(ads_router, prefix="/api")
    app.include_router(obs_router)
    app.include_router(obs_router, prefix="/api")
    app.include_router(mixer_router)
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

    return app


app = create_app()
