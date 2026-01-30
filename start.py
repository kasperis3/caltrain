"""
Run the Caltrain example: next trains at a stop.

Usage: python start.py
"""

from caltrain import get_next_trains

if __name__ == "__main__":
    stop_id = "70031"  # Bayshore Northbound; use get_caltrain_stops() to find others
    trains = get_next_trains(stop_id, limit=5)

    print(f"Next trains at stop {stop_id}:", len(trains))
    for t in trains:
        dep = t.get("expected_departure_local") or t.get("expected_arrival_local")
        print(" ", t.get("line_name") or t.get("destination"), "->", dep)
