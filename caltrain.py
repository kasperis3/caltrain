"""
Caltrain data from the 511 SF Bay API.

Use get_caltrain_stops() to get stop IDs, then get_next_trains(stop_id) for predictions.
All times are also returned in Pacific (PST/PDT) as *_local fields.
"""

import os
import time

import requests
from dotenv import load_dotenv
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

load_dotenv()

API_KEY = os.getenv("API_KEY")
CALTRAIN_OPERATOR_ID = "CT"
PACIFIC = ZoneInfo("America/Los_Angeles")

# Cache stops list (rarely changes); TTL 15 minutes
_stops_cache = None
_stops_cache_time = 0
STOPS_CACHE_TTL_SEC = 900


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
    # Call without stopCode to get full feed, then filter by stop (511 returns more trains per stop this way)
    data = _fetch_json(
        "https://api.511.org/transit/StopMonitoring",
        {
            "api_key": API_KEY,
            "agency": operator_id,
            "format": "json",
        },
    )

    visits = []
    try:
        delivery = data.get("ServiceDelivery", {})
        sm = delivery.get("StopMonitoringDelivery", {})
        raw = sm.get("MonitoredStopVisit", [])
        stop_str = str(stop_id)
        raw = [v for v in raw if v.get("MonitoringRef") == stop_str]
        for v in raw:
            journey = v.get("MonitoredVehicleJourney", {})
            call = journey.get("MonitoredCall", {})
            line = (journey.get("PublishedLineName") or "").strip()
            line_ref = (journey.get("LineRef") or "").strip()
            dest = (journey.get("DestinationName") or "").strip()
            exp_dep = call.get("ExpectedDepartureTime")
            exp_arr = call.get("ExpectedArrivalTime")
            aimed_dep = call.get("AimedDepartureTime")
            aimed_arr = call.get("AimedArrivalTime")
            visits.append({
                "line_name": line,
                "line_ref": line_ref,
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

    # Sort by expected departure (soonest first); put missing times at end
    def _sort_key(v):
        t = v.get("expected_departure") or v.get("expected_arrival") or ""
        return (t == "", t)

    visits.sort(key=_sort_key)

    if limit is not None:
        visits = visits[:limit]
    return visits


# Southbound line order (San Francisco to Tamien/Gilroy) for dropdown ordering
STATION_LINE_ORDER = [
    "San Francisco", "22nd Street", "Bayshore", "South San Francisco", "San Bruno",
    "Millbrae", "Broadway", "Burlingame", "San Mateo", "Hayward Park", "Hillsdale",
    "Belmont", "San Carlos", "Redwood City", "Atherton", "Menlo Park", "Palo Alto",
    "California Avenue", "San Antonio", "Mountain View", "Sunnyvale", "Lawrence",
    "Santa Clara", "College Park", "San Jose Diridon", "Tamien",
    "Capitol", "Blossom Hill", "Morgan Hill", "San Martin", "Gilroy", "Pulgas",
]


def _station_sort_key(stop):
    """Order key for line order; stations not in list go at end."""
    name = (stop.get("Name") or "").replace(" Caltrain Station Northbound", "").replace(" Caltrain Station Southbound", "").strip()
    try:
        return STATION_LINE_ORDER.index(name)
    except ValueError:
        return len(STATION_LINE_ORDER)


def get_caltrain_stops(operator_id=CALTRAIN_OPERATOR_ID):
    """
    List of Caltrain stops (id + name) in line order. Use id with get_next_trains().
    Cached 15 minutes to avoid repeated 511 API calls when resolving station names.
    """
    global _stops_cache, _stops_cache_time
    now = time.time()
    if _stops_cache is not None and (now - _stops_cache_time) < STOPS_CACHE_TTL_SEC:
        return _stops_cache
    data = _fetch_json(
        "https://api.511.org/transit/stops",
        {"api_key": API_KEY, "operator_id": operator_id, "format": "json"},
    )
    objs = data.get("Contents", {}).get("dataObjects", {})
    if isinstance(objs, dict):
        points = objs.get("ScheduledStopPoint", [])
    elif isinstance(objs, list):
        points = objs if objs else []
    else:
        points = []
    stops = [{"id": pt.get("id"), "Name": pt.get("Name")} for pt in points if isinstance(pt, dict)]
    if not stops:
        return _stops_cache if _stops_cache is not None else []
    stops.sort(key=_station_sort_key)
    _stops_cache = stops
    _stops_cache_time = now
    return stops


def _normalize_direction(direction):
    """Return 'Northbound', 'Southbound', or None."""
    if not direction:
        return None
    d = str(direction).strip().lower()
    if d in ("northbound", "north", "nb", "n"):
        return "Northbound"
    if d in ("southbound", "south", "sb", "s"):
        return "Southbound"
    return None


def _resolve_stop(stop_id_or_name, direction=None):
    """
    Resolve stop ID or name to (stop_id, stop_name).
    direction: "northbound"/"north" or "southbound"/"south" when name matches multiple platforms.
    Returns (stop_id, stop_name, message). message is set when ambiguous (no direction given).
    """
    if not stop_id_or_name:
        return None, None, None
    s = str(stop_id_or_name).strip()
    # If it looks like an ID (all digits), use it
    if s.isdigit():
        stops = get_caltrain_stops()
        for st in stops:
            if st.get("id") == s:
                return s, st.get("Name"), None
        return s, None, None
    # Search by name (case-insensitive substring)
    stops = get_caltrain_stops()
    name_lower = s.lower()
    matches = [st for st in stops if name_lower in (st.get("Name") or "").lower()]
    if not matches:
        return None, None, None
    if len(matches) == 1:
        st = matches[0]
        return st.get("id"), st.get("Name"), None
    # Multiple matches (e.g. Northbound + Southbound) — filter by direction
    want_dir = _normalize_direction(direction)
    if want_dir:
        for st in matches:
            if want_dir in (st.get("Name") or ""):
                return st.get("id"), st.get("Name"), None
        return None, None, None
    return None, None, "Multiple stops match. Specify direction: Northbound or Southbound."


def _service_tag(line_ref):
    """Derive short service tag from 511 LineRef (e.g. 'Local Weekday' -> 'Local')."""
    if not line_ref:
        return None
    r = line_ref.lower()
    if "limited" in r or "baby bullet" in r:
        return "Limited"
    if "express" in r:
        return "Express"
    if "local" in r:
        return "Local"
    if "weekend" in r:
        return "Weekend Local"
    if "south county" in r or "connector" in r:
        return "South County"
    return line_ref.strip() or None


def _minutes_until(iso_utc_str):
    """Minutes from now until the given UTC ISO time; None if unparseable."""
    if not iso_utc_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_utc_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = dt - now
        return int(delta.total_seconds() / 60)
    except (ValueError, TypeError):
        return None


def next_trains(stop_id_or_name, limit=5, direction=None):
    """
    Next trains at a stop. Pass stop by ID (e.g. "70031") or name (e.g. "San Francisco").
    For names that match two platforms, pass direction: "northbound" or "southbound".

    Returns dict: {"stop_id", "stop_name", "trains": [{"service", "destination", "time", "minutes_until"}, ...], "message"}.
    """
    stop_id, stop_name, message = _resolve_stop(stop_id_or_name, direction=direction)
    if not stop_id:
        return {"stop_id": None, "stop_name": None, "trains": [], "message": message}
    raw = get_next_trains(stop_id, limit=limit)
    trains = []
    for t in raw:
        line_ref = t.get("line_ref") or ""
        service = _service_tag(line_ref) or (t.get("line_name") or "").strip() or "—"
        dest = (t.get("destination") or "").strip() or "—"
        exp_dep = t.get("expected_departure") or t.get("expected_arrival")
        time_str = t.get("expected_departure_local") or t.get("expected_arrival_local") or "—"
        minutes_until = _minutes_until(exp_dep) if exp_dep else None
        trains.append({
            "service": service,
            "destination": dest,
            "time": time_str,
            "minutes_until": minutes_until,
        })
    return {"stop_id": stop_id, "stop_name": stop_name, "trains": trains, "message": None}
