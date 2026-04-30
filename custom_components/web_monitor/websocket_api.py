"""WebSocket API for Web Monitor panel."""
from __future__ import annotations

import logging

import aiohttp
import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# HA addons are reachable from HA Core via their slug as hostname.
# Fallbacks try common alternatives for different setups.
ADDON_URLS = [
    "http://web_monitor_browser:8099",      # HA Supervisor DNS (most common)
    "http://local_web_monitor_browser:8099", # Local add-on prefix
    "http://homeassistant.local:8099",       # Host IP fallback
    "http://localhost:8099",                 # Same-network fallback
]
ADDON_URL = ADDON_URLS[0]  # Will be overridden by _resolve_addon_url


def async_setup(hass: HomeAssistant) -> None:
    """Register WebSocket commands."""
    hass.data.setdefault(f"{DOMAIN}_sessions", {})

    websocket_api.async_register_command(hass, ws_start_session)
    websocket_api.async_register_command(hass, ws_screenshot)
    websocket_api.async_register_command(hass, ws_navigate)
    websocket_api.async_register_command(hass, ws_click)
    websocket_api.async_register_command(hass, ws_fill)
    websocket_api.async_register_command(hass, ws_activate_picker)
    websocket_api.async_register_command(hass, ws_get_picker_result)
    websocket_api.async_register_command(hass, ws_get_steps)
    websocket_api.async_register_command(hass, ws_save_monitor)
    websocket_api.async_register_command(hass, ws_close_session)
    websocket_api.async_register_command(hass, ws_scroll)
    websocket_api.async_register_command(hass, ws_key)
    websocket_api.async_register_command(hass, ws_pick)
    websocket_api.async_register_command(hass, ws_filter_test)
    websocket_api.async_register_command(hass, ws_select_option)


_RESOLVED_ADDON_URL: str | None = None


async def _resolve_addon_url() -> str:
    """Find which add-on URL works by probing /health."""
    global _RESOLVED_ADDON_URL
    if _RESOLVED_ADDON_URL:
        return _RESOLVED_ADDON_URL

    for candidate in ADDON_URLS:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{candidate}/health",
                    timeout=aiohttp.ClientTimeout(total=3),
                ) as resp:
                    if resp.status == 200:
                        _LOGGER.info("Web Monitor add-on reachable at %s", candidate)
                        _RESOLVED_ADDON_URL = candidate
                        return candidate
        except Exception as err:
            _LOGGER.debug("Add-on URL %s not reachable: %s", candidate, err)

    raise ConnectionError(
        "Web Monitor Browser add-on is not reachable. "
        "Make sure it's installed and running. "
        f"Tried: {', '.join(ADDON_URLS)}"
    )


async def _addon_request(method: str, path: str, json: dict = None, timeout: int = 30) -> dict:
    """Make a request to the add-on REST API."""
    base = await _resolve_addon_url()
    url = f"{base}{path}"
    async with aiohttp.ClientSession() as session:
        kwargs = {"timeout": aiohttp.ClientTimeout(total=timeout)}
        if json:
            kwargs["json"] = json
        async with getattr(session, method)(url, **kwargs) as resp:
            if resp.status == 404:
                raise ValueError("No active browser session. Start a session first.")
            # Try JSON first, fall back to text for non-JSON error responses
            try:
                data = await resp.json(content_type=None)
            except Exception:
                text = await resp.text()
                raise RuntimeError(f"HTTP {resp.status}: {text[:500]}")
            if resp.status >= 400 and isinstance(data, dict):
                err = data.get("error") or data.get("detail") or "Unknown add-on error"
                raise RuntimeError(f"HTTP {resp.status}: {err}")
            return data


@websocket_api.websocket_command({
    vol.Required("type"): "web_monitor/start_session",
    vol.Optional("url", default="about:blank"): str,
})
@websocket_api.async_response
async def ws_start_session(hass, connection, msg):
    try:
        data = await _addon_request(
            "post", "/session/start",
            json={"url": msg.get("url", "about:blank")},
            timeout=30,
        )
        hass.data[f"{DOMAIN}_sessions"][str(connection.context(msg).id)] = data.get("session_id", "default")
        connection.send_result(msg["id"], {"session_id": data.get("session_id"), "image": data.get("image")})
    except Exception as err:
        connection.send_error(msg["id"], "addon_error", f"Add-on error: {err}")


@websocket_api.websocket_command({
    vol.Required("type"): "web_monitor/screenshot",
})
@websocket_api.async_response
async def ws_screenshot(hass, connection, msg):
    session_id = hass.data[f"{DOMAIN}_sessions"].get(str(connection.context(msg).id), "default")
    try:
        data = await _addon_request("get", f"/session/{session_id}/screenshot")
        connection.send_result(msg["id"], {"image": data.get("image")})
    except Exception as err:
        connection.send_error(msg["id"], "addon_error", str(err))


