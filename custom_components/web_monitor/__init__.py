"""The Web Monitor integration."""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.helpers import config_validation as cv

from .browser import BrowserWrapper
from .const import (
    CONF_HISTORY_DAYS,
    CONF_STEPS,
    CONF_TARGET_EXTRACT,
    CONF_TARGET_SELECTOR,
    DEFAULT_HISTORY_DAYS,
    DOMAIN,
)
from .coordinator import WebMonitorCoordinator
from .history import HistoryStore

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def _ensure_chromium_installed(hass: HomeAssistant) -> None:
    """Ensure Playwright's Chromium browser is installed."""
    if hass.data.get(f"{DOMAIN}_chromium_checked"):
        return

    def _check_and_install():
        """Check for Chromium and install if missing (runs in executor)."""
        try:
            # Check if chromium is already installed
            result = subprocess.run(
                ["python3", "-m", "playwright", "install", "--dry-run", "chromium"],
                capture_output=True, text=True, timeout=30,
            )
            if "is already installed" in result.stdout:
                _LOGGER.debug("Playwright Chromium already installed")
                return

            # Install chromium with system deps
            _LOGGER.info("Installing Playwright Chromium browser (first run, ~150MB download)...")
            subprocess.run(
                ["python3", "-m", "playwright", "install", "chromium"],
                capture_output=True, text=True, timeout=600,
            )
            _LOGGER.info("Playwright Chromium installed successfully")
        except FileNotFoundError:
            # python3 not in PATH, try playwright directly
            try:
                subprocess.run(
                    ["playwright", "install", "chromium"],
                    capture_output=True, text=True, timeout=600,
                )
                _LOGGER.info("Playwright Chromium installed successfully")
            except Exception as err:
                _LOGGER.error("Failed to install Playwright Chromium: %s", err)
        except Exception as err:
            _LOGGER.error("Failed to install Playwright Chromium: %s", err)

    await hass.async_add_executor_job(_check_and_install)
    hass.data[f"{DOMAIN}_chromium_checked"] = True


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Web Monitor component."""
    hass.data.setdefault(DOMAIN, {})

    from . import websocket_api as ws_api
    ws_api.async_setup(hass)

    # Install Chromium in background (don't block setup)
    hass.async_create_task(_ensure_chromium_installed(hass))

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Web Monitor from a config entry."""
    storage_dir = hass.config.path(f"web_monitor/{entry.entry_id}")
    os.makedirs(storage_dir, exist_ok=True)

    browser = BrowserWrapper(storage_dir)

    db_path = os.path.join(storage_dir, "history.db")
    history = HistoryStore(db_path)
    await history.async_setup()

    config = dict(entry.data)

    coordinator = WebMonitorCoordinator(
        hass, config, entry.entry_id, browser, history
    )

    # Only do first refresh if steps are configured
    if config.get(CONF_STEPS):
        await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = {
        "coordinator": coordinator,
        "browser": browser,
        "history": history,
        "config": config,
    }

    hass.data[DOMAIN][entry.entry_id] = entry.runtime_data

    # Register services (once)
    if not hass.services.has_service(DOMAIN, "refresh"):
        _register_services(hass)

    # Register panel (once)
    await _async_register_panel(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        runtime = hass.data[DOMAIN].pop(entry.entry_id)
        await runtime["history"].async_close()
    return unload_ok


def _register_services(hass: HomeAssistant) -> None:
    """Register integration services."""

    async def handle_refresh(call: ServiceCall) -> None:
        monitor_id = call.data["monitor_id"]
        if monitor_id in hass.data[DOMAIN]:
            coordinator = hass.data[DOMAIN][monitor_id]["coordinator"]
            await coordinator.async_request_refresh()

    async def handle_get_history(call: ServiceCall) -> ServiceResponse:
        monitor_id = call.data["monitor_id"]
        limit = call.data.get("limit", 100)
        if monitor_id in hass.data[DOMAIN]:
            history = hass.data[DOMAIN][monitor_id]["history"]
            readings = await history.get_readings(monitor_id, limit=limit)
            return {"readings": readings}
        return {"readings": []}

    async def handle_clear_history(call: ServiceCall) -> None:
        monitor_id = call.data["monitor_id"]
        if monitor_id in hass.data[DOMAIN]:
            history = hass.data[DOMAIN][monitor_id]["history"]
            await history.clear_readings(monitor_id)

    MONITOR_ID_SCHEMA = vol.Schema({vol.Required("monitor_id"): cv.string})
    HISTORY_SCHEMA = vol.Schema({
        vol.Required("monitor_id"): cv.string,
        vol.Optional("limit", default=100): vol.All(int, vol.Range(min=1)),
    })

    hass.services.async_register(DOMAIN, "refresh", handle_refresh, schema=MONITOR_ID_SCHEMA)
    hass.services.async_register(
        DOMAIN, "get_history", handle_get_history,
        schema=HISTORY_SCHEMA, supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(DOMAIN, "clear_history", handle_clear_history, schema=MONITOR_ID_SCHEMA)


async def _async_register_panel(hass: HomeAssistant) -> None:
    """Register the Web Monitor sidebar panel."""
    from homeassistant.components import panel_custom
    from homeassistant.components.http import StaticPathConfig

    if DOMAIN in hass.data.get("frontend_panels", {}):
        return

    panel_dir = os.path.join(os.path.dirname(__file__), "frontend")
    panel_url = f"/{DOMAIN}_panel"

    await hass.http.async_register_static_paths(
        [StaticPathConfig(panel_url, panel_dir, cache_headers=False)]
    )

    await panel_custom.async_register_panel(
        hass,
        webcomponent_name="web-monitor-panel",
        frontend_url_path=DOMAIN,
        sidebar_title="Web Monitor",
        sidebar_icon="mdi:web-sync",
        module_url=f"{panel_url}/web-monitor-panel.js",
        embed_iframe=False,
        require_admin=False,
    )
