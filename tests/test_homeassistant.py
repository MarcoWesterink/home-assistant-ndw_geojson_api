"""Integration lifecycle tests; require a supported Home Assistant Python."""

import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("homeassistant")

import voluptuous as vol
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ndw_geojson_api import async_remove_config_entry_device
from custom_components.ndw_geojson_api.api import NDWError, parse_station
from custom_components.ndw_geojson_api.config_flow import settings_schema
from custom_components.ndw_geojson_api.const import (
    CONF_BBOX,
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)

BBOX = "5.63,52.03,5.65,52.05"
SAMPLE = json.loads(
    (Path(__file__).resolve().parents[1] / "ndw" / "sample_response.json").read_text()
)
STATIONS = {item["id"]: parse_station(item) for item in SAMPLE["features"]}
CLIENT = "custom_components.ndw_geojson_api.api.NDWClient.async_get_stations"


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    """Permit loading the integration under test."""


async def setup_entry(hass, *, data=None, options=None):
    entry = MockConfigEntry(
        domain=DOMAIN, data=data or {CONF_BBOX: BBOX}, options=options or {}
    )
    entry.add_to_hass(hass)
    with patch(CLIENT, return_value=STATIONS):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_devices_and_four_enabled_sensors(hass):
    entry = await setup_entry(hass)
    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert len(devices) == 3
    assert len(entities) == 12
    assert all(entity.disabled_by is None for entity in entities)
    for station in STATIONS.values():

        def state(key):
            entity_id = registry.async_get_entity_id(
                "sensor", DOMAIN, f"{entry.entry_id}_{station.id}_{key}"
            )
            return hass.states.get(entity_id)

        assert state("address").state == station.address
        assert state("last_updated").state == station.last_updated.isoformat()
        assert state("total").state == "2"
        assert state("available").state == str(station.available)
        assert state("available").attributes["latitude"] == station.latitude
        assert state("available").attributes["availabilities"]


async def test_refresh_removal_discovery_recovery_and_unload(hass):
    entry = await setup_entry(hass)
    coordinator = entry.runtime_data
    feature = deepcopy(SAMPLE["features"][0])
    feature["id"] = "new-station"
    new_station = parse_station(feature)
    with patch(CLIENT, return_value={new_station.id: new_station}):
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    registry = er.async_get(hass)
    assert len(er.async_entries_for_config_entry(registry, entry.entry_id)) == 16
    removed_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_{SAMPLE['features'][0]['id']}_available"
    )
    assert hass.states.get(removed_id).state == STATE_UNAVAILABLE
    new_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_new-station_available"
    )
    with patch(CLIENT, side_effect=NDWError("offline")):
        await coordinator.async_refresh()
    assert hass.states.get(new_id).state == STATE_UNAVAILABLE
    with patch(CLIENT, return_value=STATIONS):
        await coordinator.async_refresh()
    assert hass.states.get(removed_id).state == "2"
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_config_flow_validation_and_duplicate(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_BBOX: "invalid", CONF_POLL_INTERVAL: 120}
    )
    assert result["errors"] == {CONF_BBOX: "invalid_bbox"}
    with patch(CLIENT, side_effect=NDWError("offline")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_BBOX: BBOX, CONF_POLL_INTERVAL: 120}
        )
    assert result["errors"] == {"base": "cannot_connect"}
    with (
        patch(CLIENT, return_value={}),
        patch("custom_components.ndw_geojson_api.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_BBOX: BBOX, CONF_POLL_INTERVAL: 120}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_BBOX: BBOX, CONF_POLL_INTERVAL: 120}
    duplicate = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
        data={CONF_BBOX: BBOX, CONF_POLL_INTERVAL: 60},
    )
    assert duplicate["reason"] == "already_configured"


async def test_options_validate_and_reload(hass):
    entry = await setup_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_BBOX: "bad", CONF_POLL_INTERVAL: 90}
    )
    assert result["errors"] == {CONF_BBOX: "invalid_bbox"}
    with (
        patch(CLIENT, return_value={}),
        patch.object(hass.config_entries, "async_reload", return_value=True) as reload,
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_BBOX: "4.7,51.5,5.15,51.8", CONF_POLL_INTERVAL: 90},
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_BBOX] == "4.7,51.5,5.15,51.8"
    assert entry.options[CONF_POLL_INTERVAL] == 90
    reload.assert_called_once_with(entry.entry_id)


async def test_device_removal_only_for_absent_stations(hass):
    entry = await setup_entry(hass)
    device = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)[0]
    assert not await async_remove_config_entry_device(hass, entry, device)
    with patch(CLIENT, return_value={}):
        await entry.runtime_data.async_refresh()
    assert await async_remove_config_entry_device(hass, entry, device)


async def test_options_reject_duplicate_and_unreachable_area(hass):
    entry = await setup_entry(hass)
    other_bbox = "4.7,51.5,5.15,51.8"
    other = MockConfigEntry(domain=DOMAIN, data={CONF_BBOX: other_bbox})
    other.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_BBOX: other_bbox, CONF_POLL_INTERVAL: 120}
    )
    assert result["errors"] == {"base": "already_configured"}
    with patch(CLIENT, side_effect=NDWError("offline")):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_BBOX: BBOX, CONF_POLL_INTERVAL: 120}
        )
    assert result["errors"] == {"base": "cannot_connect"}
    assert entry.options == {}


@pytest.mark.parametrize("interval", [60, 90, 300, 3600])
def test_poll_interval_schema_accepts_whole_seconds(interval):
    assert (
        settings_schema()(
            {
                CONF_BBOX: BBOX,
                CONF_POLL_INTERVAL: interval,
            }
        )[CONF_POLL_INTERVAL]
        == interval
    )


@pytest.mark.parametrize("interval", [0, -1, 59, 60.5, "120", True, None])
def test_poll_interval_schema_rejects_invalid_values(interval):
    with pytest.raises(vol.Invalid):
        settings_schema()({CONF_BBOX: BBOX, CONF_POLL_INTERVAL: interval})


@pytest.mark.parametrize(
    ("data", "options", "expected"),
    [
        ({CONF_BBOX: BBOX}, {}, DEFAULT_POLL_INTERVAL),
        ({CONF_BBOX: BBOX, CONF_POLL_INTERVAL: 120}, {}, 120),
        (
            {CONF_BBOX: BBOX, CONF_POLL_INTERVAL: 120},
            {CONF_POLL_INTERVAL: 60},
            60,
        ),
    ],
)
async def test_poll_interval_runtime_and_options_default(hass, data, options, expected):
    entry = await setup_entry(hass, data=data, options=options)
    assert entry.runtime_data.update_interval == timedelta(seconds=expected)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["data_schema"]({CONF_BBOX: BBOX})[CONF_POLL_INTERVAL] == expected


async def test_changing_only_poll_interval_reloads_with_new_interval(hass):
    entry = await setup_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    with patch(CLIENT, return_value=STATIONS):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_BBOX: BBOX, CONF_POLL_INTERVAL: 60}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.runtime_data.update_interval == timedelta(seconds=60)
