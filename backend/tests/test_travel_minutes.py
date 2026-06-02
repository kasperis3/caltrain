from conftest import STOP_A, STOP_B, STOP_C

import caltrain


def test_route_id_maps_to_service(minimal_gtfs_zip):
    assert caltrain._route_id_to_service["route_limited"] == "Limited"
    assert caltrain._route_id_to_service["route_local"] == "Local"


def test_get_travel_minutes_local_serves_skipped_stop(minimal_gtfs_zip):
    assert caltrain.get_travel_minutes(STOP_A, STOP_B, service="Local") == 10


def test_get_travel_minutes_limited_skips_stop(minimal_gtfs_zip):
    assert caltrain.get_travel_minutes(STOP_A, STOP_B, service="Limited") is None


def test_get_travel_minutes_limited_serves_major_stop(minimal_gtfs_zip):
    assert caltrain.get_travel_minutes(STOP_A, STOP_C, service="Limited") == 12


def test_get_travel_minutes_local_serves_major_stop(minimal_gtfs_zip):
    assert caltrain.get_travel_minutes(STOP_A, STOP_C, service="Local") == 20


def test_get_travel_minutes_without_service_returns_none(minimal_gtfs_zip):
    assert caltrain.get_travel_minutes(STOP_A, STOP_B) is None
