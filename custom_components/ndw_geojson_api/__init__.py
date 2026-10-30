"""NDW Charging Stations integration."""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntry

from .api import NDWClient
from .const import CONF_BBOX, CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL, DOMAIN
from .coordinator import NDWConfigEntry, NDWCoordinator

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: NDWConfigEntry) -> bool:
    """Set up a bounding box and its shared coordinator."""
    bbox = entry.options.get(CONF_BBOX, entry.data[CONF_BBOX])
    poll_interval = entry.options.get(
        CONF_POLL_INTERVAL, entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
    )
    coordinator = NDWCoordinator(
        hass, NDWClient(async_get_clientsession(hass), bbox), poll_interval
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: NDWConfigEntry) -> bool:
    """Unload the sensors and their listeners."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(hass: HomeAssistant, entry: NDWConfigEntry) -> None:
    """Apply updated bounding box and polling options."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: NDWConfigEntry, device_entry: DeviceEntry
) -> bool:
    """Allow manual removal only for stations no longer in the area."""
    coordinator = config_entry.runtime_data
    active = {
        (DOMAIN, f"{config_entry.entry_id}_{station_id}")
        for station_id in coordinator.data
    }
    return not bool(device_entry.identifiers & active)
