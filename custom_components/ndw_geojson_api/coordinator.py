"""Shared polling for all stations in a bounding box."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import NDWClient, NDWError, Station
from .const import DEFAULT_POLL_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class NDWCoordinator(DataUpdateCoordinator[dict[str, Station]]):
    """Fetch a complete snapshot once per polling interval."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: NDWClient,
        poll_interval: int = DEFAULT_POLL_INTERVAL,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=poll_interval),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Station]:
        try:
            return await self.client.async_get_stations()
        except NDWError as err:
            raise UpdateFailed(str(err)) from err


NDWConfigEntry = ConfigEntry[NDWCoordinator]
