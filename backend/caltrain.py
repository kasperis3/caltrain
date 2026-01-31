"""
Caltrain data from the 511 SF Bay API.

Use get_caltrain_stops() to get stop IDs, then get_next_trains(stop_id) for predictions.
All times are also returned in Pacific (PST/PDT) as *_local fields.
"""

import csv
import io
import os
import time
import zipfile
from pathlib import Path

import requests
from dotenv import load_dotenv
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Load .env from backend directory (API credentials)
load_dotenv(Path(__file__).resolve().parent / ".env")

API_KEY = os.getenv("API_KEY")
CALTRAIN_OPERATOR_ID = "CT"
PACIFIC = ZoneInfo("America/Los_Angeles")

# Cache stops list (rarely changes); TTL 24 hours
_stops_cache = None
_stops_cache_time = 0
STOPS_CACHE_TTL_SEC = 86400

# Cache travel-time matrix from GTFS stop_times; TTL 24 hours
_travel_time_cache = None
_travel_time_cache_time = 0
TRAVEL_TIME_CACHE_TTL_SEC = 86400

# Last-resort embedded list if both GTFS and NeTEx fail (e.g. API change or outage).
# Main Caltrain stations; IDs from GTFS. Update occasionally if new stations added.
EMBEDDED_STOPS = [
    {"id": "70011", "Name": "San Francisco Caltrain Station Northbound"},
    {"id": "70012", "Name": "San Francisco Caltrain Station Southbound"},
    {"id": "70021", "Name": "22nd Street Caltrain Station Northbound"},
    {"id": "70022", "Name": "22nd Street Caltrain Station Southbound"},
    {"id": "70031", "Name": "Bayshore Caltrain Station Northbound"},
    {"id": "70032", "Name": "Bayshore Caltrain Station Southbound"},
    {"id": "70041", "Name": "South San Francisco Caltrain Station Northbound"},
    {"id": "70042", "Name": "South San Francisco Caltrain Station Southbound"},
    {"id": "70051", "Name": "San Bruno Caltrain Station Northbound"},
    {"id": "70052", "Name": "San Bruno Caltrain Station Southbound"},
    {"id": "70061", "Name": "Millbrae Caltrain Station Northbound"},
    {"id": "70062", "Name": "Millbrae Caltrain Station Southbound"},
    {"id": "70071", "Name": "Broadway Caltrain Station Northbound"},
    {"id": "70072", "Name": "Broadway Caltrain Station Southbound"},
    {"id": "70081", "Name": "Burlingame Caltrain Station Northbound"},
    {"id": "70082", "Name": "Burlingame Caltrain Station Southbound"},
    {"id": "70091", "Name": "San Mateo Caltrain Station Northbound"},
    {"id": "70092", "Name": "San Mateo Caltrain Station Southbound"},
    {"id": "70101", "Name": "Hayward Park Caltrain Station Northbound"},
    {"id": "70102", "Name": "Hayward Park Caltrain Station Southbound"},
    {"id": "70111", "Name": "Hillsdale Caltrain Station Northbound"},
    {"id": "70112", "Name": "Hillsdale Caltrain Station Southbound"},
    {"id": "70121", "Name": "Belmont Caltrain Station Northbound"},
    {"id": "70122", "Name": "Belmont Caltrain Station Southbound"},
    {"id": "70131", "Name": "San Carlos Caltrain Station Northbound"},
    {"id": "70132", "Name": "San Carlos Caltrain Station Southbound"},
    {"id": "70141", "Name": "Redwood City Caltrain Station Northbound"},
    {"id": "70142", "Name": "Redwood City Caltrain Station Southbound"},
    {"id": "70151", "Name": "Menlo Park Caltrain Station Northbound"},
    {"id": "70152", "Name": "Menlo Park Caltrain Station Southbound"},
    {"id": "70161", "Name": "Palo Alto Caltrain Station Northbound"},
    {"id": "70162", "Name": "Palo Alto Caltrain Station Southbound"},
    {"id": "70171", "Name": "California Avenue Caltrain Station Northbound"},
    {"id": "70172", "Name": "California Avenue Caltrain Station Southbound"},
    {"id": "70181", "Name": "San Antonio Caltrain Station Northbound"},
    {"id": "70182", "Name": "San Antonio Caltrain Station Southbound"},
    {"id": "70191", "Name": "Mountain View Caltrain Station Northbound"},
    {"id": "70192", "Name": "Mountain View Caltrain Station Southbound"},
    {"id": "70201", "Name": "Sunnyvale Caltrain Station Northbound"},
    {"id": "70202", "Name": "Sunnyvale Caltrain Station Southbound"},
    {"id": "70211", "Name": "Lawrence Caltrain Station Northbound"},
    {"id": "70212", "Name": "Lawrence Caltrain Station Southbound"},
    {"id": "70221", "Name": "Santa Clara Caltrain Station Northbound"},
    {"id": "70222", "Name": "Santa Clara Caltrain Station Southbound"},
    {"id": "70231", "Name": "College Park Caltrain Station Northbound"},
    {"id": "70232", "Name": "College Park Caltrain Station Southbound"},
    {"id": "70241", "Name": "San Jose Diridon Caltrain Station Northbound"},
    {"id": "70242", "Name": "San Jose Diridon Caltrain Station Southbound"},
    {"id": "70251", "Name": "Tamien Caltrain Station Northbound"},
    {"id": "70252", "Name": "Tamien Caltrain Station Southbound"},
]


