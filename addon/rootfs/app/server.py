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
        if url != "about:blank":
            await self._page.goto(url, wait_until="networkidle", timeout=30000)
            self._steps.append({"action": "goto", "url": url})

    async def screenshot_b64(self) -> str:
        png = await self._page.screenshot(full_page=False)
        return base64.b64encode(png).decode()

    async def navigate(self, url: str):
        await self._page.goto(url, wait_until="networkidle", timeout=30000)
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

    async def fill(self, selector: str, value: str):
        await self._page.fill(selector, value)
        self._steps.append({"action": "fill", "selector": selector, "value": value})

    async def activate_picker(self):
        await self._page.evaluate(PICKER_JS)

    async def get_picker_result(self) -> dict | None:
        return await self._page.evaluate("window.__wmPickerResult")

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
                        await page.goto(s["url"], wait_until="networkidle", timeout=timeout_ms)
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
