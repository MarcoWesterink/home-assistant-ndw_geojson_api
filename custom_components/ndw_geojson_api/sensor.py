"""Four enabled sensors per NDW charging station."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import NDWConfigEntry, NDWCoordinator

SENSORS = (
    SensorEntityDescription(key="address", name="Address", icon="mdi:map-marker"),
    SensorEntityDescription(
        key="last_updated",
        name="Last updated",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key="total", name="Total connections", icon="mdi:ev-station"
    ),
    SensorEntityDescription(
        key="available", name="Available connections", icon="mdi:ev-plug-type2"
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: NDWConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Discover initial stations and stations appearing in later snapshots."""
    coordinator: NDWCoordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def async_discover() -> None:
        new_ids = coordinator.data.keys() - known
        entities = [
            NDWSensor(coordinator, entry.entry_id, station_id, description)
            for station_id in sorted(new_ids)
            for description in SENSORS
        ]
        known.update(new_ids)
        if entities:
            async_add_entities(entities)

    async_discover()
    entry.async_on_unload(coordinator.async_add_listener(async_discover))


class NDWSensor(CoordinatorEntity[NDWCoordinator], SensorEntity):
    """A property of a station, with stable identity across address changes."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: NDWCoordinator,
        entry_id: str,
        station_id: str,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._station_id = station_id
        self._attr_unique_id = f"{entry_id}_{station_id}_{description.key}"
        station = coordinator.data[station_id]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{station_id}")},
            name=station.address,
            manufacturer=station.properties.get("operator_name") or "NDW",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def available(self) -> bool:
        return super().available and self._station_id in self.coordinator.data

    @property
    def native_value(self) -> str | int | datetime | None:
        station = self.coordinator.data.get(self._station_id)
        if station is None:
            return None
        values: dict[str, str | int | datetime | None] = {
            "address": station.address,
            "last_updated": station.last_updated,
            "total": station.total,
            "available": station.available,
        }
        return values[self.entity_description.key]

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Keep optional details on one sensor to avoid four recorder copies."""
        if self.entity_description.key != "available":
            return None
        station = self.coordinator.data.get(self._station_id)
        if station is None:
            return None
        return {
            key: value
            for key, value in station.properties.items()
            if key not in {"address", "last_updated"}
        } | {
            "station_id": station.id,
            "longitude": station.longitude,
            "latitude": station.latitude,
        }
