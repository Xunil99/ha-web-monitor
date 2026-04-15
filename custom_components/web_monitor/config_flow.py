"""Config flow for Web Monitor."""
from __future__ import annotations

from typing import Any
import uuid

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

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
