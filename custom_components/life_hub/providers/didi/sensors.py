"""滴滴出行 sensors for Life Hub."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from ...const import DOMAIN
from ...models import ProviderRuntime

_LOGGER = logging.getLogger(__name__)

_DEVICE_MODEL = "Life Hub Provider"
_MANUFACTURER = "Life Hub"

# Exported for stale-entity cleanup in sensor.py.
SENSOR_SUFFIXES: list[str] = [
    "order_status",
]


class DidiDataCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for Didi data (current order status)."""

    def __init__(self, hass, provider_rt: ProviderRuntime) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_didi_data",
            update_interval=timedelta(minutes=provider_rt.refresh_interval),
        )
        self._provider_rt = provider_rt

    async def _async_update_data(self) -> dict[str, Any]:
        client = self._provider_rt.client
        results: dict[str, Any] = {}
        try:
            result = await client.taxi_query_order()
            results["order_status"] = result
        except Exception as err:
            _LOGGER.warning("Didi query order failed: %s", err)
            results["order_status"] = None
        return results


def build_sensors(
    entry: ConfigEntry,
    provider_key: str,
    provider_rt: ProviderRuntime,
    coordinator: DidiDataCoordinator,
) -> list[SensorEntity]:
    return [
        DidiOrderStatusSensor(entry, provider_key, provider_rt, coordinator),
    ]


class DidiOrderStatusSensor(CoordinatorEntity, SensorEntity):
    """滴滴当前订单状态传感器."""

    def __init__(
        self,
        entry: ConfigEntry,
        provider_key: str,
        provider_rt: ProviderRuntime,
        coordinator: DidiDataCoordinator,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._provider_key = provider_key
        self._provider_rt = provider_rt
        self._sensor_key = "order_status"

        self._attr_unique_id = f"{entry.entry_id}_{provider_key}_{self._sensor_key}"
        self._attr_name = f"{provider_rt.title} 当前订单"
        self._attr_icon = "mdi:car"
        self._attr_should_poll = False
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id, provider_rt.subentry_type, provider_rt.subentry_id)},
            name=provider_rt.title,
            manufacturer=_MANUFACTURER,
            model=_DEVICE_MODEL,
            entry_type="service",
        )

    @property
    def native_value(self) -> str:
        data = self.coordinator.data or {}
        order = data.get("order_status", {})
        if not order:
            return "无订单"
        content = order.get("content", [])
        if content:
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    return c.get("text", "未知")
        sc = order.get("structuredContent", {})
        if sc:
            status_text = sc.get("statusText", "")
            if status_text:
                return status_text
        return "有订单"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        data = self.coordinator.data or {}
        order = data.get("order_status", {})
        if not order:
            return None
        sc = order.get("structuredContent", {})
        if not sc:
            return None
        attrs = {}
        if sc.get("statusCode") is not None:
            attrs["status_code"] = sc["statusCode"]
        if sc.get("statusText"):
            attrs["status_text"] = sc["statusText"]
        if sc.get("driver"):
            attrs["driver"] = sc["driver"]
        if sc.get("map"):
            attrs["map"] = sc["map"]
        return attrs or None