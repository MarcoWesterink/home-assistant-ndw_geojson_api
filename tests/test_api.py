"""Client tests runnable without installing Home Assistant."""

import asyncio
import importlib
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest
from yarl import URL

# Load the client without executing the Home Assistant integration entry point.
ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "ndw_test_client"
package = ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "custom_components" / "ndw_geojson_api")]
sys.modules[PACKAGE] = package
api = importlib.import_module(f"{PACKAGE}.api")
BBOX = "5.63,52.03,5.65,52.05"
SAMPLE = json.loads((ROOT / "ndw" / "sample_response.json").read_text())


def response(payload, next_url=None):
    """Create an aiohttp-compatible response context."""
    result = MagicMock()
    result.json = AsyncMock(return_value=payload)
    result.links = {"next": {"url": URL(next_url)}} if next_url else {}
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=result)
    context.__aexit__ = AsyncMock(return_value=False)
    return context


@pytest.mark.parametrize(
    "value",
    [
        "",
        "1,2,3",
        "1,2,3,4,5",
        "nan,2,3,4",
        "1,2,inf,4",
        "5,52,4,53",
        "4,53,5,52",
        "4,52,4,53",
        "-181,0,1,1",
        "0,-91,1,1",
        "0,0,181,1",
        "0,0,1,91",
        "1e0,2,3,4",
    ],
)
def test_invalid_bbox(value):
    with pytest.raises(ValueError):
        api.validate_bbox(value)


def test_bbox_normalized():
    assert api.validate_bbox(" 4.700, 51.50,5.150,51.800 ") == "4.7,51.5,5.15,51.8"


def test_bbox_keeps_small_decimals_in_swagger_format():
    assert api.validate_bbox("-0.0,0.00000001,1,1") == "0,0.00000001,1,1"


def test_sample_stations():
    stations = [api.parse_station(feature) for feature in SAMPLE["features"]]
    assert len(stations) == 3
    assert [station.available for station in stations] == [2, 2, 1]
    assert [station.total for station in stations] == [2, 2, 2]
    assert stations[0].address == "Markiezenhof 65"
    assert stations[0].last_updated.isoformat() == "2026-10-27T17:55:32+00:00"
    assert stations[0].latitude == 52.04068
    assert stations[0].properties["availabilities"][0]["power_max"] == 11040.0
    # An API "open" value of false must not overwrite reported availability.
    assert stations[0].properties["open"] is False
    assert stations[0].available == 2


def test_aggregate_connector_groups():
    feature = deepcopy(SAMPLE["features"][0])
    feature["properties"]["availabilities"].append({"total": 3, "available": 1})
    station = api.parse_station(feature)
    assert (station.total, station.available) == (5, 3)


@pytest.mark.parametrize("value", [None, []])
def test_unknown_versus_empty_availability(value):
    feature = deepcopy(SAMPLE["features"][0])
    feature["properties"]["availabilities"] = value
    station = api.parse_station(feature)
    expected = None if value is None else 0
    assert station.total == expected
    assert station.available == expected


def test_absent_availability():
    feature = deepcopy(SAMPLE["features"][0])
    del feature["properties"]["availabilities"]
    assert api.parse_station(feature).available is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("address", None),
        ("last_updated", "invalid"),
        ("last_updated", "2026-10-29T11:46:25"),
        ("open", "true"),
        ("cpo_id", None),
        ("availabilities", [{"total": 1, "available": 2}]),
        ("availabilities", [{"total": -1, "available": 0}]),
        ("availabilities", [{"total": True, "available": 0}]),
        ("availabilities", [{}]),
        ("availabilities", {}),
    ],
)
def test_malformed_properties(field, value):
    feature = deepcopy(SAMPLE["features"][0])
    feature["properties"][field] = value
    with pytest.raises(api.NDWError):
        api.parse_station(feature)


@pytest.mark.parametrize(
    "coordinates", [None, [1], [True, 1], [181, 1], [1, float("nan")]]
)
def test_malformed_geometry(coordinates):
    feature = deepcopy(SAMPLE["features"][0])
    feature["geometry"]["coordinates"] = coordinates
    with pytest.raises(api.NDWError):
        api.parse_station(feature)


def test_paginated_snapshot():
    session = MagicMock()
    cursor = "opaque+/token=="
    next_url = str(URL(api.API_URL).with_query(bbox=BBOX, cursor=cursor))
    session.get.side_effect = [
        response(
            {"type": "FeatureCollection", "features": SAMPLE["features"][:1]}, next_url
        ),
        response({"type": "FeatureCollection", "features": SAMPLE["features"][1:]}),
    ]
    stations = asyncio.run(api.NDWClient(session, BBOX).async_get_stations())
    assert len(stations) == 3
    assert session.get.call_args_list[1].kwargs["params"] == {
        "bbox": BBOX,
        "cursor": cursor,
    }
    assert session.get.call_args_list[1].args[0] == api.API_URL


@pytest.mark.parametrize(
    "payload",
    [None, {}, {"type": "FeatureCollection", "features": {}}, {"type": "Other"}],
)
def test_invalid_collection(payload):
    session = MagicMock()
    session.get.return_value = response(payload)
    with pytest.raises(api.NDWError):
        asyncio.run(api.NDWClient(session, BBOX).async_get_stations())


@pytest.mark.parametrize(
    "next_url",
    [
        "https://example.com/features?cursor=secret",
        api.API_URL + "/unexpected?cursor=abc",
        api.API_URL + "?bbox=" + BBOX,
    ],
)
def test_invalid_pagination(next_url):
    session = MagicMock()
    session.get.return_value = response(
        {"type": "FeatureCollection", "features": []}, next_url
    )
    with pytest.raises(api.NDWError):
        asyncio.run(api.NDWClient(session, BBOX).async_get_stations())
    assert session.get.call_count == 1


def test_repeated_cursor():
    session = MagicMock()
    session.get.return_value = response(
        {"type": "FeatureCollection", "features": []},
        api.API_URL + "?cursor=abc",
    )
    with pytest.raises(api.NDWError, match="repeated"):
        asyncio.run(api.NDWClient(session, BBOX).async_get_stations())
    assert session.get.call_count == 2


def test_duplicate_station():
    session = MagicMock()
    session.get.return_value = response(
        {"type": "FeatureCollection", "features": [SAMPLE["features"][0]] * 2}
    )
    with pytest.raises(api.NDWError, match="Duplicate"):
        asyncio.run(api.NDWClient(session, BBOX).async_get_stations())


@pytest.mark.parametrize(
    "error",
    [aiohttp.ClientConnectionError("offline"), TimeoutError(), ValueError("bad JSON")],
)
def test_request_failure(error):
    session = MagicMock()
    session.get.side_effect = error
    with pytest.raises(api.NDWError, match="Unable to fetch"):
        asyncio.run(api.NDWClient(session, BBOX).async_get_stations())


def test_http_error():
    session = MagicMock()
    context = response({})
    context.__aenter__.return_value.raise_for_status.side_effect = (
        aiohttp.ClientResponseError(MagicMock(), (), status=500, message="server error")
    )
    session.get.return_value = context
    with pytest.raises(api.NDWError, match="500"):
        asyncio.run(api.NDWClient(session, BBOX).async_get_stations())


def test_second_page_failure_does_not_return_partial_snapshot():
    session = MagicMock()
    session.get.side_effect = [
        response(SAMPLE, api.API_URL + "?cursor=abc"),
        aiohttp.ClientConnectionError("second page failed"),
    ]
    with pytest.raises(api.NDWError):
        asyncio.run(api.NDWClient(session, BBOX).async_get_stations())
