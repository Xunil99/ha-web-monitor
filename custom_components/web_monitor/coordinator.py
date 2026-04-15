"""DataUpdateCoordinator for Web Monitor."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .browser import BrowserWrapper, ScrapeResult
from .const import (
    CONF_INTERVAL,
    CONF_MONITOR_NAME,
    CONF_PERSIST_SESSION,
    CONF_SAVE_SCREENSHOTS,
    CONF_STEPS,
    CONF_TARGET_EXTRACT,
    CONF_TARGET_SELECTOR,
    CONF_TIMEOUT,
    DEFAULT_INTERVAL,
    DEFAULT_TIMEOUT,
)
from .history import HistoryStore

_LOGGER = logging.getLogger(__name__)


class WebMonitorCoordinator(DataUpdateCoordinator[dict]):
    """Coordinator that periodically scrapes a web page."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict,
        entry_id: str,
        browser: BrowserWrapper,
        history: HistoryStore,
    ) -> None:
        interval = config.get(CONF_INTERVAL, DEFAULT_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=f"Web Monitor: {config.get(CONF_MONITOR_NAME, entry_id)}",
            update_interval=timedelta(seconds=interval),
        )
        self._config = config
        self._entry_id = entry_id
        self._browser = browser
        self._history = history
        self._last_value: str | None = None

    async def _async_update_data(self) -> dict:
        """Fetch data by replaying steps and extracting target."""
        steps = self._config.get(CONF_STEPS, [])
        if not steps:
            return {"value": None, "success": True, "message": "No steps configured"}

        target = {
            "selector": self._config.get(CONF_TARGET_SELECTOR, ""),
            "extract": self._config.get(CONF_TARGET_EXTRACT, "text_content"),
        }

        if not target["selector"]:
            return {"value": None, "success": True, "message": "No target configured"}

        result: ScrapeResult = await self._browser.replay_and_extract(
            steps=steps,
            target=target,
            timeout=self._config.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
            monitor_id=self._entry_id,
            persist_session=self._config.get(CONF_PERSIST_SESSION, True),
            save_screenshot=self._config.get(CONF_SAVE_SCREENSHOTS, False),
        )

        if not result.success:
            raise UpdateFailed(f"Scraping failed: {result.error}")

        changed = result.value != self._last_value
        previous = self._last_value

        screenshot_path = None
        if result.screenshot:
            import os
            screenshot_dir = os.path.join(self._browser._storage_dir, "screenshots")
            os.makedirs(screenshot_dir, exist_ok=True)
            screenshot_path = os.path.join(screenshot_dir, f"{self._entry_id}_latest.png")
            with open(screenshot_path, "wb") as f:
                f.write(result.screenshot)

        await self._history.add_reading(
            monitor_id=self._entry_id,
            value=result.value,
            previous_value=previous,
            changed=changed,
            screenshot_path=screenshot_path,
        )

        self._last_value = result.value

        return {
            "value": result.value,
            "success": True,
            "changed": changed,
            "previous_value": previous,
            "screenshot_path": screenshot_path,
        }
