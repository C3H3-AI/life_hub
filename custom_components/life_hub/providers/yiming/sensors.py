"""Yiming (一鸣真鲜奶吧) sensors for Life Hub."""

from __future__ import annotations

import logging
from collections.abc import Callable
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
    "balance", "points", "member_level", "member_expiry", "coupon_count",
    "member_name", "growth_value", "app_notice", "claimable_coupons",
    "recent_orders", "usable_coupons", "integral_detail", "member_equity",
    "transaction_details", "default_address", "nearest_store",
]


class LifeHubDataCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for provider data (balance, points, etc.)."""

    def __init__(self, hass, provider_rt: ProviderRuntime) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_yiming_data",
            update_interval=timedelta(minutes=provider_rt.refresh_interval),
        )
        self._provider_rt = provider_rt

    async def _async_update_data(self) -> dict[str, Any]:
        from .api import YimingApiError
        client = self._provider_rt.client
        results: dict[str, Any] = {}
        tasks = {
            "balance": client.get_balance(),
            "member": client.get_member_info(),
            "coupon": client.get_coupon_sum(),
            "integral": client.get_integral(),
            "user": client.get_user_info(),
            "orders": client.get_orders(page_size=5),
            "my_coupons": client.get_my_coupons(page_size=20),
            "coupon_pools": client.get_coupon_pools(),
            "integral_detail": client.get_integral_detail(page_size=5),
            "app_equity": client.get_app_equity(),
            "transaction_details": client.get_transaction_details(),
            "default_address": client.get_default_address(),
            "app_notice": client.get_app_notice(),
        }
        for key, coro in tasks.items():
            try:
                results[key] = await coro
            except Exception as err:
                _LOGGER.warning("Yiming endpoint %s failed: %s", key, err)
                results[key] = None
        return results


def _safe(data: dict, *keys, default=None):
    """逐层取值, 任一层缺失/为 None 时返回 default."""
    cur: Any = data
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
        if cur is None:
            return default
    return cur


class LifeHubSensor(CoordinatorEntity[LifeHubDataCoordinator], SensorEntity):
    """Generic provider data sensor reused by yiming, mcdonalds, etc."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        provider_key: str,
        provider_rt: ProviderRuntime,
        coordinator: LifeHubDataCoordinator,
        *,
        key: str,
        name: str,
        icon: str,
        value_fn: Callable[[dict], Any],
        attrs_fn: Callable[[dict], dict] | None = None,
        unit: str | None = None,
        state_class: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_name = name
        self._attr_icon = icon
        self._value_fn = value_fn
        self._attrs_fn = attrs_fn
        self._attr_unique_id = f"{entry.entry_id}_{provider_key}_{key}"
        self._attr_config_subentry_id = provider_rt.subentry_id
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = state_class
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id, provider_rt.subentry_type, provider_rt.subentry_id)},
            name=provider_rt.title,
            manufacturer=_MANUFACTURER,
            model=_DEVICE_MODEL,
            entry_type="service",
        )

    @property
    def native_value(self):
        if self.coordinator.data:
            return self._value_fn(self.coordinator.data)
        return None

    @property
    def extra_state_attributes(self) -> dict:
        if self._attrs_fn and self.coordinator.data:
            return self._attrs_fn(self.coordinator.data)
        return {}


