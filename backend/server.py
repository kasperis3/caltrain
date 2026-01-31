"""
Caltrain API server. All routes under /api. Serves frontend at / for local dev.

Run from repo root: uvicorn backend.server:app --reload
Then open http://127.0.0.1:8000/ (frontend) or .../api/stops (API).
"""

from pathlib import Path

from fastapi import APIRouter, FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Use backend.caltrain so uvicorn can run from repo root: uvicorn backend.server:app
from backend.caltrain import get_next_trains, get_caltrain_stops, get_stops_in_direction, next_trains

app = FastAPI(title="Caltrain API")

# Serve frontend at / for local dev (frontend/ is sibling of backend/)
_frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if _frontend_dir.exists():
    @app.get("/")
    def index():
        return FileResponse(_frontend_dir / "index.html")

    app.mount("/css", StaticFiles(directory=_frontend_dir / "css"), name="css")
    app.mount("/js", StaticFiles(directory=_frontend_dir / "js"), name="js")

# All API routes under /api for nginx proxy
api_router = APIRouter(prefix="/api", tags=["api"])


@api_router.get("/stops")
def stops():
    """List all Caltrain stops (id + name)."""
    return get_caltrain_stops()


@api_router.get("/stops/{stop_id}/trains")
def trains(stop_id: str, limit: int | None = 10):
    """Next train predictions at a stop. Optional query: limit (default 10)."""
    return get_next_trains(stop_id, limit=limit)


@api_router.get("/stops_in_direction")
def stops_in_direction(
    from_station: str = Query(..., alias="from"),
    direction: str = ...,
):
    """Stations in the given direction from from_station (northbound or southbound)."""
    return get_stops_in_direction(from_station, direction)


@api_router.get("/next_trains")
def next_trains_endpoint(stop: str, limit: int = 5, direction: str | None = None, to: str | None = None):
    """Next trains at a stop. Pass stop by ID or name; use direction when name has two platforms. Optional to= for trip time to that station."""
    return next_trains(stop, limit=limit, direction=direction, to_stop=to)


app.include_router(api_router)
