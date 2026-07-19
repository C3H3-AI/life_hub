"""美团优惠下单 provider for Life Hub.

登录方式：扫码登录（美团开发者中心 Passport）。
请在 QClaw 中完成扫码授权后，将获取到的 token 填入 auth_token 字段。
"""
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
from .flow import MeituanOrderSubentryFlow

_LOGGER = logging.getLogger(__name__)

PROVIDER_KEY = "meituan_order"
PROVIDER_NAME = "美团优惠下单"

MEITUAN_API_URL = "https://mcp-open-cater.meituan.com/v1/api/voyage/openapi/query"


def build_schema(current: dict[str, Any]) -> vol.Schema:
    return vol.Schema({
        vol.Required("auth_token", default=current.get("auth_token", "")): str,
        vol.Optional("refresh_interval", default=current.get("refresh_interval", 30)): vol.All(
            vol.Coerce(int), vol.Range(min=10, max=1440)
        ),
    })


async def validate_config(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """验证 token — 通过 MCP 餐饮接口测试连通性。"""
    token = data.get("auth_token", "")
    if not token:
        raise ValueError("auth_token is required（请先在 QClaw 中扫码获取）")
    session = async_get_clientsession(hass)
    try:
        async with session.post(
            MEITUAN_API_URL,
            headers={"Authorization": token, "Content-Type": "application/json"},
            json={"city": "北京", "query": "test"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status == 401:
                raise ValueError("Token 无效 (401)，请重新扫码获取")
            resp.raise_for_status()
            body = await resp.json()
            if body.get("code") != 0:
                raise ValueError(f"API error: {body.get('msg', 'unknown')}")
    except ValueError:
        raise
    except Exception as err:
        raise ValueError(f"连接失败: {err}") from err


async def setup_provider(
    hass: HomeAssistant,
    config: dict[str, Any],
    subentry_id: str,
) -> ProviderRuntime:
    token = config["auth_token"]
    session = async_get_clientsession(hass)
    status = "connected"

    client = MeituanOrderClient(session, token)

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


class MeituanOrderClient:
    """美团优惠下单客户端。"""

    def __init__(self, session: aiohttp.ClientSession, token: str) -> None:
        self._session = session
        self._token = token
        self._headers = {"Authorization": token, "Content-Type": "application/json"}

    _MEITUAN_METHODS: dict[str, Callable[..., Awaitable[dict]]] | None = None

    def _get_methods(self) -> dict[str, Callable[..., Awaitable[dict]]]:
        if self._MEITUAN_METHODS is None:
            type(self)._MEITUAN_METHODS = {
                "get_orders": lambda p: self.get_orders(),
                "get_coupons": lambda p: self.get_coupons(),
                "claim_coupon": lambda p: self.claim_coupon(p["coupon_id"]),
                "claim_all_coupons": lambda p: self.claim_all_coupons(),
            }
        return self._MEITUAN_METHODS

    async def call_method(self, method: str, params: dict | None = None) -> dict:
        handler = self._get_methods().get(method)
        if handler is None:
            raise ValueError(f"未知方法: {method}")
        return await handler(params or {})

    async def _query(self, query: str, city: str = "北京") -> dict:
        async with self._session.post(
            MEITUAN_API_URL,
            headers=self._headers,
            json={"city": city, "query": query},
            timeout=aiohttp.ClientTimeout(total=120),
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def get_orders(self) -> dict:
        return await self._query("查询我的美团订单列表")

    async def get_coupons(self) -> dict:
        return await self._query("查询我的美团优惠券列表")

    async def claim_coupon(self, coupon_id: str) -> dict:
        return await self._query(f"领取美团优惠券，优惠券ID：{coupon_id}")

    async def claim_all_coupons(self) -> dict:
        return await self._query("帮我领取所有可领取的美团优惠券")


PROVIDER_SPEC = ProviderSpec(
    key=PROVIDER_KEY,
    name=PROVIDER_NAME,
    schema_builder=build_schema,
    validate_config=validate_config,
    setup_provider=setup_provider,
    flow_handler=MeituanOrderSubentryFlow,
    token_url="https://developer.meituan.com/zh/v2/dev/token",
    help_text="请在 QClaw 集成面板中完成美团跑腿助手扫码授权，将 token 填入 auth_token",
    allow_multiple=True,
)
