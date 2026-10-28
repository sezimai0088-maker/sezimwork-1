from bot.geo import check_zone, distance_m, twogis_link

OFFICE = dict(office_lat=42.8746, office_lon=74.5698, radius_m=100, max_accuracy_m=100)


def test_distance_zero_for_same_point():
    assert distance_m(42.8746, 74.5698, 42.8746, 74.5698) == 0


def test_distance_known_value():
    # 0.001° широты ≈ 111 м
    d = distance_m(42.8746, 74.5698, 42.8756, 74.5698)
    assert 110 < d < 112


def test_inside_zone():
    result = check_zone(42.8750, 74.5698, 15, **OFFICE)  # ~44 м
    assert result.inside
    assert not result.accuracy_too_low


def test_outside_zone():
    result = check_zone(42.8770, 74.5698, 15, **OFFICE)  # ~267 м
    assert not result.inside
    assert 260 < result.distance_m < 275


def test_edge_of_zone():
    inside = check_zone(42.87549, 74.5698, 10, **OFFICE)  # ~99 м
    outside = check_zone(42.87552, 74.5698, 10, **OFFICE)  # ~102 м
    assert inside.inside
    assert not outside.inside


def test_low_accuracy_is_rejected_even_inside():
    result = check_zone(42.8746, 74.5698, 350, **OFFICE)
    assert result.accuracy_too_low
    assert not result.inside


def test_missing_accuracy_is_allowed():
    assert check_zone(42.8746, 74.5698, None, **OFFICE).inside


def test_twogis_link_puts_longitude_first():
    link = twogis_link(42.8746, 74.5698)
    assert link == "https://2gis.kg/geo/74.569800,42.874600?m=74.569800,42.874600/17"


def test_twogis_link_trailing_slash():
    assert twogis_link(1, 2, "https://2gis.kg/").startswith("https://2gis.kg/geo/")
