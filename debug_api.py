#!/usr/bin/env python3
"""
Debug script to verify the 511 API and our parsing.
Run from project root: python3 debug_api.py

Stops are now loaded from the GTFS feed (511 NeTEx /transit/stops no longer
returns a list). This script still checks StopMonitoring and the final get_caltrain_stops().
"""

import os
import sys

# Load .env before importing caltrain
from dotenv import load_dotenv
load_dotenv()

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
import caltrain
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

# --- 4. StopMonitoring (optional, one stop) ---
print("\n--- 511 StopMonitoring API (one stop) ---")
stop_id = stops[0]["id"] if stops else "70031"
url2 = "https://api.511.org/transit/StopMonitoring"
params2 = {"api_key": API_KEY, "agency": "CT", "format": "json"}
try:
    r2 = requests.get(url2, params=params2)
    r2.encoding = "utf-8-sig"
    print(f"  Status: {r2.status_code}")
    if r2.status_code == 200:
        data2 = r2.json()
        delivery = data2.get("ServiceDelivery", {})
        sm = delivery.get("StopMonitoringDelivery", {})
        visits = sm.get("MonitoredStopVisit", [])
        for_our_stop = [v for v in visits if v.get("MonitoringRef") == str(stop_id)]
        print(f"  Total visits in feed: {len(visits)}, for stop {stop_id}: {len(for_our_stop)}")
    else:
        print(f"  Body: {r2.text[:300]}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n--- Done. If you see stops above, the API and parsing are OK. ---")
