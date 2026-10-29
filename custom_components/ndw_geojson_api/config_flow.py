"""UI configuration for NDW charging station bounding boxes."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NDWClient, NDWError, validate_bbox
from .const import CONF_BBOX, DOMAIN


def bbox_schema(default: str = "") -> vol.Schema:
    """Build the shared setup/options form."""
    return vol.Schema({vol.Required(CONF_BBOX, default=default): str})


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
                        title=f"NDW ({bbox})", data={CONF_BBOX: bbox}
                    )
        return self.async_show_form(
            step_id="user",
            data_schema=bbox_schema(user_input[CONF_BBOX] if user_input else ""),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> NDWOptionsFlow:
        return NDWOptionsFlow()


class NDWOptionsFlow(config_entries.OptionsFlow):
    """Edit a bounding box without reinstalling the integration."""

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
                        return self.async_create_entry(title="", data={CONF_BBOX: bbox})
        default = self.config_entry.options.get(
            CONF_BBOX, self.config_entry.data[CONF_BBOX]
        )
        return self.async_show_form(
            step_id="init",
            data_schema=bbox_schema(user_input[CONF_BBOX] if user_input else default),
            errors=errors,
        )