def _fetch_json(url, params):
    """GET url with params; handle 511 UTF-8 BOM and return JSON."""
    r = requests.get(url, params=params)
    r.encoding = "utf-8-sig"
    return r.json()


def _utc_to_local(iso_utc_str):
    """Turn a UTC ISO time string into Pacific time only, e.g. '8:41 AM' (timezone shown in header)."""
    if not iso_utc_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_utc_str.replace("Z", "+00:00"))
        local = dt.astimezone(PACIFIC)
        h = local.hour % 12 or 12
        return f"{h}:{local.minute:02d} {local.strftime('%p')}"
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
    name = _stop_display_name(stop)
    try:
        return STATION_LINE_ORDER.index(name)
    except ValueError:
        return len(STATION_LINE_ORDER)


def _stop_display_name(stop):
    """Strip direction suffix for display (e.g. 'San Francisco')."""
    name = (stop.get("Name") or "").replace(" Caltrain Station Northbound", "").replace(" Caltrain Station Southbound", "").strip()
    return name


def _stop_line_index(stop):
    """Index of stop in STATION_LINE_ORDER; len(ORDER) if not found."""
    name = _stop_display_name(stop)
    try:
        return STATION_LINE_ORDER.index(name)
    except ValueError:
        return len(STATION_LINE_ORDER)


def get_stops_in_direction(from_station, direction, operator_id=CALTRAIN_OPERATOR_ID):
    """
    Stops that are in the given direction from from_station (same format as get_caltrain_stops).
    from_station: station name or id. direction: 'northbound' or 'southbound'.
    Returns list of {id, Name} in line order, excluding the from station itself.
    """
    from_id, from_name, msg = _resolve_stop(from_station, direction=direction)
    if not from_id:
        return []
    stops = get_caltrain_stops(operator_id=operator_id)
    from_idx = None
    for st in stops:
        if st.get("id") == from_id:
            from_idx = _stop_line_index(st)
            break
    if from_idx is None:
        return []
    want_south = direction and "south" in direction.lower()
    result = []
    seen_display_name = set()
    for st in stops:
        idx = _stop_line_index(st)
        if st.get("id") == from_id:
            continue
        if want_south and idx > from_idx:
            name = _stop_display_name(st)
            if name not in seen_display_name:
                seen_display_name.add(name)
                result.append(st)
        elif not want_south and idx < from_idx:
            name = _stop_display_name(st)
            if name not in seen_display_name:
                seen_display_name.add(name)
                result.append(st)
    return result


def _gtfs_time_to_seconds(time_str):
    """Convert GTFS time (HH:MM:SS or H:MM:SS, can be 25:00:00) to seconds since midnight."""
    if not time_str:
        return None
    parts = (time_str or "").strip().split(":")
    if len(parts) != 3:
        return None
    try:
        h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
        return h * 3600 + m * 60 + s
    except (ValueError, TypeError):
        return None