@websocket_api.websocket_command({
    vol.Required("type"): "web_monitor/navigate",
    vol.Required("url"): str,
})
@websocket_api.async_response
async def ws_navigate(hass, connection, msg):
    session_id = hass.data[f"{DOMAIN}_sessions"].get(str(connection.context(msg).id), "default")
    try:
        data = await _addon_request("post", f"/session/{session_id}/navigate", json={"url": msg["url"]})
        connection.send_result(msg["id"], {"image": data.get("image")})
    except Exception as err:
        connection.send_error(msg["id"], "addon_error", str(err))


@websocket_api.websocket_command({
    vol.Required("type"): "web_monitor/click",
    vol.Required("x"): int,
    vol.Required("y"): int,
})
@websocket_api.async_response
async def ws_click(hass, connection, msg):
    session_id = hass.data[f"{DOMAIN}_sessions"].get(str(connection.context(msg).id), "default")
    try:
        data = await _addon_request("post", f"/session/{session_id}/click", json={"x": msg["x"], "y": msg["y"]})
        connection.send_result(msg["id"], {"image": data.get("image"), "element": data.get("element")})
    except Exception as err:
        connection.send_error(msg["id"], "addon_error", str(err))


@websocket_api.websocket_command({
    vol.Required("type"): "web_monitor/fill",
    vol.Required("selector"): str,
    vol.Required("value"): str,
})
@websocket_api.async_response
async def ws_fill(hass, connection, msg):
    session_id = hass.data[f"{DOMAIN}_sessions"].get(str(connection.context(msg).id), "default")
    try:
        data = await _addon_request("post", f"/session/{session_id}/fill", json={"selector": msg["selector"], "value": msg["value"]})
        connection.send_result(msg["id"], {"image": data.get("image")})
    except Exception as err:
        connection.send_error(msg["id"], "addon_error", str(err))


@websocket_api.websocket_command({
    vol.Required("type"): "web_monitor/activate_picker",
})
@websocket_api.async_response
async def ws_activate_picker(hass, connection, msg):
    session_id = hass.data[f"{DOMAIN}_sessions"].get(str(connection.context(msg).id), "default")
    try:
        data = await _addon_request("post", f"/session/{session_id}/picker/activate")
        connection.send_result(msg["id"], {"status": "picker_active"})
    except Exception as err:
        connection.send_error(msg["id"], "addon_error", str(err))


@websocket_api.websocket_command({
    vol.Required("type"): "web_monitor/get_picker_result",
})
@websocket_api.async_response
async def ws_get_picker_result(hass, connection, msg):
    session_id = hass.data[f"{DOMAIN}_sessions"].get(str(connection.context(msg).id), "default")
    try:
        data = await _addon_request("get", f"/session/{session_id}/picker/result")
        connection.send_result(msg["id"], {"result": data.get("result")})
    except Exception as err:
        connection.send_error(msg["id"], "addon_error", str(err))


@websocket_api.websocket_command({
    vol.Required("type"): "web_monitor/get_steps",
})
@websocket_api.async_response
async def ws_get_steps(hass, connection, msg):
    session_id = hass.data[f"{DOMAIN}_sessions"].get(str(connection.context(msg).id), "default")
    try:
        data = await _addon_request("get", f"/session/{session_id}/steps")
        connection.send_result(msg["id"], {"steps": data.get("steps", [])})
    except Exception as err:
        connection.send_error(msg["id"], "addon_error", str(err))


@websocket_api.websocket_command({
    vol.Required("type"): "web_monitor/save_monitor",
    vol.Required("entry_id"): str,
    vol.Required("target_selector"): str,
    vol.Optional("target_extract", default="text_content"): str,
    vol.Optional("target_attribute", default=""): str,
    vol.Optional("filter_mode", default="none"): str,
    vol.Optional("filter_pattern", default=""): str,
    vol.Optional("filter_end_pattern", default=""): str,
})
@websocket_api.async_response
async def ws_save_monitor(hass, connection, msg):
    session_id = hass.data[f"{DOMAIN}_sessions"].get(str(connection.context(msg).id), "default")
    try:
        step_data = await _addon_request("get", f"/session/{session_id}/steps")
        steps = step_data.get("steps", [])
    except Exception as err:
        connection.send_error(msg["id"], "addon_error", str(err))
        return

    entry_id = msg["entry_id"]
    entry = hass.config_entries.async_get_entry(entry_id)
    if not entry:
        connection.send_error(msg["id"], "not_found", "Config entry not found")
        return

    new_data = dict(entry.data)
    new_data["steps"] = steps
    new_data["target_selector"] = msg["target_selector"]
    new_data["target_extract"] = msg.get("target_extract", "text_content")
    if msg.get("target_attribute"):
        new_data["target_attribute"] = msg["target_attribute"]
    new_data["filter_mode"] = msg.get("filter_mode", "none")
    new_data["filter_pattern"] = msg.get("filter_pattern", "")
    new_data["filter_end_pattern"] = msg.get("filter_end_pattern", "")

    hass.config_entries.async_update_entry(entry, data=new_data)

    # Send success response immediately
    connection.send_result(msg["id"], {"status": "saved", "steps_count": len(steps)})

    # Trigger refresh in background (don't block the WS response)
    if entry_id in hass.data.get(DOMAIN, {}):
        runtime = hass.data[DOMAIN][entry_id]
        runtime["config"].update(new_data)
        try:
            hass.async_create_task(runtime["coordinator"].async_request_refresh())
        except Exception as err:
            _LOGGER.warning("Failed to schedule refresh after save: %s", err)


