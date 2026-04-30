"""Web Monitor Browser Add-on — FastAPI server wrapping Playwright."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger(__name__)


def normalize_url(url: str) -> str:
    """Prepend https:// if URL has no scheme."""
    if not url or url == "about:blank":
        return url
    if url.startswith(("http://", "https://", "about:", "file://")):
        return url
    return "https://" + url

# CSS selector generator JS
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


# --- Pydantic models ---

class StepModel(BaseModel):
    action: str
    url: str | None = None
    selector: str | None = None
    value: str | None = None

class TargetModel(BaseModel):
    selector: str
    extract: str = "text_content"
    attribute: str | None = None
    # Text filter to extract only part of the value:
    # - "none" (default): full text
    # - "regex": filter_pattern is a regex; first capture group (or whole match) is returned
    # - "before": return text BEFORE filter_pattern
    # - "after": return text AFTER filter_pattern
    # - "between": return text between filter_pattern and filter_end_pattern
    filter_mode: str = "none"
    filter_pattern: str | None = None
    filter_end_pattern: str | None = None


def apply_text_filter(text: str | None, mode: str, pattern: str | None, end_pattern: str | None) -> str | None:
    """Apply a text filter to the extracted value."""
    if text is None or not mode or mode == "none" or not pattern:
        return text
    import re
    try:
        if mode == "regex":
            m = re.search(pattern, text)
            if not m:
                return text
            return m.group(1) if m.groups() else m.group(0)
        elif mode == "before":
            idx = text.find(pattern)
            return text[:idx] if idx >= 0 else text
        elif mode == "after":
            idx = text.find(pattern)
            return text[idx + len(pattern):] if idx >= 0 else text
        elif mode == "between":
            if not end_pattern:
                return text
            start = text.find(pattern)
            if start < 0:
                return text
            start += len(pattern)
            end = text.find(end_pattern, start)
            return text[start:end] if end >= 0 else text[start:]
    except Exception as err:
        _LOGGER.warning("Filter failed (%s): %s", mode, err)
    return text

class ScrapeRequest(BaseModel):
    steps: list[StepModel]
    target: TargetModel
    timeout: int = 60
    monitor_id: str = "default"
    persist_session: bool = True
    save_screenshot: bool = False

class NavigateRequest(BaseModel):
    url: str

class ClickRequest(BaseModel):
    x: int
    y: int

class FillRequest(BaseModel):
    selector: str
    value: str

class SessionStartRequest(BaseModel):
    url: str = "about:blank"


# --- Browser session manager ---

