"""
Caltrain data from the 511 SF Bay API.

Use get_caltrain_stops() to get stop IDs, then get_next_trains(stop_id) for predictions.
All times are also returned in Pacific (PST/PDT) as *_local fields.
"""

import os

import requests
from dotenv import load_dotenv
from datetime import datetime
from zoneinfo import ZoneInfo

load_dotenv()

API_KEY = os.getenv("API_KEY")
CALTRAIN_OPERATOR_ID = "CT"
PACIFIC = ZoneInfo("America/Los_Angeles")


def _fetch_json(url, params):
    """GET url with params; handle 511 UTF-8 BOM and return JSON."""
    r = requests.get(url, params=params)
    r.encoding = "utf-8-sig"
    return r.json()


def _utc_to_local(iso_utc_str):
    """Turn a UTC ISO time string into Pacific, e.g. '8:41 AM PST'."""
    if not iso_utc_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_utc_str.replace("Z", "+00:00"))
        local = dt.astimezone(PACIFIC)
        h = local.hour % 12 or 12
        return f"{h}:{local.minute:02d} {local.strftime('%p %Z')}"
    except (ValueError, TypeError):
        return None


def get_next_trains(stop_id, operator_id=CALTRAIN_OPERATOR_ID, limit=None):
    """
    Next train predictions at a stop (real-time from 511).

    - stop_id: e.g. "70031" (use get_caltrain_stops() to find IDs).
    - operator_id: agency, default Caltrain (CT).
    - limit: max predictions to return; None = all.

    Returns a list of dicts with line_name, destination, expected_*_local, etc.
    """
    data = _fetch_json(
        "https://api.511.org/transit/StopMonitoring",
        {
            "api_key": API_KEY,
            "agency": operator_id,
            "stopCode": str(stop_id),
            "format": "json",
        },
    )

    visits = []
    try:
        delivery = data.get("ServiceDelivery", {})
        sm = delivery.get("StopMonitoringDelivery", {})
        raw = sm.get("MonitoredStopVisit", [])
        for v in raw:
            journey = v.get("MonitoredVehicleJourney", {})
            call = journey.get("MonitoredCall", {})
            line = (journey.get("PublishedLineName") or "").strip()
            dest = (journey.get("DestinationName") or "").strip()
            exp_dep = call.get("ExpectedDepartureTime")
            exp_arr = call.get("ExpectedArrivalTime")
            aimed_dep = call.get("AimedDepartureTime")
            aimed_arr = call.get("AimedArrivalTime")
            visits.append({
                "line_name": line,
                "destination": dest,
                "expected_departure": exp_dep,
                "expected_arrival": exp_arr,
                "aimed_departure": aimed_dep,
                "aimed_arrival": aimed_arr,
                "expected_departure_local": _utc_to_local(exp_dep),
                "expected_arrival_local": _utc_to_local(exp_arr),
                "aimed_departure_local": _utc_to_local(aimed_dep),
                "aimed_arrival_local": _utc_to_local(aimed_arr),
            })
    except (KeyError, TypeError, AttributeError):
        pass

    if limit is not None:
        visits = visits[:limit]
    return visits


def get_caltrain_stops(operator_id=CALTRAIN_OPERATOR_ID):
    """
    List of Caltrain stops (id + name). Use id with get_next_trains().
    """
    data = _fetch_json(
        "https://api.511.org/transit/stops",
        {"api_key": API_KEY, "operator_id": operator_id, "format": "json"},
    )

    out = []
    for obj in data.get("Contents", {}).get("dataObjects", []):
        for pt in obj.get("ServiceFrame", {}).get("scheduledStopPoints", []):
            out.append({"id": pt.get("id"), "Name": pt.get("Name")})
    return out
