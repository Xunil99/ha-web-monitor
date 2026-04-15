"""Integration-level tests for Web Monitor."""
import pytest
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.web_monitor.browser import BrowserWrapper, ScrapeResult
from custom_components.web_monitor.history import HistoryStore


class TestEndToEnd:
    """Test the full flow: record steps, scrape, history."""

    @pytest.mark.asyncio
    async def test_full_scrape_cycle(self):
        """Test scraping and storing to history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "history.db")
            history = HistoryStore(db_path)
            await history.async_setup()

            browser = BrowserWrapper(tmpdir)

            steps = [
                {"action": "goto", "url": "https://example.com"},
                {"action": "click", "selector": "#btn"},
            ]
            target = {"selector": ".price", "extract": "text_content"}

            with patch("custom_components.web_monitor.browser.async_playwright") as mock_pw:
                mock_browser = AsyncMock()
                mock_context = AsyncMock()
                mock_page = AsyncMock()
                mock_element = AsyncMock()

                mock_pw.return_value.__aenter__.return_value.chromium.launch = AsyncMock(return_value=mock_browser)
                mock_browser.new_context = AsyncMock(return_value=mock_context)
                mock_context.new_page = AsyncMock(return_value=mock_page)
                mock_page.wait_for_selector = AsyncMock(return_value=mock_element)
                mock_element.text_content = AsyncMock(return_value="42,50 EUR")

                result = await browser.replay_and_extract(steps, target, timeout=30)

            assert result.success
            assert result.value == "42,50 EUR"

            await history.add_reading("test_monitor", result.value, None, changed=True)

            readings = await history.get_readings("test_monitor")
            assert len(readings) == 1
            assert readings[0]["value"] == "42,50 EUR"

            count = await history.get_reading_count("test_monitor")
            assert count == 1

            await history.async_close()
