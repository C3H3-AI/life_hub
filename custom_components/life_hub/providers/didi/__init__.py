"""滴滴出行 MCP Provider for Life Hub.

接入滴滴 MCP 服务，支持查车型、预估价格、创建/查询/取消订单、获取司机位置。

Token 获取：访问 https://mcp.didichuxing.com/ 登录后激活获取 DIDI_KEY。

注意：滴滴 MCP 使用 Streamable HTTP 协议（JSON-RPC 2.0 over HTTP POST）。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.core import HomeAssistant
# 不再使用 HA async_get_clientsession — HomeAssistantTCPConnector 对滴滴 DNS 解析会挂

from ..base import ProviderSpec
from ...models import ProviderRuntime

_LOGGER = logging.getLogger(__name__)

PROVIDER_KEY = "didi"
PROVIDER_NAME = "滴滴出行"

DIDI_MCP_BASE = "https://mcp.didichuxing.com/mcp-servers"
DIDI_MCP_HEADERS = {"Content-Type": "application/json; charset=utf-8"}


def build_schema(current: dict[str, Any]) -> vol.Schema:
    return vol.Schema({
        vol.Required("api_key", default=current.get("api_key", "")): str,
        vol.Optional("refresh_interval", default=current.get("refresh_interval", 30)): vol.All(
            vol.Coerce(int), vol.Range(min=10, max=1440)
        ),
    })


async def validate_config(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """验证 DIDI_KEY — 调用 tools/list 测试连通性。"""
    key = data.get("api_key", "")
    if not key:
        raise ValueError("api_key is required（请前往 https://mcp.didichuxing.com/ 获取）")
    session = aiohttp.ClientSession()
    url = f"{DIDI_MCP_BASE}?key={key}"
    payload = {
        "jsonrpc": "2.0", "method": "tools/list", "id": 1,
        "params": {"_meta": {"progressToken": 1}},
    }
    try:
        async with session.post(
            url, json=payload,
            headers=DIDI_MCP_HEADERS,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status == 401 or resp.status == 403:
                raise ValueError("DIDI_KEY 无效")
            resp.raise_for_status()
            body = await resp.json()
            if body.get("error"):
                raise ValueError(f"API 错误: {body['error'].get('message', 'unknown')}")
            if "result" not in body:
                raise ValueError("服务器返回格式异常")
    except ValueError:
        raise
    except asyncio.TimeoutError:
        raise ValueError("连接超时")
    except Exception as err:
        raise ValueError(f"连接失败: {err}") from err
    finally:
        await session.close()


async def setup_provider(
    hass: HomeAssistant,
    config: dict[str, Any],
    subentry_id: str,
) -> ProviderRuntime:
    api_key = config["api_key"]
    status = "connected"

    client = DidiClient(api_key)

    async def stop() -> None:
        await client.close()

    def get_status() -> str:
        return status

    async def _health_check() -> bool:
        try:
            await client.call_tool("taxi_estimate", {
                "from_lng": "116.397128", "from_lat": "39.916527",
                "from_name": "北京", "to_lng": "116.407396", "to_lat": "39.904200",
                "to_name": "天安门",
            })
            return True
        except Exception as err:
            _LOGGER.warning("Didi health check failed: %s", err)
            return False

    return ProviderRuntime(
        key=PROVIDER_KEY, title=PROVIDER_NAME, subentry_id=subentry_id,
        client=client, stop=stop, status=get_status, status_check=_health_check,
    )


class DidiClient:
    """滴滴 MCP 客户端。

    使用 Streamable HTTP 协议（JSON-RPC 2.0 over HTTP POST）。
    使用独立 aiohttp session 避免 HA HomeAssistantTCPConnector 的 DNS 解析问题。
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._base_url = f"{DIDI_MCP_BASE}?key={api_key}"
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
        )

    async def close(self) -> None:
        await self._session.close()

    async def call_tool(self, tool_name: str, arguments: dict | None = None) -> dict:
        """调用滴滴 MCP 工具（Streamable HTTP 协议，自动重试 HTTP 202）。"""
        payload = {
            "jsonrpc": "2.0", "method": "tools/call", "id": 1,
            "params": {
                "name": tool_name, "arguments": arguments or {},
                "_meta": {"progressToken": 1},
            },
        }

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            async with self._session.post(
                self._base_url, json=payload,
                headers=DIDI_MCP_HEADERS,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                # HTTP 202 Accepted — Streamable HTTP 异步处理中，等待后重试
                if resp.status == 202:
                    if attempt < max_retries:
                        _LOGGER.debug(
                            "Didi MCP returned 202 (attempt %d/%d), retrying in 1s...",
                            attempt, max_retries,
                        )
                        await asyncio.sleep(1)
                        continue
                    text = await resp.text()
                    _LOGGER.warning(
                        "Didi MCP still returning 202 after %d retries: %s",
                        max_retries, text[:200],
                    )
                    raise ValueError(
                        f"滴滴 MCP 服务暂时繁忙（HTTP 202），请稍后重试"
                    )

                resp.raise_for_status()
                try:
                    body = await resp.json()
                except (aiohttp.ContentTypeError, ValueError) as err:
                    text = await resp.text()
                    _LOGGER.warning("Didi MCP non-JSON response (HTTP %s): %s", resp.status, text[:200])
                    raise ValueError(f"Didi MCP returned non-JSON response (HTTP {resp.status}): {text[:100]}") from err
                if body.get("error"):
                    raise ValueError(f"Didi MCP error: {body['error'].get('message', 'unknown')}")
                return body.get("result", body)

        raise RuntimeError("unreachable")

    async def taxi_estimate(self, from_lng: str, from_lat: str, from_name: str,
                             to_lng: str, to_lat: str, to_name: str) -> dict:
        return await self.call_tool("taxi_estimate", {
            "from_lng": from_lng, "from_lat": from_lat, "from_name": from_name,
            "to_lng": to_lng, "to_lat": to_lat, "to_name": to_name,
        })

    async def taxi_create_order(self, estimate_trace_id: str, product_category: str,
                                 caller_car_phone: str | None = None) -> dict:
        args = {"estimate_trace_id": estimate_trace_id, "product_category": product_category}
        if caller_car_phone:
            args["caller_car_phone"] = caller_car_phone
        return await self.call_tool("taxi_create_order", args)

    async def taxi_query_order(self, order_id: str | None = None) -> dict:
        args = {}
        if order_id:
            args["order_id"] = order_id
        return await self.call_tool("taxi_query_order", args)

    async def taxi_cancel_order(self, order_id: str, reason: str | None = None) -> dict:
        args = {"order_id": order_id}
        if reason:
            args["reason"] = reason
        return await self.call_tool("taxi_cancel_order", args)

    async def taxi_get_driver_location(self, order_id: str) -> dict:
        return await self.call_tool("taxi_get_driver_location", {"order_id": order_id})

    async def taxi_generate_ride_app_link(self, from_lng: str, from_lat: str,
                                           to_lng: str, to_lat: str,
                                           product_category: str | None = None) -> dict:
        args = {"from_lng": from_lng, "from_lat": from_lat, "to_lng": to_lng, "to_lat": to_lat}
        if product_category:
            args["product_category"] = product_category
        return await self.call_tool("taxi_generate_ride_app_link", args)

    async def maps_textsearch(self, keywords: str, city: str,
                               location: str | None = None,
                               show_fields: str | None = None) -> dict:
        args = {"keywords": keywords, "city": city}
        if location:
            args["location"] = location
        if show_fields:
            args["show_fields"] = show_fields
        return await self.call_tool("maps_textsearch", args)

    async def maps_place_around(self, keywords: str, location: str,
                                 max_distance: str | None = None) -> dict:
        args = {"keywords": keywords, "location": location}
        if max_distance:
            args["max_distance"] = max_distance
        return await self.call_tool("maps_place_around", args)

    async def maps_regeocode(self, location: str) -> dict:
        return await self.call_tool("maps_regeocode", {"location": location})

    async def maps_direction_driving(self, origin: str, destination: str,
                                      need_geo: bool | None = None) -> dict:
        args = {"origin": origin, "destination": destination}
        if need_geo is not None:
            args["need_geo"] = need_geo
        return await self.call_tool("maps_direction_driving", args)

    async def maps_direction_transit(self, origin: str, destination: str,
                                      city: str) -> dict:
        return await self.call_tool("maps_direction_transit", {
            "origin": origin, "destination": destination, "city": city,
        })

    async def maps_direction_walking(self, origin: str, destination: str,
                                      need_geo: bool | None = None) -> dict:
        args = {"origin": origin, "destination": destination}
        if need_geo is not None:
            args["need_geo"] = need_geo
        return await self.call_tool("maps_direction_walking", args)

    async def maps_direction_bicycling(self, origin: str, destination: str,
                                        need_geo: bool | None = None) -> dict:
        args = {"origin": origin, "destination": destination}
        if need_geo is not None:
            args["need_geo"] = need_geo
        return await self.call_tool("maps_direction_bicycling", args)


PROVIDER_SPEC = ProviderSpec(
    key=PROVIDER_KEY,
    name=PROVIDER_NAME,
    schema_builder=build_schema,
    validate_config=validate_config,
    setup_provider=setup_provider,
    token_url="https://mcp.didichuxing.com/",
    help_text="前往滴滴 MCP 官网登录后激活获取 DIDI_KEY",
    allow_multiple=True,
)
