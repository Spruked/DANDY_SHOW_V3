import os
from pathlib import Path

from app.main import app


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("DANDY_HOST", "127.0.0.1")
    port = int(os.getenv("DANDY_PORT", "8010"))

    # Exclude heavy write dirs from watchfiles so a produce job is never
    # killed by uvicorn reloading mid-TTS.
    project_root = Path(__file__).resolve().parent.parent
    reload_excludes = [
        str(project_root / "episodes"),
        str(project_root / "staging"),
        str(project_root / "audio"),
        str(project_root / "logs"),
        str(project_root / "social" / "generated"),
        str(project_root / "social" / "renders"),
    ]

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=True,
        reload_excludes=reload_excludes,
    )
