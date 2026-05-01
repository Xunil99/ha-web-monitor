"""Config flow for Web Monitor."""
from __future__ import annotations

from typing import Any
import uuid

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback

from .const import (
    CONF_HISTORY_DAYS,
    CONF_INTERVAL,
    CONF_MONITOR_NAME,
    CONF_PERSIST_SESSION,
    CONF_SAVE_SCREENSHOTS,
    CONF_TIMEOUT,
    DEFAULT_HISTORY_DAYS,
    DEFAULT_INTERVAL,
    DEFAULT_SAVE_SCREENSHOTS,
    DEFAULT_PERSIST_SESSION,
    DEFAULT_TIMEOUT,
    DOMAIN,
)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MONITOR_NAME): str,
        vol.Optional(CONF_INTERVAL, default=DEFAULT_INTERVAL): vol.All(
            int, vol.Range(min=60)
        ),
        vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.All(
            int, vol.Range(min=10, max=300)
        ),
        vol.Optional(
            CONF_SAVE_SCREENSHOTS, default=DEFAULT_SAVE_SCREENSHOTS
        ): bool,
        vol.Optional(
            CONF_PERSIST_SESSION, default=DEFAULT_PERSIST_SESSION
        ): bool,
        vol.Optional(
            CONF_HISTORY_DAYS, default=DEFAULT_HISTORY_DAYS
        ): vol.All(int, vol.Range(min=1)),
    }
)


class WebMonitorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Web Monitor."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial config step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            unique_id = str(uuid.uuid4())
            await self.async_set_unique_id(unique_id)

            return self.async_create_entry(
                title=user_input[CONF_MONITOR_NAME],
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return WebMonitorOptionsFlow(config_entry)


class WebMonitorOptionsFlow(OptionsFlow):
    """Allow changing interval/timeout/etc. after the monitor is created."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit existing monitor settings."""
        if user_input is not None:
            # Merge new options into entry.data so the coordinator picks them up
            new_data = dict(self._entry.data)
            new_data.update(user_input)
            self.hass.config_entries.async_update_entry(self._entry, data=new_data)

            # Trigger reload so the coordinator uses the new interval
            await self.hass.config_entries.async_reload(self._entry.entry_id)

            return self.async_create_entry(title="", data={})

        current = self._entry.data
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_INTERVAL,
                    default=current.get(CONF_INTERVAL, DEFAULT_INTERVAL),
                ): vol.All(int, vol.Range(min=60)),
                vol.Required(
                    CONF_TIMEOUT,
                    default=current.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
                ): vol.All(int, vol.Range(min=10, max=300)),
                vol.Required(
                    CONF_SAVE_SCREENSHOTS,
                    default=current.get(CONF_SAVE_SCREENSHOTS, DEFAULT_SAVE_SCREENSHOTS),
                ): bool,
                vol.Required(
                    CONF_PERSIST_SESSION,
                    default=current.get(CONF_PERSIST_SESSION, DEFAULT_PERSIST_SESSION),
                ): bool,
                vol.Required(
                    CONF_HISTORY_DAYS,
                    default=current.get(CONF_HISTORY_DAYS, DEFAULT_HISTORY_DAYS),
                ): vol.All(int, vol.Range(min=1)),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
