#!/usr/bin/env python3
"""
Debug script to verify the 511 API and our parsing.
Run from project root: python3 scripts/debug_api.py

Stops are now loaded from the GTFS feed (511 NeTEx /transit/stops no longer
returns a list). This script checks StopMonitoring (with/without stopcode) and get_caltrain_stops().
"""

import os
import sys
from pathlib import Path

# Add project root so backend can be imported (run from repo root: python3 scripts/debug_api.py)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load .env from scripts/ or backend/
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")
load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env")

API_KEY = os.getenv("API_KEY")
if not API_KEY:
    print("ERROR: API_KEY not set. Add it to .env (see .env.example)")
    sys.exit(1)
print("OK: API_KEY is set")

import requests

# --- 1. Raw 511 stops API ---
print("\n--- 511 Stops API (raw) ---")
url = "https://api.511.org/transit/stops"
params = {"api_key": API_KEY, "operator_id": "CT", "format": "json"}
try:
    r = requests.get(url, params=params)
    r.encoding = "utf-8-sig"
    print(f"  Status: {r.status_code}")
    if r.status_code != 200:
        print(f"  Body (first 500 chars): {r.text[:500]}")
        sys.exit(1)
    data = r.json()
except Exception as e:
    print(f"  ERROR: {e}")
    sys.exit(1)

# Inspect structure
top_keys = list(data.keys()) if isinstance(data, dict) else []
print(f"  Top-level keys: {top_keys}")
# Recursively find any list that looks like stops (items with id + Name)
def find_stop_like_lists(obj, path="data"):
    if isinstance(obj, list) and len(obj) > 0:
        first = obj[0]
        if isinstance(first, dict) and ("id" in first or "Name" in first or "name" in first):
            return [(path, len(obj), list(first.keys())[:6])]
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.extend(find_stop_like_lists(v, f"{path}.{k}"))
    elif isinstance(obj, list) and obj and isinstance(obj[0], dict):
        for i, item in enumerate(obj[:1]):
            out.extend(find_stop_like_lists(item, f"{path}[0]"))
    return out
candidates = find_stop_like_lists(data)
if candidates:
    print(f"  Possible stop lists: {candidates}")

contents = data.get("Contents") if isinstance(data, dict) else None
if contents is None:
    print("  ERROR: No 'Contents' in response")
    print(f"  Response keys: {list(data.keys())}")
    sys.exit(1)
print(f"  Contents keys: {list(contents.keys()) if isinstance(contents, dict) else type(contents)}")

data_objects = contents.get("dataObjects")
print(f"  dataObjects type: {type(data_objects)}")

if isinstance(data_objects, dict):
    print(f"  dataObjects keys: {list(data_objects.keys())}")
    # 511 may return ScheduledStopPoint as key, or a different structure
    points = data_objects.get("ScheduledStopPoint", data_objects.get("ScheduledStopPoints", []))
    # If dataObjects is a single wrapper, look for nested list
    if not points and "id" in data_objects:
        print(f"  dataObjects sample (first 400 chars): {str(data_objects)[:400]}")
elif isinstance(data_objects, list):
    print(f"  dataObjects length: {len(data_objects)}")
    points = data_objects if data_objects else []
else:
    points = []
    print(f"  dataObjects is neither dict nor list: {data_objects is None}")

# Dump structure to find where stops actually are
if not points and data_objects is not None:
    import json
    print("  --- Full dataObjects structure (to find stops) ---")
    try:
        # If it's a dict, show each key and type of value
        if isinstance(data_objects, dict):
            for k, v in data_objects.items():
                if isinstance(v, list):
                    print(f"    {k}: list len={len(v)}")
                    if v and isinstance(v[0], dict):
                        print(f"      first item keys: {list(v[0].keys())[:8]}")
                else:
                    print(f"    {k}: {type(v).__name__} = {str(v)[:80]}")
        elif isinstance(data_objects, list):
            print(f"    list len={len(data_objects)}, first: {data_objects[0] if data_objects else None}")
    except Exception as e:
        print(f"    (dump error: {e})")

