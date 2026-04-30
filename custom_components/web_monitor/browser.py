"""HTTP client wrapper for the Web Monitor Browser Add-on."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

import aiohttp

from .const import (
    EXTRACT_ATTRIBUTE,
    EXTRACT_INNER_HTML,
    EXTRACT_TEXT,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_ADDON_URL = "http://web_monitor_browser:8099"
_FALLBACK_URLS = [
    "http://web_monitor_browser:8099",
    "http://local_web_monitor_browser:8099",
    "http://homeassistant.local:8099",
    "http://localhost:8099",
]


async def _find_reachable_addon_url() -> str | None:
    """Probe candidate URLs and return the first that responds."""
    for candidate in _FALLBACK_URLS:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{candidate}/health",
                    timeout=aiohttp.ClientTimeout(total=3),
                ) as resp:
                    if resp.status == 200:
                        return candidate
        except Exception:
            continue
    return None


@dataclass
class ScrapeResult:
    """Result of a scraping run."""
    success: bool
    value: str | None = None
    error: str | None = None
    screenshot: bytes | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


class BrowserWrapper:
    """HTTP client that communicates with the Web Monitor Browser Add-on."""

    def __init__(self, addon_url: str = DEFAULT_ADDON_URL) -> None:
        self._addon_url = addon_url.rstrip("/")

    async def check_addon_available(self) -> bool:
        """Check if the add-on is running."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self._addon_url}/health", timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False

    async def replay_and_extract(
        self,
        steps: list[dict],
        target: dict,
        timeout: int = 60,
        monitor_id: str = "default",
        persist_session: bool = True,
        save_screenshot: bool = False,
    ) -> ScrapeResult:
        """Send scrape request to the add-on."""
        payload = {
            "steps": steps,
            "target": {
                "selector": target.get("selector", ""),
                "extract": target.get("extract", "text_content"),
                "filter_mode": target.get("filter_mode", "none"),
                "filter_pattern": target.get("filter_pattern", "") or None,
                "filter_end_pattern": target.get("filter_end_pattern", "") or None,
            },
            "timeout": timeout,
            "monitor_id": monitor_id,
            "persist_session": persist_session,
            "save_screenshot": save_screenshot,
        }
        if target.get("attribute"):
            payload["target"]["attribute"] = target["attribute"]

        # Auto-resolve add-on URL if default is not reachable
        if not await self.check_addon_available():
            resolved = await _find_reachable_addon_url()
            if resolved:
                self._addon_url = resolved
                _LOGGER.info("Using add-on URL: %s", resolved)
            else:
                return ScrapeResult(
                    success=False,
                    error="Web Monitor Browser add-on is not reachable. Make sure it's installed and running.",
                )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self._addon_url}/scrape",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=timeout + 30),
                ) as resp:
                    if resp.status != 200:
                        return ScrapeResult(
                            success=False,
                            error=f"Add-on returned HTTP {resp.status}",
                        )
                    data = await resp.json()

            if not data.get("success"):
                return ScrapeResult(success=False, error=data.get("error", "Unknown error"))

            return ScrapeResult(
                success=True,
                value=data.get("value"),
            )

        except aiohttp.ClientError as err:
            _LOGGER.error("Failed to reach Web Monitor Browser add-on: %s", err)
            return ScrapeResult(
                success=False,
                error=f"Add-on not reachable: {err}. Is the Web Monitor Browser add-on installed and running?",
            )
        except Exception as err:
            _LOGGER.error("Scraping failed: %s", err)
            return ScrapeResult(success=False, error=str(err))