class BrowserSession:
    def __init__(self):
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._steps: list[dict] = []

    async def start(self, url: str = "about:blank"):
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()

        # Try playwright-managed chromium first, fall back to system chromium
        launch_args = {
            "headless": True,
            "args": ["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"],
        }
        system_chromium = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH")
        if system_chromium and os.path.exists(system_chromium):
            launch_args["executable_path"] = system_chromium

        self._browser = await self._pw.chromium.launch(**launch_args)
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 720}
        )
        self._page = await self._context.new_page()
        url = normalize_url(url)
        if url != "about:blank":
            await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
            self._steps.append({"action": "goto", "url": url})

    async def screenshot_b64(self) -> str:
        png = await self._page.screenshot(full_page=False)
        return base64.b64encode(png).decode()

    async def navigate(self, url: str):
        url = normalize_url(url)
        await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
        self._steps.append({"action": "goto", "url": url})

    async def scroll(self, delta_y: int):
        """Scroll the page by delta_y pixels."""
        await self._page.mouse.wheel(0, delta_y)

    async def key_press(self, key: str):
        """Press a keyboard key (e.g. 'PageDown', 'Tab', 'Enter')."""
        await self._page.keyboard.press(key)

    async def click(self, x: int, y: int) -> dict:
        # Determine what kind of element is at (x, y) BEFORE clicking,
        # so we can give the frontend hints (e.g. options for <select>)
        element_info = await self._page.evaluate(f"""() => {{
            const el = document.elementFromPoint({x}, {y});
            if (!el) return null;
            // Walk up to find the closest meaningful element (input, select, button, etc.)
            let target = el;
            const walkUp = el.closest('select, input, textarea, button, a');
            if (walkUp) target = walkUp;
            const info = {{
                selector: ({SELECTOR_JS})(target),
                tag: target.tagName.toLowerCase(),
                type: (target.getAttribute('type') || '').toLowerCase(),
                text: target.textContent?.trim()?.substring(0, 100) || '',
                value: target.value !== undefined ? String(target.value).substring(0, 100) : null,
            }};
            // For <select> elements, return the list of options
            if (target.tagName.toLowerCase() === 'select') {{
                info.options = Array.from(target.options).map(o => ({{
                    value: o.value,
                    label: o.textContent?.trim() || o.value,
                    selected: o.selected,
                }}));
                info.is_select = true;
            }}
            // For checkboxes/radios, indicate current state
            if (target.tagName.toLowerCase() === 'input' && (info.type === 'checkbox' || info.type === 'radio')) {{
                info.checked = target.checked;
            }}
            return info;
        }}""")

        # If it's a native <select>, don't click (dropdown won't render in headless).
        # Just return the options; the frontend will let the user pick.
        if element_info and element_info.get("is_select"):
            return element_info

        await self._page.mouse.click(x, y)
        try:
            await self._page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass
        if element_info:
            self._steps.append({"action": "click", "selector": element_info["selector"]})
        return element_info or {}

    async def select_option(self, selector: str, value: str) -> None:
        """Select an option in a <select> element."""
        await self._page.select_option(selector, value)
        self._steps.append({"action": "select", "selector": selector, "value": value})

    async def fill(self, selector: str, value: str):
        await self._page.fill(selector, value)
        self._steps.append({"action": "fill", "selector": selector, "value": value})

    async def activate_picker(self):
        # Picker is frontend-state only; backend just needs to be able to
        # query element-at-point on demand. No JS injection needed.
        return None

    async def get_picker_result(self) -> dict | None:
        # Legacy endpoint - kept for compatibility but unused in v0.3+
        return None

    async def pick_element_at(self, x: int, y: int) -> dict | None:
        """Return info about the element at the given viewport coordinates."""
        return await self._page.evaluate(f"""() => {{
            const el = document.elementFromPoint({x}, {y});
            if (!el) return null;
            return {{
                selector: ({SELECTOR_JS})(el),
                tag: el.tagName.toLowerCase(),
                text: el.textContent?.trim()?.substring(0, 200) || '',
                rect: el.getBoundingClientRect().toJSON(),
            }};
        }}""")

    @property
    def steps(self) -> list[dict]:
        return list(self._steps)

    def clear_steps(self):
        self._steps.clear()

    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        self._browser = None
        self._pw = None


# --- Global state ---

sessions: dict[str, BrowserSession] = {}
STORAGE_DIR = os.environ.get("STORAGE_DIR", "/config/web_monitor")
os.makedirs(STORAGE_DIR, exist_ok=True)


# --- FastAPI app ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    _LOGGER.info("Web Monitor Browser service starting")
    yield
    _LOGGER.info("Shutting down, closing browser sessions...")
    for sid, session in sessions.items():
        await session.close()
    sessions.clear()

app = FastAPI(title="Web Monitor Browser", lifespan=lifespan)


# Catch-all exception handler: return JSON with traceback instead of plain-text 500
import traceback as _traceback
from fastapi import Request
from fastapi.responses import JSONResponse


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    tb = _traceback.format_exc()
    _LOGGER.error("Unhandled error in %s %s:\n%s", request.method, request.url.path, tb)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": str(exc),
            "error_type": exc.__class__.__name__,
            "traceback": tb,
        },
    )


@app.get("/")
async def root():
    return {
        "service": "Web Monitor Browser",
        "version": "0.1.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
            "scrape": "POST /scrape",
            "session": "POST /session/start",
        },
    }


@app.get("/health")
async def health():
    return {"status": "ok", "sessions": len(sessions)}


@app.post("/session/start")
async def start_session(req: SessionStartRequest, session_id: str = "default"):
    if session_id in sessions:
        await sessions[session_id].close()
    session = BrowserSession()
    await session.start(req.url)
    sessions[session_id] = session
    screenshot = await session.screenshot_b64() if req.url != "about:blank" else None
    return {"session_id": session_id, "image": screenshot}


@app.post("/session/{session_id}/navigate")
async def navigate(session_id: str, req: NavigateRequest):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "No active session")
    await session.navigate(req.url)
    image = await session.screenshot_b64()
    return {"image": image, "steps": session.steps}


@app.post("/session/{session_id}/click")
async def click(session_id: str, req: ClickRequest):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "No active session")
    info = await session.click(req.x, req.y)
    image = await session.screenshot_b64()
    return {"image": image, "element": info, "steps": session.steps}


@app.post("/session/{session_id}/fill")
async def fill(session_id: str, req: FillRequest):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "No active session")
    await session.fill(req.selector, req.value)
    image = await session.screenshot_b64()
    return {"image": image, "steps": session.steps}


class SelectOptionRequest(BaseModel):
    selector: str
    value: str


