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

DEFAULT_ADDON_URL = "http://localhost:8099"


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
            },
            "timeout": timeout,
            "monitor_id": monitor_id,
            "persist_session": persist_session,
            "save_screenshot": save_screenshot,
        }
        if target.get("attribute"):
            payload["target"]["attribute"] = target["attribute"]

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
