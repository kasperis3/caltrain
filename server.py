"""
Minimal FastAPI server for Caltrain data.

Run: python3 -m uvicorn server:app --reload
Then open http://127.0.0.1:8000
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from caltrain import get_next_trains, get_caltrain_stops, next_trains

app = FastAPI(title="Caltrain API")

static_dir = Path(__file__).parent / "static"

if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/")
    def index():
        return FileResponse(static_dir / "index.html")


@app.get("/stops")
def stops():
    """List all Caltrain stops (id + name)."""
    return get_caltrain_stops()


@app.get("/stops/{stop_id}/trains")
def trains(stop_id: str, limit: int | None = 10):
    """Next train predictions at a stop. Optional query: limit (default 10)."""
    return get_next_trains(stop_id, limit=limit)


@app.get("/next_trains")
def next_trains_endpoint(stop: str, limit: int = 5, direction: str | None = None):
    """Next trains at a stop. Pass stop by ID or name; use direction (northbound/southbound) when name has two platforms."""
    return next_trains(stop, limit=limit, direction=direction)
