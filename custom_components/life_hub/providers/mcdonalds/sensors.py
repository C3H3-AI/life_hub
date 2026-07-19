"""McDonald's (麦当劳) sensors for Life Hub."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ...const import DOMAIN
from ...models import ProviderRuntime
from ...providers.base_client import parse_mcp_content
from ...providers.yiming.sensors import LifeHubSensor, LifeHubDataCoordinator

_LOGGER = logging.getLogger(__name__)


def _to_float(v):
    """把 MCP 可能返回的任意形态数值安全转成 float，无法解析则返回 None。

    MCP 常把积分/金额以带千分位逗号、货币符号（¥/元）甚至单位的字符串返回，
    例如 "1,234"、"¥1,234"、"1,234.5元"。这里只保留数字/小数点/负号再转。
    """
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip().replace(",", "").replace("，", "")
        s = "".join(c for c in s if c.isdigit() or c in ".-")
        if s in ("", "-", ".", "-.", ".-"):
            return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _normalize_coupons(parsed):
    """把 available-coupons 的解析结果归一成 list（或 None）。

    麦当劳 MCP 优惠券真数据在 structuredContent.data 里，可能是
    直接的 list，也可能是 {"data": [...]} / {"data": {"list": [...]}} 信封。
    """
    if parsed is None:
        return None
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        d = parsed.get("data") if isinstance(parsed.get("data"), dict) else parsed
        if isinstance(d, list):
            return d
        for v in d.values():
            if isinstance(v, list):
                return v
    return None


# Exported for stale-entity cleanup in sensor.py.
SENSOR_SUFFIXES: list[str] = [
    "available_points", "accumulative_points", "expiring_points",
    "available_coupons",
]


class McdonaldsDataCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for McDonald's data (points, coupons, etc.)."""

    def __init__(self, hass, provider_rt: ProviderRuntime) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_mcdonalds_data",
            update_interval=timedelta(minutes=provider_rt.refresh_interval),
        )
        self._provider_rt = provider_rt

    async def _async_update_data(self) -> dict[str, Any]:
        client = self._provider_rt.client
        results: dict[str, Any] = {}
        # Query account info (points)
        try:
            raw = await client.call_tool("query-my-account", {})
            parsed = parse_mcp_content(raw)
            if isinstance(parsed, dict):
                # 麦当劳 MCP 真数据在 structuredContent.data 里（外层是 success/code/message 信封）
                account = parsed.get("data") if isinstance(parsed.get("data"), dict) else parsed
                # 归一化：数值常以字符串（含千分位逗号）返回，转成 float
                # 转成 float 避免传感器 native_value 里 float() 抛错。
                for f in ("availablePoint", "accumulativePoint", "frozenPoint", "expiredPoint"):
                    val = account.get(f)
                    if isinstance(val, str):
                        try:
                            account[f] = float(val.replace(",", ""))
                        except ValueError:
                            account[f] = None
                    elif not isinstance(val, (int, float)):
                        # 非数值（dict/list/bool 等）直接置空，避免下游 float() 抛错
                        account[f] = None
                results["account"] = account
            else:
                results["account"] = {}
        except Exception as err:
            _LOGGER.warning("McDonald's query-my-account failed: %s", err)
            results["account"] = {}
        # Query available coupons
        try:
            raw = await client.call_tool("available-coupons", {})
            parsed = parse_mcp_content(raw)
            results["coupons"] = _normalize_coupons(parsed)
        except Exception as err:
            _LOGGER.warning("McDonald's available-coupons failed: %s", err)
            results["coupons"] = None
        return results


def build_sensors(
    entry: ConfigEntry,
    provider_key: str,
    provider_rt: ProviderRuntime,
    coordinator: McdonaldsDataCoordinator,
) -> list[SensorEntity]:
    """Build all McDonald's data sensors."""

    def available_points_val(d):
        return _to_float(d.get("account", {}).get("availablePoint"))

    def available_points_attrs(d):
        acc = d.get("account", {})
        return {
            "accumulative_point": acc.get("accumulativePoint"),
            "frozen_point": acc.get("frozenPoint"),
            "expired_point": acc.get("expiredPoint"),
        }

    def accumulative_points_val(d):
        return _to_float(d.get("account", {}).get("accumulativePoint"))

    def expiring_points_val(d):
        return _to_float(d.get("account", {}).get("expiredPoint"))

    def available_coupons_val(d):
        coupons = d.get("coupons")
        if coupons is None:
            return None
        if isinstance(coupons, list):
            return len(coupons)
        return 0

    def available_coupons_attrs(d):
        coupons = d.get("coupons")
        if not isinstance(coupons, list):
            return {}
        return {
            "coupons": [
                {
                    "name": c.get("couponName") or c.get("name"),
                    "value": c.get("faceValue") or c.get("value"),
                    "desc": c.get("description") or c.get("desc"),
                    "end_date": c.get("endDate") or c.get("endTime"),
                }
                for c in coupons[:20]
            ],
        }

    return [
        LifeHubSensor(entry, provider_key, provider_rt, coordinator,
            key="available_points", name="可用积分", icon="mdi:star-circle",
            value_fn=available_points_val, attrs_fn=available_points_attrs,
            state_class=SensorStateClass.MEASUREMENT),
        LifeHubSensor(entry, provider_key, provider_rt, coordinator,
            key="accumulative_points", name="累计积分", icon="mdi:chart-line",
            value_fn=accumulative_points_val,
            state_class=SensorStateClass.MEASUREMENT),
        LifeHubSensor(entry, provider_key, provider_rt, coordinator,
            key="expiring_points", name="即将过期积分", icon="mdi:clock-alert",
            value_fn=expiring_points_val,
            state_class=SensorStateClass.MEASUREMENT),
        LifeHubSensor(entry, provider_key, provider_rt, coordinator,
            key="available_coupons", name="可领优惠券", icon="mdi:ticket-confirmation",
            value_fn=available_coupons_val, attrs_fn=available_coupons_attrs,
            state_class=SensorStateClass.MEASUREMENT),
    ]
