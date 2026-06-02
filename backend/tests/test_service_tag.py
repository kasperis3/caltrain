import caltrain


def test_service_tag_limited_before_local():
    assert caltrain._service_tag("Limited Weekday") == "Limited"


def test_service_tag_local():
    assert caltrain._service_tag("Local Weekday") == "Local"


def test_service_tag_express():
    assert caltrain._service_tag("Baby Bullet Weekday") == "Limited"
