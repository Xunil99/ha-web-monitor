"""Playwright browser wrapper for Web Monitor."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime

from playwright.async_api import async_playwright

from .const import (
    EXTRACT_ATTRIBUTE,
    EXTRACT_INNER_HTML,
    EXTRACT_TEXT,
    STEP_CLICK,
    STEP_FILL,
    STEP_GOTO,
    STEP_SELECT,
    STEP_WAIT,
)

_LOGGER = logging.getLogger(__name__)

BROWSER_ARGS = [
    "--disable-gpu",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-background-networking",
    "--disable-extensions",
]


@dataclass
class ScrapeResult:
    """Result of a scraping run."""
    success: bool
    value: str | None = None
    error: str | None = None
    screenshot: bytes | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


class BrowserWrapper:
    """Manages Playwright browser lifecycle and step execution."""

    def __init__(self, storage_dir: str) -> None:
        self._storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)

    def _storage_state_path(self, monitor_id: str) -> str:
        return os.path.join(self._storage_dir, f"{monitor_id}_state.json")

    async def replay_and_extract(
        self,
        steps: list[dict],
        target: dict,
        timeout: int = 60,
        monitor_id: str = "default",
        persist_session: bool = True,
        save_screenshot: bool = False,
    ) -> ScrapeResult:
        timeout_ms = timeout * 1000
        state_path = self._storage_state_path(monitor_id)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=BROWSER_ARGS)
            try:
                storage = state_path if persist_session and os.path.exists(state_path) else None
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 720},
                    storage_state=storage,
                )
                page = await context.new_page()

                for step in steps:
                    await self._execute_step(page, step, timeout_ms)

                element = await page.wait_for_selector(target["selector"], timeout=timeout_ms)
                value = await self._extract_value(element, target)

                screenshot = None
                if save_screenshot:
                    screenshot = await page.screenshot(full_page=False)

                if persist_session:
                    await context.storage_state(path=state_path)

                return ScrapeResult(success=True, value=value, screenshot=screenshot)

            except Exception as err:
                _LOGGER.error("Scraping failed: %s", err)
                return ScrapeResult(success=False, error=str(err))
            finally:
                await browser.close()

    async def _execute_step(self, page, step: dict, timeout_ms: int) -> None:
        action = step["action"]
        if action == STEP_GOTO:
            await page.goto(step["url"], wait_until="networkidle", timeout=timeout_ms)
        elif action == STEP_CLICK:
            await page.click(step["selector"], timeout=timeout_ms)
        elif action == STEP_FILL:
            await page.fill(step["selector"], step["value"], timeout=timeout_ms)
        elif action == STEP_WAIT:
            await page.wait_for_selector(step["selector"], timeout=timeout_ms)
        elif action == STEP_SELECT:
            await page.select_option(step["selector"], step["value"], timeout=timeout_ms)
        else:
            _LOGGER.warning("Unknown step action: %s", action)

    async def _extract_value(self, element, target: dict) -> str | None:
        extract = target.get("extract", EXTRACT_TEXT)
        if extract == EXTRACT_TEXT:
            return await element.text_content()
        elif extract == EXTRACT_INNER_HTML:
            return await element.inner_html()
        elif extract == EXTRACT_ATTRIBUTE:
            attr = target.get("attribute", "")
            return await element.get_attribute(attr)
        return None
