"""UI configuration for NDW charging station bounding boxes."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NDWClient, NDWError, validate_bbox
from .const import (
    CONF_BBOX,
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    MIN_POLL_INTERVAL,
)


def settings_schema(
    default_bbox: str = "", default_interval: int = DEFAULT_POLL_INTERVAL
) -> vol.Schema:
    """Build the shared setup/options form."""
    return vol.Schema(
        {
            vol.Required(CONF_BBOX, default=default_bbox): str,
            vol.Required(CONF_POLL_INTERVAL, default=default_interval): vol.All(
                int, vol.Range(min=MIN_POLL_INTERVAL)
            ),
        }
    )


class NDWConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create one config entry per bounding box."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                bbox = validate_bbox(user_input[CONF_BBOX])
            except ValueError:
                errors[CONF_BBOX] = "invalid_bbox"
            else:
                if any(
                    entry.options.get(CONF_BBOX, entry.data[CONF_BBOX]) == bbox
                    for entry in self._async_current_entries()
                ):
                    return self.async_abort(reason="already_configured")
                try:
                    await NDWClient(
                        async_get_clientsession(self.hass), bbox
                    ).async_get_stations()
                except NDWError:
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(
                        title=f"NDW ({bbox})",
                        data={
                            CONF_BBOX: bbox,
                            CONF_POLL_INTERVAL: user_input[CONF_POLL_INTERVAL],
                        },
                    )
        return self.async_show_form(
            step_id="user",
            data_schema=settings_schema(
                user_input[CONF_BBOX] if user_input else "",
                user_input[CONF_POLL_INTERVAL] if user_input else DEFAULT_POLL_INTERVAL,
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> NDWOptionsFlow:
        return NDWOptionsFlow()


class NDWOptionsFlow(config_entries.OptionsFlow):
    """Edit the area and polling interval without reinstalling."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                bbox = validate_bbox(user_input[CONF_BBOX])
            except ValueError:
                errors[CONF_BBOX] = "invalid_bbox"
            else:
                if any(
                    entry.entry_id != self.config_entry.entry_id
                    and entry.options.get(CONF_BBOX, entry.data[CONF_BBOX]) == bbox
                    for entry in self.hass.config_entries.async_entries(DOMAIN)
                ):
                    errors["base"] = "already_configured"
                else:
                    try:
                        await NDWClient(
                            async_get_clientsession(self.hass), bbox
                        ).async_get_stations()
                    except NDWError:
                        errors["base"] = "cannot_connect"
                    else:
                        return self.async_create_entry(
                            title="",
                            data={
                                CONF_BBOX: bbox,
                                CONF_POLL_INTERVAL: user_input[CONF_POLL_INTERVAL],
                            },
                        )
        default = self.config_entry.options.get(
            CONF_BBOX, self.config_entry.data[CONF_BBOX]
        )
        default_interval = self.config_entry.options.get(
            CONF_POLL_INTERVAL,
            self.config_entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
        )
        return self.async_show_form(
            step_id="init",
            data_schema=settings_schema(
                user_input[CONF_BBOX] if user_input else default,
                user_input[CONF_POLL_INTERVAL] if user_input else default_interval,
            ),
            errors=errors,
        )
