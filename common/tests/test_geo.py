import math
import re

import pytest
from edith_common import geo
from edith_common.geo import SCENARIO_ORIGIN as O
from hypothesis import given, settings
from hypothesis import strategies as st

ENU = st.floats(min_value=-3000, max_value=3000, allow_nan=False)
UP = st.floats(min_value=-50, max_value=500, allow_nan=False)


def test_origin_to_mgrs():
    assert geo.to_mgrs(O.lat, O.lon) == "16TCK6100236799" == geo.SCENARIO_ORIGIN_MGRS


def test_origin_from_mgrs_is_within_a_metre():
    lat, lon = geo.from_mgrs("16TCK 61002 36799")
    e, n, _ = geo.lla_to_enu(lat, lon, O.alt_msl_m, O)
    assert math.hypot(e, n) < 1.0


def test_clock():
    assert geo.clock_from_bearing(62) == "2 o'clock"
    assert geo.clock_from_bearing(0) == "12 o'clock"
    assert geo.clock_from_bearing(-14) == "12 o'clock"
    assert geo.clock_from_bearing(-16) == "11 o'clock"
    assert geo.clock_from_bearing(359.9) == "12 o'clock"
    assert geo.clock_from_bearing(180) == "6 o'clock"
    assert [geo.clock_hour(h * 30) for h in range(12)] == [12, *range(1, 12)]
    assert geo.bearing_from_clock(3, 350) == 80
    assert geo.bearing_from_clock(12, 41.5) == 41.5
    with pytest.raises(ValueError):
        geo.bearing_from_clock(0, 0)


def test_wrap():
    assert geo.wrap360(-10) == 350
    assert geo.wrap360(720) == 0
    assert geo.wrap180(190) == -170
    assert geo.wrap180(-180) == -180


def test_bearing_range_geodesic():
    lat2, lon2, _ = geo.enu_to_lla(300, 400, 0, O)
    assert geo.range_m(O.lat, O.lon, lat2, lon2) == pytest.approx(500, abs=0.05)
    assert geo.bearing_deg(O.lat, O.lon, lat2, lon2) == pytest.approx(36.87, abs=0.02)
    assert geo.bearing_enu_deg(300, 400) == pytest.approx(36.8699, abs=1e-3)
    assert geo.bearing_enu_deg(-1, 0) == 270
    # Philadelphia -> Piatt County ~ 1,100 km (sanity on a long geodesic)
    assert 1.0e6 < geo.range_m(39.95, -75.16, O.lat, O.lon) < 1.2e6


def test_ce90_and_hae():
    assert geo.CE90_K == 2.146
    assert geo.sigma_from_ce90(21.46) == pytest.approx(10)
    assert geo.ce90_from_sigma(10) == pytest.approx(21.46)
    assert geo.hae_m(210, O) == pytest.approx(177)


@pytest.mark.parametrize("r,ce,label", [
    (437, None, "~450 m"), (10, None, "~50 m"), (980, None, "1.0 km"), (1234, None, "1.2 km"),
    (437, 73, "~400 m"), (437, 30, "~450 m"), (2960, None, "3.0 km"), (999, 500, "1.0 km"),
    (120, 0, "~100 m"),
])
def test_range_label(r, ce, label):
    assert geo.range_label(r, ce) == label


def test_round_range():
    assert geo.round_range_m(437) == 450
    assert geo.round_range_m(437, 120) == 450  # step 150
    assert geo.round_range_m(0) == 50


@settings(max_examples=300, deadline=None)
@given(ENU, ENU, UP)
def test_enu_lla_roundtrip(e, n, u):
    lat, lon, alt = geo.enu_to_lla(e, n, u, O)
    e2, n2, u2 = geo.lla_to_enu(lat, lon, alt, O)
    assert math.dist((e, n, u), (e2, n2, u2)) < 0.01


@settings(max_examples=300, deadline=None)
@given(ENU, ENU)
def test_enu_mgrs_enu_roundtrip(e, n):
    lat, lon, _ = geo.enu_to_lla(e, n, 0, O)
    s = geo.to_mgrs(lat, lon)
    assert re.fullmatch(r"16T[A-Z]{2}\d{10}", s)
    lat2, lon2 = geo.from_mgrs(s)
    e2, n2, _ = geo.lla_to_enu(lat2, lon2, O.alt_msl_m, O)
    assert math.hypot(e - e2, n - n2) < 1.0


@settings(max_examples=200, deadline=None)
@given(ENU, ENU)
def test_bearing_matches_enu_locally(e, n):
    if math.hypot(e, n) < 20:
        return
    lat, lon, _ = geo.enu_to_lla(e, n, 0, O)
    assert abs(geo.wrap180(geo.bearing_deg(O.lat, O.lon, lat, lon) - geo.bearing_enu_deg(e, n))) < 0.1
    assert geo.range_m(O.lat, O.lon, lat, lon) == pytest.approx(math.hypot(e, n), rel=1e-3)


@settings(max_examples=500, deadline=None)
@given(st.floats(min_value=0, max_value=50_000, allow_nan=False),
       st.one_of(st.none(), st.floats(min_value=0, max_value=800, allow_nan=False)))
def test_range_label_properties(r, ce):
    step = 50 * max(1, math.ceil(max(50.0, ce or 0.0) / 50.0 - 1e-9))
    rr = geo.round_range_m(r, ce)
    assert rr % 50 == 0 and rr % step == 0 and rr >= step
    if r >= step / 2:
        assert abs(rr - r) <= step / 2 + 1e-6
    label = geo.range_label(r, ce)
    if rr < 1000:
        assert label == f"~{rr} m"
    else:
        m = re.fullmatch(r"(\d+)\.(\d) km", label)
        assert m, label
        km = float(label.split()[0])
        assert km >= 1.0 and abs(km * 1000 - r) <= max(100, step) / 2 + 50


@settings(max_examples=300, deadline=None)
@given(st.floats(min_value=-1e4, max_value=1e4, allow_nan=False),
       st.floats(min_value=0, max_value=359.99, allow_nan=False))
def test_clock_roundtrip(rel, heading):
    h = geo.clock_hour(rel)
    assert 1 <= h <= 12
    b = geo.bearing_from_clock(h, heading)
    assert abs(geo.wrap180(b - heading - rel)) <= 15 + 1e-6
    assert geo.clock_from_bearing(rel) == f"{h} o'clock"