@app.post("/session/{session_id}/select_option")
async def select_option(session_id: str, req: SelectOptionRequest):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "No active session")
    await session.select_option(req.selector, req.value)
    image = await session.screenshot_b64()
    return {"image": image, "steps": session.steps}


class ScrollRequest(BaseModel):
    delta_y: int


@app.post("/session/{session_id}/scroll")
async def scroll(session_id: str, req: ScrollRequest):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "No active session")
    await session.scroll(req.delta_y)
    image = await session.screenshot_b64()
    return {"image": image}


class KeyRequest(BaseModel):
    key: str


@app.post("/session/{session_id}/key")
async def key_press(session_id: str, req: KeyRequest):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "No active session")
    await session.key_press(req.key)
    image = await session.screenshot_b64()
    return {"image": image}


@app.get("/session/{session_id}/screenshot")
async def screenshot(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "No active session")
    image = await session.screenshot_b64()
    return {"image": image}


@app.post("/session/{session_id}/picker/activate")
async def activate_picker(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "No active session")
    await session.activate_picker()
    return {"status": "picker_active"}


class FilterTestRequest(BaseModel):
    text: str
    mode: str
    pattern: str | None = None
    end_pattern: str | None = None


@app.post("/filter/test")
async def filter_test(req: FilterTestRequest):
    """Apply filter to text and return result. Used for live preview."""
    return {"result": apply_text_filter(req.text, req.mode, req.pattern, req.end_pattern)}


@app.post("/session/{session_id}/pick")
async def pick_element(session_id: str, req: ClickRequest):
    """Get element info at given coordinates without clicking."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "No active session")
    result = await session.pick_element_at(req.x, req.y)
    return {"result": result}


@app.get("/session/{session_id}/picker/result")
async def get_picker_result(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "No active session")
    result = await session.get_picker_result()
    return {"result": result}


@app.get("/session/{session_id}/steps")
async def get_steps(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "No active session")
    return {"steps": session.steps}


@app.delete("/session/{session_id}")
async def close_session(session_id: str):
    session = sessions.pop(session_id, None)
    if session:
        await session.close()
    return {"status": "closed"}


@app.post("/scrape")
async def scrape(req: ScrapeRequest):
    """One-shot scrape: start browser, replay steps, extract value, close."""
    from playwright.async_api import async_playwright

    timeout_ms = req.timeout * 1000
    state_path = os.path.join(STORAGE_DIR, f"{req.monitor_id}_state.json")

    try:
        async with async_playwright() as p:
            launch_args = {
                "headless": True,
                "args": ["--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage"],
            }
            system_chromium = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH")
            if system_chromium and os.path.exists(system_chromium):
                launch_args["executable_path"] = system_chromium

            browser = await p.chromium.launch(**launch_args)
            try:
                storage = state_path if req.persist_session and os.path.exists(state_path) else None
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    storage_state=storage,
                )
                page = await context.new_page()

                for step in req.steps:
                    s = step.model_dump(exclude_none=True)
                    action = s["action"]
                    if action == "goto":
                        await page.goto(normalize_url(s["url"]), wait_until="domcontentloaded", timeout=timeout_ms)
                    elif action == "click":
                        await page.click(s["selector"], timeout=timeout_ms)
                    elif action == "fill":
                        await page.fill(s["selector"], s["value"], timeout=timeout_ms)
                    elif action == "wait":
                        await page.wait_for_selector(s["selector"], timeout=timeout_ms)
                    elif action == "select":
                        await page.select_option(s["selector"], s["value"], timeout=timeout_ms)

                element = await page.wait_for_selector(req.target.selector, timeout=timeout_ms)

                extract = req.target.extract
                if extract == "text_content":
                    value = await element.text_content()
                elif extract == "inner_html":
                    value = await element.inner_html()
                elif extract == "attribute" and req.target.attribute:
                    value = await element.get_attribute(req.target.attribute)
                else:
                    value = await element.text_content()

                # Apply optional text filter to extract just a part of the value
                value = apply_text_filter(
                    value,
                    req.target.filter_mode,
                    req.target.filter_pattern,
                    req.target.filter_end_pattern,
                )

                screenshot_b64 = None
                if req.save_screenshot:
                    png = await page.screenshot(full_page=False)
                    screenshot_b64 = base64.b64encode(png).decode()

                if req.persist_session:
                    await context.storage_state(path=state_path)

                return {
                    "success": True,
                    "value": value,
                    "screenshot": screenshot_b64,
                }
            finally:
                await browser.close()

    except Exception as err:
        _LOGGER.error("Scrape failed: %s", err)
        return {"success": False, "value": None, "error": str(err)}
