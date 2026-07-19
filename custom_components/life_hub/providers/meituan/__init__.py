"""Meituan provider for Life Hub (合并: 旅行/优惠下单/外卖跑腿)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..base import ProviderSpec
from ...models import ProviderRuntime

_LOGGER = logging.getLogger(__name__)

PROVIDER_KEY = "meituan"
PROVIDER_NAME = "美团"

MEITUAN_API_URL = "https://mcp-open-cater.meituan.com/v1/api/voyage/openapi/query"


def build_schema(current: dict[str, Any]) -> vol.Schema:
    return vol.Schema({
        vol.Required("api_token", default=current.get("api_token", "")): str,
        vol.Optional("refresh_interval", default=current.get("refresh_interval", 30)): vol.All(
            vol.Coerce(int), vol.Range(min=10, max=1440)
        ),
    })


async def validate_config(hass: HomeAssistant, data: dict[str, Any]) -> None:
    token = data.get("api_token", "")
    if not token:
        raise ValueError("api_token is required")
    session = async_get_clientsession(hass)
    try:
        async with session.post(
            MEITUAN_API_URL,
            headers={"Authorization": token, "Content-Type": "application/json"},
            json={"city": "北京", "query": "test"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status == 401:
                raise ValueError("Invalid API token")
            resp.raise_for_status()
            body = await resp.json()
            if body.get("code") != 0:
                raise ValueError(f"API error: {body.get('msg', 'unknown')}")
    except ValueError:
        raise
    except Exception as err:
        raise ValueError(f"Connection failed: {err}") from err


async def setup_provider(
    hass: HomeAssistant,
    config: dict[str, Any],
    subentry_id: str,
) -> ProviderRuntime:
    token = config["api_token"]
    session = async_get_clientsession(hass)
    status = "connected"

    client = MeituanClient(session, token)

    async def stop() -> None:
        pass

    def get_status() -> str:
        return status

    async def _health_check() -> bool:
        try:
            await client.get_orders()
            return True
        except Exception as err:
            _LOGGER.warning("Meituan health check failed: %s", err)
            return False

    return ProviderRuntime(
        key=PROVIDER_KEY, title=PROVIDER_NAME, subentry_id=subentry_id,
        client=client, stop=stop, status=get_status, status_check=_health_check,
    )


class MeituanClient:
    """美团客户端（合并: 旅行/优惠下单/外卖跑腿）"""

    def __init__(self, session: aiohttp.ClientSession, token: str) -> None:
        self._session = session
        self._token = token
        self._headers = {"Authorization": token, "Content-Type": "application/json"}

    _MEITUAN_METHODS: dict[str, Callable[..., Awaitable[dict]]] | None = None

    def _get_methods(self) -> dict[str, Callable[..., Awaitable[dict]]]:
        if self._MEITUAN_METHODS is None:
            type(self)._MEITUAN_METHODS = {
                # ===== 美团旅行 =====
                "search_hotel": lambda p: self.search_hotel(p.get("query", ""), p.get("city", "北京")),
                "search_flight": lambda p: self.search_flight(p.get("origin", ""), p.get("destination", ""), p.get("dep_date", "")),
                "search_train": lambda p: self.search_train(p.get("origin", ""), p.get("destination", ""), p.get("dep_date", "")),
                "search_poi": lambda p: self.search_poi(p.get("city", "北京"), p.get("keyword", "")),
                "plan_itinerary": lambda p: self.plan_itinerary(p.get("city", ""), p.get("days", 3), p.get("budget", 0)),
                "get_travel_orders": lambda p: self.get_travel_orders(),
                # ===== 优惠下单 =====
                "get_orders": lambda p: self.get_orders(),
                "get_coupons": lambda p: self.get_coupons(),
                "claim_coupon": lambda p: self.claim_coupon(p["coupon_id"]),
                "claim_all_coupons": lambda p: self.claim_all_coupons(),
                # ===== 外卖跑腿 =====
                "login": lambda p: self.login(),
                "get_address_list": lambda p: self.get_address_list(),
                "search_poi_waimai": lambda p: self.search_poi_waimai(p.get("keyword", ""), p.get("city", "北京")),
                "preview_order": lambda p: self.preview_order(p["sender"], p["recipient"], p["goods"]),
                "submit_order": lambda p: self.submit_order(p["sender"], p["recipient"], p["goods"]),
                "get_order_status": lambda p: self.get_order_status(p["order_id"]),
                "get_store_info": lambda p: self.get_store_info(p["store_id"]),
                "search_stores": lambda p: self.search_stores(p.get("keyword", "")),
            }
        return self._MEITUAN_METHODS

    async def call_method(self, method: str, params: dict | None = None) -> dict:
        """通用方法调用入口，类似一鸣的 yiming_call_api。"""
        handler = self._get_methods().get(method)
        if handler is None:
            raise ValueError(f"未知方法: {method}，可用方法: {', '.join(sorted(self._get_methods().keys()))}")
        return await handler(params or {})

    async def _query(self, query: str, city: str = "北京") -> dict:
        """通用 AI 查询接口"""
        async with self._session.post(
            MEITUAN_API_URL,
            headers=self._headers,
            json={"city": city, "query": query},
            timeout=aiohttp.ClientTimeout(total=120),
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    # ========== 美团旅行相关 ==========

    async def search_hotel(self, query: str, city: str = "北京") -> dict:
        return await self._query(f"搜索酒店：{query}", city)

    async def search_flight(self, origin: str, destination: str, dep_date: str = "", **kwargs) -> dict:
        query = f"搜索机票：从{origin}到{destination}"
        if dep_date:
            query += f"，出发日期{dep_date}"
        return await self._query(query)

    async def search_train(self, origin: str, destination: str, dep_date: str = "", **kwargs) -> dict:
        query = f"搜索火车票：从{origin}到{destination}"
        if dep_date:
            query += f"，出发日期{dep_date}"
        return await self._query(query)

    async def search_poi(self, city: str, keyword: str = "", **kwargs) -> dict:
        query = f"搜索景点：{city}"
        if keyword:
            query += f"，{keyword}"
        return await self._query(query, city)

    async def plan_itinerary(self, city: str, days: int = 3, budget: int = 0, **kwargs) -> dict:
        query = f"行程规划：{city}，{days}天"
        if budget:
            query += f"，预算{budget}元"
        return await self._query(query, city)

    async def get_travel_orders(self) -> dict:
        """获取美团旅行订单"""
        return await self._query("查询我的美团旅行订单")

    # ========== 优惠下单相关 ==========

    async def get_orders(self) -> dict:
        """获取美团订单列表"""
        return await self._query("查询我的美团订单列表")

    async def get_coupons(self) -> dict:
        """获取优惠券列表"""
        return await self._query("查询我的美团优惠券列表")

    async def claim_coupon(self, coupon_id: str) -> dict:
        """领取指定优惠券"""
        return await self._query(f"领取美团优惠券，优惠券ID：{coupon_id}")

    async def claim_all_coupons(self) -> dict:
        """领取所有可领优惠券"""
        return await self._query("帮我领取所有可领取的美团优惠券")

    # ========== 外卖跑腿相关 ==========

    async def login(self) -> dict:
        """检查登录状态"""
        return await self._query("查询美团账号登录状态")

    async def get_address_list(self) -> dict:
        """获取用户地址簿"""
        return await self._query("查询我的美团收货地址列表")

    async def search_poi_waimai(self, keyword: str, city: str = "北京") -> dict:
        """POI 地址搜索（外卖跑腿）"""
        return await self._query(f"搜索美团地址：{city} {keyword}", city)

    async def preview_order(self, sender: dict, recipient: dict, goods: dict, **kwargs) -> dict:
        """预览订单（不提交）"""
        return await self._query(f"预览美团跑腿订单：从{sender}到{recipient}，物品{goods}")

    async def submit_order(self, sender: dict, recipient: dict, goods: dict, **kwargs) -> dict:
        """提交订单"""
        return await self._query(f"提交美团跑腿订单：从{sender}到{recipient}，物品{goods}")

    async def get_order_status(self, order_id: str) -> dict:
        """查询订单状态"""
        return await self._query(f"查询美团订单状态，订单ID：{order_id}")

    async def get_store_info(self, store_id: str) -> dict:
        """获取门店信息"""
        return await self._query(f"查询美团门店信息，门店ID：{store_id}")

    async def search_stores(self, keyword: str, **kwargs) -> dict:
        """搜索附近门店"""
        return await self._query(f"搜索美团门店：{keyword}")


PROVIDER_SPEC = ProviderSpec(
    key=PROVIDER_KEY,
    name=PROVIDER_NAME,
    schema_builder=build_schema,
    validate_config=validate_config,
    setup_provider=setup_provider,
    allow_multiple=True,
)