print(f"  ScheduledStopPoint count: {len(points) if isinstance(points, list) else 'N/A'}")

if points and isinstance(points, list):
    sample = points[0] if isinstance(points[0], dict) else points[0]
    print(f"  First item keys: {list(sample.keys()) if isinstance(sample, dict) else type(sample)}")
    print(f"  First 3 stops: {[(p.get('id'), p.get('Name')) for p in points[:3] if isinstance(p, dict)]}")
else:
    print("  WARNING: No stop points in response")

# --- 2. Our get_caltrain_stops() (bypass cache by calling internal fetch) ---
print("\n--- Our get_caltrain_stops() ---")
# Clear cache so we hit API
from backend import caltrain
caltrain._stops_cache = None
caltrain._stops_cache_time = 0
try:
    stops = caltrain.get_caltrain_stops()
    print(f"  Returned {len(stops)} stops")
    if stops:
        print(f"  First 3: {[(s.get('id'), s.get('Name')) for s in stops[:3]]}")
    else:
        print("  WARNING: Empty list returned")
except Exception as e:
    print(f"  ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# --- 3. Quick /stops endpoint simulation ---
print("\n--- Simulated /stops response (what frontend gets) ---")
print(f"  JSON length: {len(str(stops))} chars")
print(f"  First item: {stops[0] if stops else 'N/A'}")

# --- 4. StopMonitoring (with stopcode, then without) ---
print("\n--- 511 StopMonitoring API ---")
stop_id = stops[0]["id"] if stops else "70031"
url2 = "https://api.511.org/transit/StopMonitoring"

for label, params2 in [
    ("WITH stopcode", {"api_key": API_KEY, "agency": "CT", "stopcode": stop_id, "format": "json"}),
    ("WITHOUT stopcode", {"api_key": API_KEY, "agency": "CT", "format": "json"}),
]:
    print(f"\n  {label}:")
    try:
        r2 = requests.get(url2, params=params2)
        r2.encoding = "utf-8-sig"
        print(f"    Status: {r2.status_code}")
        if r2.status_code == 200:
            data2 = r2.json()
            delivery = data2.get("ServiceDelivery", {})
            sm = delivery.get("StopMonitoringDelivery", {})
            visits = sm.get("MonitoredStopVisit", [])
            if not visits and isinstance(sm.get("MonitoredStopVisit"), dict):
                visits = list(sm.get("MonitoredStopVisit", {}).values()) if sm.get("MonitoredStopVisit") else []
            for_our_stop = [v for v in visits if v.get("MonitoringRef") == str(stop_id)] if isinstance(visits, list) else []
            print(f"    Total visits: {len(visits) if isinstance(visits, list) else 'N/A'}, for stop {stop_id}: {len(for_our_stop)}")
            if visits and isinstance(visits, list) and len(visits) > 0:
                print(f"    First visit keys: {list(visits[0].keys())[:8]}")
            elif not visits:
                print(f"    Response top keys: {list(data2.keys())}")
                if "ServiceDelivery" in data2:
                    sd = data2["ServiceDelivery"]
                    print(f"    ServiceDelivery keys: {list(sd.keys())}")
        else:
            print(f"    Body: {r2.text[:300]}")
    except Exception as e:
        print(f"    ERROR: {e}")

# --- 5. GTFS-Realtime Trip Updates (raw) ---
print("\n--- 511 GTFS-Realtime Trip Updates ---")
stop_ids_seen = set()
try:
    from google.transit import gtfs_realtime_pb2
    r3 = requests.get(
        "https://api.511.org/transit/tripupdates",
        params={"api_key": API_KEY, "agency": "CT"},
        timeout=10,
    )
    print(f"  Status: {r3.status_code}, size: {len(r3.content)} bytes")
    if r3.status_code == 200 and r3.content:
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(r3.content)
        entities_with_tu = sum(1 for e in feed.entity if e.HasField("trip_update"))
        stop_ids_seen = set()
        for e in feed.entity:
            if e.HasField("trip_update"):
                for stu in e.trip_update.stop_time_update:
                    stop_ids_seen.add(stu.stop_id)
        print(f"  Entities with trip_update: {entities_with_tu}")
        print(f"  Unique stop_ids in feed: {len(stop_ids_seen)}")
        sample = list(stop_ids_seen)[:5] if stop_ids_seen else []
        print(f"  Sample stop_ids: {sample}")
        print(f"  Our stop {stop_id} in feed: {stop_id in stop_ids_seen}")
except Exception as e:
    print(f"  ERROR: {e}")
    import traceback
    traceback.print_exc()

# --- 5b. SIRI Stop Timetable (scheduled departures fallback) ---
print("\n--- 511 Stop Timetable (scheduled departures) ---")
try:
    r4 = requests.get(
        "https://api.511.org/transit/stoptimetable",
        params={"api_key": API_KEY, "operatorref": "CT", "monitoringref": stop_id, "format": "json"},
        timeout=10,
    )
    r4.encoding = "utf-8-sig"
    print(f"  Status: {r4.status_code}")
    if r4.status_code == 200:
        data4 = r4.json()
        sd = data4.get("Siri", {}).get("ServiceDelivery", {})
        stt = sd.get("StopTimetableDelivery", {})
        visits4 = stt.get("TimetabledStopVisit", [])
        if isinstance(visits4, dict):
            visits4 = list(visits4.values())
        print(f"  TimetabledStopVisit count: {len(visits4) if isinstance(visits4, list) else 'N/A'}")
        if visits4 and isinstance(visits4, list):
            print(f"  First visit keys: {list(visits4[0].keys())[:8]}")
except Exception as e:
    print(f"  ERROR: {e}")

# --- 6. DATA SOURCE PRIORITY (each source's response for our stop) ---
print("\n" + "=" * 60)
print("DATA SOURCE PRIORITY ORDER")
print("=" * 60)
print("""
  Priority 1: gtfs_realtime    - GTFS-Realtime Trip Updates (real-time)
  Priority 2: stop_timetable   - SIRI Stop Timetable (scheduled)
  Priority 3: stop_monitoring  - SIRI StopMonitoring (live when available)
  First non-empty source wins. UI shows: Real-time / Scheduled / Live
""")
sources = caltrain.debug_data_sources(stop_id)
winner = None
for key, visits in sources.items():
    label = key.replace("priority_1_", "1. ").replace("priority_2_", "2. ").replace("priority_3_", "3. ")
    n = len(visits) if visits else 0
    status = f"{n} visit(s)" if n else "empty"
    if n and winner is None:
        winner = key.split("_", 2)[-1]  # gtfs_realtime, stop_timetable, or stop_monitoring
    print(f"  {label}: {status}")
    if visits and len(visits) > 0:
        for i, v in enumerate(visits[:2]):
            print(f"      {i+1}. {v.get('line_ref', '?')} -> {v.get('destination', '?')} @ {v.get('expected_departure_local', '?')}")
print(f"\n  >>> WINNER (source used): {winner or 'none'}")
print("=" * 60)

# --- 7. get_next_trains (final result) ---
print("\n--- get_next_trains (final combined result) ---")
test_stops = [stop_id]
if stop_ids_seen and stop_id not in stop_ids_seen:
    test_stops.append(list(stop_ids_seen)[0])
for test_stop in test_stops:
    try:
        visits, source = caltrain.get_next_trains(test_stop, limit=5)
        print(f"  Stop {test_stop}: {len(visits)} train(s) (source: {source})")
        for i, t in enumerate(visits[:3]):
            print(f"    {i+1}. {t.get('line_ref', '?')} -> {t.get('destination', '?')} @ {t.get('expected_departure_local', '?')}")
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()

print("\n--- Done. If you see stops above, the API and parsing are OK. ---")
