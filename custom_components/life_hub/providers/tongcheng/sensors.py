"""同程旅行订单传感器。"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from ...models import ProviderRuntime

_LOGGER = logging.getLogger(__name__)

DOMAIN = "life_hub"

SENSOR_SUFFIXES = ["order_count", "user_name"]


class TongchengDataCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to fetch tongcheng order data."""

    def __init__(self, hass: HomeAssistant, provider_rt: ProviderRuntime) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_tongcheng_data",
            update_interval=timedelta(minutes=30),
        )
        self._provider_rt = provider_rt

    async def _async_update_data(self) -> dict[str, Any]:
        client = getattr(self._provider_rt, "client", None)
        if client is None:
            raise UpdateFailed("Tongcheng client not available")

        data: dict[str, Any] = {}

        try:
            orders = await client.get_orders()
            data["order_count"] = len(orders) if isinstance(orders, list) else 0
        except Exception as err:
            _LOGGER.warning("Tongcheng get_orders failed: %s", err)
            data["order_count"] = 0

        try:
            user_info = await client.get_user_info()
            if isinstance(user_info, dict):
                data["user_name"] = user_info.get("nickname") or user_info.get("name", "")
        except Exception as err:
            _LOGGER.warning("Tongcheng get_user_info failed: %s", err)

        return data


def build_sensors(
    entry: ConfigEntry,
    provider_key: str,
    provider_rt: ProviderRuntime,
    coordinator: TongchengDataCoordinator,
) -> list[SensorEntity]:
    """Build tongcheng data sensors."""
    return [
        OrderCountSensor(entry, provider_key, provider_rt, coordinator),
    ]


class OrderCountSensor(CoordinatorEntity[TongchengDataCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:receipt-text-check"

    def __init__(
        self,
        entry: ConfigEntry,
        provider_key: str,
        provider_rt: ProviderRuntime,
        coordinator: TongchengDataCoordinator,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{provider_key}_order_count"
        self._attr_name = "订单数量"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id, provider_rt.subentry_type)},
        }

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data:
            return self.coordinator.data.get("order_count", 0)
        return None
