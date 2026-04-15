"""Sensor platform for Web Monitor."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_INTERVAL, CONF_MONITOR_NAME, CONF_STEPS, CONF_TARGET_SELECTOR, DOMAIN
from .coordinator import WebMonitorCoordinator
from .history import HistoryStore


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Web Monitor sensor from config entry."""
    coordinator: WebMonitorCoordinator = entry.runtime_data["coordinator"]
    config: dict = entry.runtime_data["config"]
    history: HistoryStore = entry.runtime_data["history"]

    async_add_entities([WebMonitorSensor(coordinator, config, history)])


class WebMonitorSensor(CoordinatorEntity[WebMonitorCoordinator], SensorEntity):
    """Sensor showing the monitored web value."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: WebMonitorCoordinator,
        config: dict,
        history: HistoryStore,
    ) -> None:
        super().__init__(coordinator)
        self._config = config
        self._history = history
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_web_monitor"
        self._attr_name = config.get(CONF_MONITOR_NAME, "Web Monitor")
        self._attr_icon = "mdi:web"

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data:
            return self.coordinator.data.get("value")
        return None

    @property
    def extra_state_attributes(self) -> dict:
        attrs = {
            "selector": self._config.get(CONF_TARGET_SELECTOR, ""),
            "check_interval": self._config.get(CONF_INTERVAL, 3600),
        }
        steps = self._config.get(CONF_STEPS, [])
        for step in steps:
            if step.get("action") == "goto":
                attrs["source_url"] = step.get("url", "")
                break

        if self.coordinator.data:
            data = self.coordinator.data
            attrs["previous_value"] = data.get("previous_value")
            attrs["value_changed"] = data.get("changed", False)
            if data.get("screenshot_path"):
                attrs["screenshot"] = data["screenshot_path"]

        return attrs

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.coordinator.config_entry.entry_id)},
            "name": self._config.get(CONF_MONITOR_NAME, "Web Monitor"),
            "manufacturer": "Web Monitor",
            "model": "Web Scraper",
        }
