"""
Next 5 trains at a stop (by ID or name). Use direction when a name has two platforms.

Usage: python start.py [stop] [direction]
  e.g. python start.py 70031
       python start.py Belmont
       python start.py "San Francisco" southbound
"""

import sys
from backend.caltrain import next_trains

if __name__ == "__main__":
    stop_input = (sys.argv[1] if len(sys.argv) > 1 else "").strip() or "70031"
    direction = (sys.argv[2] if len(sys.argv) > 2 else "").strip() or None
    result = next_trains(stop_input, limit=5, direction=direction)
    if not result["stop_id"]:
        if result.get("message"):
            print(result["message"])
        else:
            print(f"Stop not found: {stop_input!r}")
        sys.exit(1)

    label = result["stop_name"] or result["stop_id"]
    print(f"Next {len(result['trains'])} trains at {label}:")
    for t in result["trains"]:
        print(f"  {t['destination']} — {t['time']}")
