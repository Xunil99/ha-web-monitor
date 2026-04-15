"""WebSocket API for Web Monitor panel."""
from __future__ import annotations

import asyncio
import base64
import logging

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SELECTOR_JS = """
(element) => {
    const parts = [];
    let el = element;
    while (el && el.nodeType === 1) {
        if (el.id) {
            parts.unshift('#' + CSS.escape(el.id));
            break;
        }
        let sibling = el, nth = 1;
        while ((sibling = sibling.previousElementSibling)) {
            if (sibling.tagName === el.tagName) nth++;
        }
        const tag = el.tagName.toLowerCase();
        parts.unshift(nth > 1 ? `${tag}:nth-of-type(${nth})` : tag);
        el = el.parentElement;
    }
    return parts.join(' > ');
}
"""

PICKER_JS = """
() => {
    if (window.__wmPickerActive) return;
    window.__wmPickerActive = true;
    window.__wmPickerResult = null;

    const overlay = document.createElement('div');
    overlay.id = '__wm_overlay';
    overlay.style.cssText = 'position:fixed;pointer-events:none;border:2px solid #4285f4;background:rgba(66,133,244,0.1);z-index:99999;transition:all 0.05s;display:none;';
    document.body.appendChild(overlay);

    const handler = (e) => {
        const rect = e.target.getBoundingClientRect();
        overlay.style.display = 'block';
        overlay.style.top = rect.top + 'px';
        overlay.style.left = rect.left + 'px';
        overlay.style.width = rect.width + 'px';
        overlay.style.height = rect.height + 'px';
    };

    const clickHandler = (e) => {
        e.preventDefault();
        e.stopPropagation();
        const el = e.target;
        window.__wmPickerResult = {
            selector: (""" + SELECTOR_JS + """)(el),
            text: el.textContent?.trim()?.substring(0, 200) || '',
            tag: el.tagName.toLowerCase(),
            rect: el.getBoundingClientRect().toJSON(),
        };
        overlay.remove();
        document.removeEventListener('mousemove', handler, true);
        document.removeEventListener('click', clickHandler, true);
        window.__wmPickerActive = false;
    };

    document.addEventListener('mousemove', handler, true);
    document.addEventListener('click', clickHandler, true);
}
"""