def build_sensors(
    entry: ConfigEntry,
    provider_key: str,
    provider_rt: ProviderRuntime,
    coordinator: LifeHubDataCoordinator,
) -> list[SensorEntity]:
    """Build all yiming data sensors."""

    def balance_val(d):
        v = _safe(d, "balance", "balance")
        return float(v) if v is not None else None

    def balance_attrs(d):
        b = _safe(d, "balance") or {}
        return {"vipid": b.get("vipid"), "vipname": b.get("vipname"), "mobile": b.get("mobile")}

    def points_val(d):
        v = _safe(d, "balance", "points")
        if v is not None:
            return int(float(v))
        iv = _safe(d, "integral")
        return int(float(iv)) if iv is not None else None

    def member_level_val(d):
        return _safe(d, "member", "memberCode")

    def member_expiry_val(d):
        v = _safe(d, "member", "invalidDate")
        return v.split(" ")[0] if isinstance(v, str) else v

    def coupon_val(d):
        return _safe(d, "coupon", "sum")

    def name_val(d):
        return _safe(d, "balance", "vipname")

    def growth_val(d):
        v = _safe(d, "member", "userLevelInfoResponse", "growthValue")
        return float(v) if v is not None else None

    def orders_val(d):
        orders = _safe(d, "orders", "list") or []
        return len(orders)

    def usable_coupons_val(d):
        coupons = _safe(d, "my_coupons", "list") or []
        return len(coupons)

    def notice_val(d):
        data = _safe(d, "app_notice")
        if data is None:
            return "无公告"
        if isinstance(data, list):
            return f"{len(data)} 条"
        if isinstance(data, dict):
            return data.get("title") or "有公告"
        return "有公告"

    def notice_attrs(d):
        return {"raw": _safe(d, "app_notice")}

    def claimable_val(d):
        pools = _safe(d, "coupon_pools") or []
        return sum(1 for p in pools if (p.get("residue_count") or 0) > 0)

    def claimable_attrs(d):
        pools = _safe(d, "coupon_pools") or []
        claimable = [p for p in pools if (p.get("residue_count") or 0) > 0]
        return {
            "claimable_count": len(claimable),
            "total_coupons": len(pools),
            "coupons": [
                {
                    "name": p.get("name"),
                    "face_value": p.get("face_value"),
                    "equity_pool_id": p.get("equity_pool_id"),
                    "coupon_code": p.get("coupon_code"),
                    "residue_count": p.get("residue_count"),
                    "valid_time": p.get("valid_time"),
                }
                for p in claimable
            ],
        }

    def integral_detail_val(d):
        detail_data = _safe(d, "integral_detail", "data") or []
        if detail_data:
            last = detail_data[0]
            change = last.get("changeCount", 0)
            return f"{change:+d}"
        return "0"

    def integral_detail_attrs(d):
        detail_data = _safe(d, "integral_detail", "data") or []
        return {
            "total": _safe(d, "integral_detail", "total"),
            "records": [
                {
                    "type_name": r.get("integralTypeName"),
                    "change_count": r.get("changeCount"),
                    "change_time": r.get("changeTime"),
                    "remark": r.get("remark"),
                }
                for r in detail_data[:10]
            ],
        }

    def equity_val(d):
        equity = _safe(d, "app_equity", "levelEquityList") or []
        return len(equity)

    def equity_attrs(d):
        equity = _safe(d, "app_equity", "levelEquityList") or []
        return {
            "levels": [
                {
                    "level": l.get("level"),
                    "equity_pools": [
                        {"name": p.get("name"), "sub_title": p.get("subTitle")}
                        for p in (l.get("equityPoolDTOList") or [])
                    ],
                }
                for l in equity
            ],
        }

    def transaction_val(d):
        txns = _safe(d, "transaction_details") or []
        if txns:
            last = txns[0] if isinstance(txns, list) else txns
            amount = last.get("transactionAmount") or last.get("amount") or 0
            return f"¥{float(amount)/100:.2f}" if amount else "0"
        return "无"

    def transaction_attrs(d):
        txns = _safe(d, "transaction_details") or []
        if not isinstance(txns, list):
            txns = [txns]
        return {
            "records": [
                {
                    "amount": t.get("transactionAmount"),
                    "type": t.get("transactionType"),
                    "time": t.get("createTime") or t.get("transactionTime"),
                    "remark": t.get("remark"),
                }
                for t in txns[:10]
            ],
        }

    def address_val(d):
        addr = _safe(d, "default_address") or {}
        return addr.get("name", "无")

    def address_attrs(d):
        addr = _safe(d, "default_address") or {}
        return {
            "name": addr.get("name"),
            "mobile": addr.get("mobile"),
            "province": addr.get("province"),
            "city": addr.get("city"),
            "district": addr.get("district"),
            "address": addr.get("address"),
        }

    def nearest_store_val(d):
        store = _safe(d, "nearest_store")
        if store is None:
            return "未知"
        return store.get("storeName") or store.get("name") or "未知"

    def nearest_store_attrs(d):
        store = _safe(d, "nearest_store") or {}
        return {
            "store_code": store.get("storeCode"),
            "address": store.get("address"),
            "distance": store.get("distance"),
            "phone": store.get("phone"),
        }

    return [
        LifeHubSensor(entry, provider_key, provider_rt, coordinator,
            key="balance", name="储值余额", icon="mdi:wallet",
            value_fn=balance_val, attrs_fn=balance_attrs, unit="元",
            state_class=SensorStateClass.MEASUREMENT),
        LifeHubSensor(entry, provider_key, provider_rt, coordinator,
            key="points", name="积分", icon="mdi:star-circle",
            value_fn=points_val, state_class=SensorStateClass.MEASUREMENT),
        LifeHubSensor(entry, provider_key, provider_rt, coordinator,
            key="member_level", name="会员等级", icon="mdi:shield-crown",
            value_fn=member_level_val),
        LifeHubSensor(entry, provider_key, provider_rt, coordinator,
            key="member_expiry", name="会员到期", icon="mdi:calendar-clock",
            value_fn=member_expiry_val),
        LifeHubSensor(entry, provider_key, provider_rt, coordinator,
            key="coupon_count", name="优惠券数量", icon="mdi:ticket-percent",
            value_fn=coupon_val, state_class=SensorStateClass.MEASUREMENT),
        LifeHubSensor(entry, provider_key, provider_rt, coordinator,
            key="member_name", name="会员姓名", icon="mdi:account",
            value_fn=name_val),
        LifeHubSensor(entry, provider_key, provider_rt, coordinator,
            key="growth_value", name="成长值", icon="mdi:chart-line",
            value_fn=growth_val, state_class=SensorStateClass.MEASUREMENT),
        LifeHubSensor(entry, provider_key, provider_rt, coordinator,
            key="app_notice", name="App 公告", icon="mdi:bullhorn",
            value_fn=notice_val, attrs_fn=notice_attrs),
        LifeHubSensor(entry, provider_key, provider_rt, coordinator,
            key="claimable_coupons", name="可领优惠券", icon="mdi:ticket-confirmation",
            value_fn=claimable_val, attrs_fn=claimable_attrs, state_class=SensorStateClass.MEASUREMENT),
        LifeHubSensor(entry, provider_key, provider_rt, coordinator,
            key="recent_orders", name="最近订单数", icon="mdi:receipt",
            value_fn=orders_val, state_class=SensorStateClass.MEASUREMENT),
        LifeHubSensor(entry, provider_key, provider_rt, coordinator,
            key="usable_coupons", name="可用优惠券", icon="mdi:ticket-percent-outline",
            value_fn=usable_coupons_val, state_class=SensorStateClass.MEASUREMENT),
        LifeHubSensor(entry, provider_key, provider_rt, coordinator,
            key="integral_detail", name="最近积分变动", icon="mdi:swap-vertical-bold",
            value_fn=integral_detail_val, attrs_fn=integral_detail_attrs),
        LifeHubSensor(entry, provider_key, provider_rt, coordinator,
            key="member_equity", name="会员权益层级", icon="mdi:shield-star",
            value_fn=equity_val, attrs_fn=equity_attrs),
        LifeHubSensor(entry, provider_key, provider_rt, coordinator,
            key="transaction_details", name="最近交易", icon="mdi:swap-horizontal-bold",
            value_fn=transaction_val, attrs_fn=transaction_attrs),
        LifeHubSensor(entry, provider_key, provider_rt, coordinator,
            key="default_address", name="默认地址", icon="mdi:map-marker",
            value_fn=address_val, attrs_fn=address_attrs),
        LifeHubSensor(entry, provider_key, provider_rt, coordinator,
            key="nearest_store", name="最近门店", icon="mdi:store",
            value_fn=nearest_store_val, attrs_fn=nearest_store_attrs),
    ]
