"""美团旅游传感器 — 旅行订单数、优惠券数量。"""
from __future__ import annotations

import logging
import re
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

SENSOR_SUFFIXES = ["travel_order_count", "coupon_count"]


class MeituanDataCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to fetch meituan travel data."""

    def __init__(self, hass: HomeAssistant, provider_rt: ProviderRuntime) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_meituan_data",
            update_interval=timedelta(minutes=30),
        )
        self._provider_rt = provider_rt

    async def _async_update_data(self) -> dict[str, Any]:
        client = getattr(self._provider_rt, "client", None)
        if client is None:
            raise UpdateFailed("Meituan client not available")

        data: dict[str, Any] = {}

        try:
            orders = await client.get_travel_orders()
            data["travel_order_count"] = _extract_count(orders, "订单")
        except Exception as err:
            _LOGGER.warning("Meituan get_travel_orders failed: %s", err)
            data["travel_order_count"] = 0

        try:
            coupons = await client.get_coupons()
            data["coupon_count"] = _extract_count(coupons, "优惠券")
        except Exception as err:
            _LOGGER.warning("Meituan get_coupons failed: %s", err)
            data["coupon_count"] = 0

        return data


def _extract_count(response: dict, keyword: str) -> int:
    for key in ("count", "total", "num", "size", "number", "quantity"):
        val = response.get(key)
        if isinstance(val, (int, float)):
            return int(val)
    result = response.get("result", {})
    if isinstance(result, str):
        nums = re.findall(rf'(\d+)\s*{keyword}', result)
        if nums:
            return int(nums[0])
    elif isinstance(result, dict):
        content = result.get("content", "")
        if isinstance(content, str):
            nums = re.findall(rf'(\d+)\s*{keyword}', content)
            if nums:
                return int(nums[0])
    data = response.get("data", {})
    if isinstance(data, dict):
        if "list" in data and isinstance(data["list"], list):
            return len(data["list"])
        if "items" in data and isinstance(data["items"], list):
            return len(data["items"])
    for msg in response.get("messages", []):
        if isinstance(msg, str):
            nums = re.findall(rf'(\d+)\s*{keyword}', msg)
            if nums:
                return int(nums[0])
    return 0


def build_sensors(
    entry: ConfigEntry,
    provider_key: str,
    provider_rt: ProviderRuntime,
    coordinator: MeituanDataCoordinator,
) -> list[SensorEntity]:
    return [
        TravelOrderCountSensor(entry, provider_key, provider_rt, coordinator),
        CouponCountSensor(entry, provider_key, provider_rt, coordinator),
    ]


class TravelOrderCountSensor(CoordinatorEntity[MeituanDataCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:airplane"

    def __init__(
        self, entry: ConfigEntry, provider_key: str,
        provider_rt: ProviderRuntime, coordinator: MeituanDataCoordinator,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{provider_key}_travel_order_count"
        self._attr_name = "旅行订单数量"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id, provider_rt.subentry_type, provider_rt.subentry_id)},
        }

    @property
    def native_value(self) -> int | None:
        return (self.coordinator.data or {}).get("travel_order_count", 0)


class CouponCountSensor(CoordinatorEntity[MeituanDataCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:ticket-percent"

    def __init__(
        self, entry: ConfigEntry, provider_key: str,
        provider_rt: ProviderRuntime, coordinator: MeituanDataCoordinator,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{provider_key}_coupon_count"
        self._attr_name = "优惠券数量"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id, provider_rt.subentry_type, provider_rt.subentry_id)},
        }

    @property
    def native_value(self) -> int | None:
        return (self.coordinator.data or {}).get("coupon_count", 0)