def _build_travel_time_cache(operator_id=CALTRAIN_OPERATOR_ID):
    """Fetch GTFS, parse stop_times.txt, build (from_id, to_id) -> median minutes. Cached 24h."""
    global _travel_time_cache, _travel_time_cache_time
    now = time.time()
    if _travel_time_cache is not None and (now - _travel_time_cache_time) < TRAVEL_TIME_CACHE_TTL_SEC:
        return
    try:
        r = requests.get(
            "https://api.511.org/transit/datafeeds",
            params={"api_key": API_KEY, "operator_id": operator_id},
        )
        r.raise_for_status()
        r.encoding = "utf-8-sig"
    except Exception:
        return
    pairs_minutes = {}  # (from_id, to_id) -> list of minutes
    with zipfile.ZipFile(io.BytesIO(r.content), "r") as zf:
        stop_times_file = next((n for n in zf.namelist() if n.lower() == "stop_times.txt"), None)
        if not stop_times_file:
            return
        with zf.open(stop_times_file) as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
            rows = [row for row in reader]
    # Group by trip_id, sort by stop_sequence
    by_trip = {}
    for row in rows:
        trip_id = (row.get("trip_id") or "").strip()
        stop_id = (row.get("stop_id") or "").strip()
        arr = _gtfs_time_to_seconds(row.get("arrival_time"))
        dep = _gtfs_time_to_seconds(row.get("departure_time"))
        seq = (row.get("stop_sequence") or "").strip()
        try:
            seq = int(seq)
        except (ValueError, TypeError):
            continue
        if not trip_id or not stop_id or dep is None:
            continue
        by_trip.setdefault(trip_id, []).append((seq, stop_id, dep, arr))
    for trip_id, stop_list in by_trip.items():
        stop_list.sort(key=lambda x: x[0])
        for i in range(len(stop_list)):
            _, from_id, dep_i, _ = stop_list[i]
            for j in range(i + 1, len(stop_list)):
                _, to_id, dep_j, arr_j = stop_list[j]
                to_time = arr_j if arr_j is not None else dep_j
                if to_time is None:
                    continue
                minutes = (to_time - dep_i) // 60
                if minutes >= 0:
                    key = (from_id, to_id)
                    pairs_minutes.setdefault(key, []).append(minutes)
    # Median per pair
    _travel_time_cache = {}
    for (from_id, to_id), mins_list in pairs_minutes.items():
        if mins_list:
            mins_list.sort()
            mid = len(mins_list) // 2
            median = mins_list[mid] if len(mins_list) % 2 else (mins_list[mid - 1] + mins_list[mid]) // 2
            _travel_time_cache[(from_id, to_id)] = median
    _travel_time_cache_time = now


def get_travel_minutes(from_stop_id, to_stop_id, operator_id=CALTRAIN_OPERATOR_ID):
    """
    Typical travel time in minutes from from_stop_id to to_stop_id (from GTFS stop_times).
    Returns int or None if not available.
    """
    if not from_stop_id or not to_stop_id or from_stop_id == to_stop_id:
        return None
    _build_travel_time_cache(operator_id=operator_id)
    if _travel_time_cache is None:
        return None
    return _travel_time_cache.get((str(from_stop_id), str(to_stop_id)))


def _fetch_stops_from_gtfs(operator_id=CALTRAIN_OPERATOR_ID):
    """
    Fetch stop list from 511 GTFS feed (stops.txt). Primary source for stops.
    """
    r = requests.get(
        "https://api.511.org/transit/datafeeds",
        params={"api_key": API_KEY, "operator_id": operator_id},
    )
    r.raise_for_status()
    r.encoding = "utf-8-sig"
    stops = []
    with zipfile.ZipFile(io.BytesIO(r.content), "r") as zf:
        # Accept stops.txt or Stops.txt (case may change)
        stop_file = next((n for n in zf.namelist() if n.lower() == "stops.txt"), None)
        if not stop_file:
            return stops
        with zf.open(stop_file) as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
            for row in reader:
                location_type = (row.get("location_type") or "").strip()
                if location_type == "1":
                    continue
                stop_id = (row.get("stop_id") or "").strip()
                stop_name = (row.get("stop_name") or "").strip()
                if stop_id and stop_name:
                    stops.append({"id": stop_id, "Name": stop_name})
    return stops