class BrowserSession:
    """Manages a live Playwright session for the panel."""

    def __init__(self) -> None:
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._steps: list[dict] = []

    async def start(self, url: str = "about:blank") -> None:
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=True,
            args=["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 720}
        )
        self._page = await self._context.new_page()
        if url != "about:blank":
            await self._page.goto(url, wait_until="networkidle")
            self._steps.append({"action": "goto", "url": url})

    async def screenshot_b64(self) -> str:
        png = await self._page.screenshot(full_page=False)
        return base64.b64encode(png).decode()

    async def navigate(self, url: str) -> None:
        await self._page.goto(url, wait_until="networkidle")
        self._steps.append({"action": "goto", "url": url})

    async def click(self, x: int, y: int) -> dict:
        selector_info = await self._page.evaluate(f"""() => {{
            const el = document.elementFromPoint({x}, {y});
            if (!el) return null;
            return {{
                selector: ({SELECTOR_JS})(el),
                tag: el.tagName.toLowerCase(),
                text: el.textContent?.trim()?.substring(0, 100) || '',
            }};
        }}""")

        await self._page.mouse.click(x, y)
        try:
            await self._page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

        if selector_info:
            self._steps.append({"action": "click", "selector": selector_info["selector"]})

        return selector_info or {}

    async def fill(self, selector: str, value: str) -> None:
        await self._page.fill(selector, value)
        self._steps.append({"action": "fill", "selector": selector, "value": value})

    async def type_text(self, text: str) -> None:
        await self._page.keyboard.type(text)

    async def activate_picker(self) -> None:
        await self._page.evaluate(PICKER_JS)

    async def get_picker_result(self) -> dict | None:
        return await self._page.evaluate("window.__wmPickerResult")

    async def get_element_text(self, selector: str) -> str | None:
        try:
            el = await self._page.wait_for_selector(selector, timeout=5000)
            return await el.text_content()
        except Exception:
            return None

    @property
    def steps(self) -> list[dict]:
        return list(self._steps)

    def clear_steps(self) -> None:
        self._steps.clear()

    async def close(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        self._browser = None
        self._pw = None


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


@websocket_api.websocket_command({
    vol.Required("type"): "web_monitor/start_session",
    vol.Optional("url", default="about:blank"): str,
})
@websocket_api.async_response
async def ws_start_session(hass, connection, msg):
    sessions = hass.data[f"{DOMAIN}_sessions"]
    session_id = str(connection.context(msg).id)

    if session_id in sessions:
        await sessions[session_id].close()

    session = BrowserSession()
    await session.start(msg.get("url", "about:blank"))
    sessions[session_id] = session
    connection.send_result(msg["id"], {"session_id": session_id})


@websocket_api.websocket_command({
    vol.Required("type"): "web_monitor/screenshot",
})
@websocket_api.async_response
async def ws_screenshot(hass, connection, msg):
    sessions = hass.data[f"{DOMAIN}_sessions"]
    session_id = str(connection.context(msg).id)
    session = sessions.get(session_id)
    if not session:
        connection.send_error(msg["id"], "no_session", "No active browser session")
        return
    b64 = await session.screenshot_b64()
    connection.send_result(msg["id"], {"image": b64})


@websocket_api.websocket_command({
    vol.Required("type"): "web_monitor/navigate",
    vol.Required("url"): str,
})
@websocket_api.async_response
async def ws_navigate(hass, connection, msg):
    sessions = hass.data[f"{DOMAIN}_sessions"]
    session_id = str(connection.context(msg).id)
    session = sessions.get(session_id)
    if not session:
        connection.send_error(msg["id"], "no_session", "No active browser session")
        return
    await session.navigate(msg["url"])
    b64 = await session.screenshot_b64()
    connection.send_result(msg["id"], {"image": b64})


@websocket_api.websocket_command({
    vol.Required("type"): "web_monitor/click",
    vol.Required("x"): int,
    vol.Required("y"): int,
})
@websocket_api.async_response
async def ws_click(hass, connection, msg):
    sessions = hass.data[f"{DOMAIN}_sessions"]
    session_id = str(connection.context(msg).id)
    session = sessions.get(session_id)
    if not session:
        connection.send_error(msg["id"], "no_session", "No active browser session")
        return
    info = await session.click(msg["x"], msg["y"])
    b64 = await session.screenshot_b64()
    connection.send_result(msg["id"], {"image": b64, "element": info})


@websocket_api.websocket_command({
    vol.Required("type"): "web_monitor/fill",
    vol.Required("selector"): str,
    vol.Required("value"): str,
})
@websocket_api.async_response
async def ws_fill(hass, connection, msg):
    sessions = hass.data[f"{DOMAIN}_sessions"]
    session_id = str(connection.context(msg).id)
    session = sessions.get(session_id)
    if not session:
        connection.send_error(msg["id"], "no_session", "No active browser session")
        return
    await session.fill(msg["selector"], msg["value"])
    b64 = await session.screenshot_b64()
    connection.send_result(msg["id"], {"image": b64})


@websocket_api.websocket_command({
    vol.Required("type"): "web_monitor/activate_picker",
})
@websocket_api.async_response
async def ws_activate_picker(hass, connection, msg):
    sessions = hass.data[f"{DOMAIN}_sessions"]
    session_id = str(connection.context(msg).id)
    session = sessions.get(session_id)
    if not session:
        connection.send_error(msg["id"], "no_session", "No active browser session")
        return
    await session.activate_picker()
    connection.send_result(msg["id"], {"status": "picker_active"})


@websocket_api.websocket_command({
    vol.Required("type"): "web_monitor/get_picker_result",
})
@websocket_api.async_response
async def ws_get_picker_result(hass, connection, msg):
    sessions = hass.data[f"{DOMAIN}_sessions"]
    session_id = str(connection.context(msg).id)
    session = sessions.get(session_id)
    if not session:
        connection.send_error(msg["id"], "no_session", "No active browser session")
        return
    result = await session.get_picker_result()
    connection.send_result(msg["id"], {"result": result})


@websocket_api.websocket_command({
    vol.Required("type"): "web_monitor/get_steps",
})
@websocket_api.async_response
async def ws_get_steps(hass, connection, msg):
    sessions = hass.data[f"{DOMAIN}_sessions"]
    session_id = str(connection.context(msg).id)
    session = sessions.get(session_id)
    if not session:
        connection.send_error(msg["id"], "no_session", "No active browser session")
        return
    connection.send_result(msg["id"], {"steps": session.steps})


@websocket_api.websocket_command({
    vol.Required("type"): "web_monitor/save_monitor",
    vol.Required("entry_id"): str,
    vol.Required("target_selector"): str,
    vol.Optional("target_extract", default="text_content"): str,
    vol.Optional("target_attribute", default=""): str,
})
@websocket_api.async_response
async def ws_save_monitor(hass, connection, msg):
    """Save the recorded steps and target to the config entry."""
    sessions = hass.data[f"{DOMAIN}_sessions"]
    session_id = str(connection.context(msg).id)
    session = sessions.get(session_id)
    if not session:
        connection.send_error(msg["id"], "no_session", "No active browser session")
        return

    entry_id = msg["entry_id"]
    entry = hass.config_entries.async_get_entry(entry_id)
    if not entry:
        connection.send_error(msg["id"], "not_found", "Config entry not found")
        return

    new_data = dict(entry.data)
    new_data["steps"] = session.steps
    new_data["target_selector"] = msg["target_selector"]
    new_data["target_extract"] = msg.get("target_extract", "text_content")
    if msg.get("target_attribute"):
        new_data["target_attribute"] = msg["target_attribute"]

    hass.config_entries.async_update_entry(entry, data=new_data)

    if entry_id in hass.data.get(DOMAIN, {}):
        runtime = hass.data[DOMAIN][entry_id]
        runtime["config"].update(new_data)
        await runtime["coordinator"].async_request_refresh()

    connection.send_result(msg["id"], {"status": "saved", "steps_count": len(session.steps)})


@websocket_api.websocket_command({
    vol.Required("type"): "web_monitor/close_session",
})
@websocket_api.async_response
async def ws_close_session(hass, connection, msg):
    sessions = hass.data[f"{DOMAIN}_sessions"]
    session_id = str(connection.context(msg).id)
    session = sessions.pop(session_id, None)
    if session:
        await session.close()
    connection.send_result(msg["id"], {"status": "closed"})