@websocket_api.websocket_command({
    vol.Required("type"): "web_monitor/close_session",
})
@websocket_api.async_response
async def ws_close_session(hass, connection, msg):
    session_id = hass.data[f"{DOMAIN}_sessions"].pop(str(connection.context(msg).id), "default")
    try:
        await _addon_request("delete", f"/session/{session_id}")
    except Exception:
        pass
    connection.send_result(msg["id"], {"status": "closed"})


@websocket_api.websocket_command({
    vol.Required("type"): "web_monitor/scroll",
    vol.Required("delta_y"): int,
})
@websocket_api.async_response
async def ws_scroll(hass, connection, msg):
    session_id = hass.data[f"{DOMAIN}_sessions"].get(str(connection.context(msg).id), "default")
    try:
        data = await _addon_request("post", f"/session/{session_id}/scroll", json={"delta_y": msg["delta_y"]})
        connection.send_result(msg["id"], {"image": data.get("image")})
    except Exception as err:
        connection.send_error(msg["id"], "addon_error", str(err))


@websocket_api.websocket_command({
    vol.Required("type"): "web_monitor/pick",
    vol.Required("x"): int,
    vol.Required("y"): int,
})
@websocket_api.async_response
async def ws_pick(hass, connection, msg):
    """Pick element at coordinates without clicking it."""
    session_id = hass.data[f"{DOMAIN}_sessions"].get(str(connection.context(msg).id), "default")
    try:
        data = await _addon_request("post", f"/session/{session_id}/pick", json={"x": msg["x"], "y": msg["y"]})
        connection.send_result(msg["id"], {"result": data.get("result")})
    except Exception as err:
        connection.send_error(msg["id"], "addon_error", str(err))


@websocket_api.websocket_command({
    vol.Required("type"): "web_monitor/select_option",
    vol.Required("selector"): str,
    vol.Required("value"): str,
})
@websocket_api.async_response
async def ws_select_option(hass, connection, msg):
    session_id = hass.data[f"{DOMAIN}_sessions"].get(str(connection.context(msg).id), "default")
    try:
        data = await _addon_request(
            "post", f"/session/{session_id}/select_option",
            json={"selector": msg["selector"], "value": msg["value"]},
        )
        connection.send_result(msg["id"], {"image": data.get("image")})
    except Exception as err:
        connection.send_error(msg["id"], "addon_error", str(err))


@websocket_api.websocket_command({
    vol.Required("type"): "web_monitor/filter_test",
    vol.Required("text"): str,
    vol.Required("mode"): str,
    vol.Optional("pattern", default=""): str,
    vol.Optional("end_pattern", default=""): str,
})
@websocket_api.async_response
async def ws_filter_test(hass, connection, msg):
    """Apply a filter to text and return preview. Calls add-on."""
    payload = {
        "text": msg["text"],
        "mode": msg["mode"],
        "pattern": msg.get("pattern", ""),
        "end_pattern": msg.get("end_pattern", ""),
    }
    try:
        data = await _addon_request("post", "/filter/test", json=payload)
        connection.send_result(msg["id"], {"result": data.get("result", "")})
    except Exception as err:
        connection.send_error(msg["id"], "addon_error", str(err))


@websocket_api.websocket_command({
    vol.Required("type"): "web_monitor/key",
    vol.Required("key"): str,
})
@websocket_api.async_response
async def ws_key(hass, connection, msg):
    session_id = hass.data[f"{DOMAIN}_sessions"].get(str(connection.context(msg).id), "default")
    try:
        data = await _addon_request("post", f"/session/{session_id}/key", json={"key": msg["key"]})
        connection.send_result(msg["id"], {"image": data.get("image")})
    except Exception as err:
        connection.send_error(msg["id"], "addon_error", str(err))