def _fetch_stops_from_netex(operator_id=CALTRAIN_OPERATOR_ID):
    """
    Try 511 NeTEx /transit/stops API. Fallback if GTFS fails or format changes.
    Handles both legacy (ScheduledStopPoint list) and other list shapes.
    """
    data = _fetch_json(
        "https://api.511.org/transit/stops",
        {"api_key": API_KEY, "operator_id": operator_id, "format": "json"},
    )
    objs = data.get("Contents", {}).get("dataObjects", {})
    if isinstance(objs, dict):
        points = objs.get("ScheduledStopPoint") or objs.get("ScheduledStopPoints") or []
    elif isinstance(objs, list):
        points = objs
    else:
        points = []
    return [{"id": pt.get("id"), "Name": pt.get("Name")} for pt in points if isinstance(pt, dict) and (pt.get("id") or pt.get("Name"))]


# Exclude these from the station dropdown (case-insensitive substring in stop name)
STOP_NAME_EXCLUDES = ("elevator", "shuttle", "stanford")


def _filter_stops_for_display(stops):
    """Exclude elevator, shuttle, and Stanford stops from the list."""
    if not stops:
        return stops
    name_lower_keys = [k.lower() for k in STOP_NAME_EXCLUDES]
    return [
        s for s in stops
        if not any(k in (s.get("Name") or "").lower() for k in name_lower_keys)
    ]


def get_caltrain_stops(operator_id=CALTRAIN_OPERATOR_ID):
    """
    List of Caltrain stops (id + name) in line order. Use id with get_next_trains().
    Excludes elevator, shuttle, and Stanford stops. Future-proof: tries GTFS first,
    then NeTEx, then cache, then embedded list. Cached 24 hours.
    """
    global _stops_cache, _stops_cache_time
    now = time.time()
    if _stops_cache is not None and (now - _stops_cache_time) < STOPS_CACHE_TTL_SEC:
        return _stops_cache

    stops = []
    # 1. Primary: GTFS feed (most reliable)
    try:
        stops = _fetch_stops_from_gtfs(operator_id=operator_id)
    except Exception:
        pass
    # 2. Fallback: NeTEx /transit/stops (in case 511 restores or changes format)
    if not stops:
        try:
            stops = _fetch_stops_from_netex(operator_id=operator_id)
        except Exception:
            pass
    # 3. Use cache if we have it (e.g. API temporarily down)
    if not stops and _stops_cache is not None:
        return _stops_cache
    # 4. Last resort: embedded list so dropdown is never empty
    if not stops:
        stops = list(EMBEDDED_STOPS)

    stops = _filter_stops_for_display(stops)
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


def next_trains(stop_id_or_name, limit=5, direction=None, to_stop=None):
    """
    Next trains at a stop. Pass stop by ID (e.g. "70031") or name (e.g. "San Francisco").
    For names that match two platforms, pass direction: "northbound" or "southbound".
    If to_stop (name or id) is given, each train includes travel_minutes from this stop to to_stop.

    Returns dict: {"stop_id", "stop_name", "trains": [{"service", "destination", "time", "minutes_until", "travel_minutes"?}, ...], "message"}.
    """
    stop_id, stop_name, message = _resolve_stop(stop_id_or_name, direction=direction)
    if not stop_id:
        return {"stop_id": None, "stop_name": None, "trains": [], "message": message}
    to_id = None
    if to_stop:
        to_id, _, _ = _resolve_stop(to_stop, direction=direction)
    travel_min = get_travel_minutes(stop_id, to_id) if to_id else None
    raw = get_next_trains(stop_id, limit=limit)
    trains = []
    for t in raw:
        line_ref = t.get("line_ref") or ""
        service = _service_tag(line_ref) or (t.get("line_name") or "").strip() or "—"
        dest = (t.get("destination") or "").strip() or "—"
        exp_dep = t.get("expected_departure") or t.get("expected_arrival")
        time_str = t.get("expected_departure_local") or t.get("expected_arrival_local") or "—"
        minutes_until = _minutes_until(exp_dep) if exp_dep else None
        train = {
            "service": service,
            "destination": dest,
            "time": time_str,
            "minutes_until": minutes_until,
        }
        if travel_min is not None:
            train["travel_minutes"] = travel_min
        trains.append(train)
    return {"stop_id": stop_id, "stop_name": stop_name, "trains": trains, "message": None}
