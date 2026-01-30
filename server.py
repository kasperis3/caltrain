"""
Minimal FastAPI server for Caltrain data.

Run: uvicorn server:app --reload
"""

from fastapi import FastAPI

from caltrain import get_next_trains, get_caltrain_stops

app = FastAPI(title="Caltrain API")


@app.get("/stops")
def stops():
    """List all Caltrain stops (id + name)."""
    return get_caltrain_stops()


@app.get("/stops/{stop_id}/trains")
def trains(stop_id: str, limit: int | None = 10):
    """Next train predictions at a stop. Optional query: limit (default 10)."""
    return get_next_trains(stop_id, limit=limit)
