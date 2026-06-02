from unittest.mock import patch

from conftest import STOP_A, STOP_B

import caltrain


def _visit(line_ref, service_label):
    return {
        "line_ref": line_ref,
        "line_name": line_ref,
        "destination": "C",
        "expected_departure": "2026-06-02T14:00:00+00:00",
        "expected_arrival": "2026-06-02T14:00:00+00:00",
        "expected_departure_local": "7:00 AM",
        "expected_arrival_local": "7:00 AM",
    }


@patch.object(caltrain, "get_next_trains")
@patch.object(caltrain, "_resolve_stop")
def test_next_trains_limited_no_travel_to_skipped_stop(mock_resolve, mock_get_trains, minimal_gtfs_zip):
    mock_resolve.side_effect = [
        (STOP_A, "San Mateo", None),
        (STOP_B, "Hayward Park", None),
    ]
    mock_get_trains.return_value = (
        [
            _visit("route_limited", "Limited"),
            _visit("route_local", "Local"),
        ],
        "gtfs_realtime",
    )

    result = caltrain.next_trains(
        STOP_A, limit=5, direction="southbound", to_stop=STOP_B
    )

    assert result["stop_id"] == STOP_A
    limited = next(t for t in result["trains"] if t["service"] == "Limited")
    local = next(t for t in result["trains"] if t["service"] == "Local")
    assert "travel_minutes" not in limited
    assert local["travel_minutes"] == 10
