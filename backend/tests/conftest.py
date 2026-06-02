import io
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import caltrain

FIXTURE_ROUTES = """route_id,agency_id,route_short_name,route_long_name,route_type
route_local,CT,Local,Local Weekday,2
route_limited,CT,Limited,Limited Weekday,2
"""

FIXTURE_TRIPS = """route_id,service_id,trip_id
route_local,weekday,local_1
route_limited,weekday,limited_1
"""

FIXTURE_STOP_TIMES = """trip_id,arrival_time,departure_time,stop_id,stop_sequence
local_1,08:00:00,08:00:00,90001,1
local_1,08:10:00,08:10:00,90002,2
local_1,08:20:00,08:20:00,90003,3
limited_1,08:00:00,08:00:00,90001,1
limited_1,08:12:00,08:12:00,90003,2
"""

STOP_A = "90001"
STOP_B = "90002"
STOP_C = "90003"


def _write_minimal_gtfs_zip(path):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("routes.txt", FIXTURE_ROUTES)
        zf.writestr("trips.txt", FIXTURE_TRIPS)
        zf.writestr("stop_times.txt", FIXTURE_STOP_TIMES)


@pytest.fixture(autouse=True)
def reset_travel_cache():
    caltrain._clear_travel_time_cache()
    yield
    caltrain._clear_travel_time_cache()


@pytest.fixture
def minimal_gtfs_zip(tmp_path):
    path = tmp_path / "minimal_gtfs.zip"
    _write_minimal_gtfs_zip(path)
    caltrain._load_travel_time_cache_from_zip_path(path)
    return path
