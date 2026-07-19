"""Ctrip (WenDao) provider for Life Hub — 使用 QClaw 版问道 API。

配置：填入从 https://www.ctrip.com/wendao/openclaw 获取的 API token。
"""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..base import ProviderSpec
from ...models import ProviderRuntime

_LOGGER = logging.getLogger(__name__)

PROVIDER_KEY = "ctrip"
PROVIDER_NAME = "携程旅行"

CTRIP_API_URL = "https://externalcallback.ctrip.com/skills/api/crew/qclaw/searchInfo"


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
            CTRIP_API_URL,
            json={"inputs": {"token": token, "query": "ping"}},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status == 401:
                raise ValueError("Token 无效 (401)")
            resp.raise_for_status()
            body = await resp.json()
            if not isinstance(body, dict):
                raise ValueError(f"API 返回格式异常: {body}")
    except ValueError:
        raise
    except Exception as err:
        raise ValueError(f"连接失败: {err}") from err


async def setup_provider(
    hass: HomeAssistant,
    config: dict[str, Any],
    subentry_id: str,
) -> ProviderRuntime:
    token = config["api_token"]
    session = async_get_clientsession(hass)
    status = "connected"

    client = CtripClient(session, token)

    async def stop() -> None:
        pass

    def get_status() -> str:
        return status

    async def _health_check() -> bool:
        try:
            await client.query("ping")
            return True
        except Exception as err:
            _LOGGER.warning("Ctrip health check failed: %s", err)
            return False

    return ProviderRuntime(
        key=PROVIDER_KEY, title=PROVIDER_NAME, subentry_id=subentry_id,
        client=client, stop=stop, status=get_status, status_check=_health_check,
    )


class CtripClient:
    def __init__(self, session: aiohttp.ClientSession, token: str) -> None:
        self._session = session
        self._token = token

    async def query(self, query: str) -> str:
        """调用问道 API，返回 Markdown 文本。"""
        async with self._session.post(
            CTRIP_API_URL,
            json={"inputs": {"token": self._token, "query": query}},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            result = data.get("result", data)
            if isinstance(result, dict):
                return result.get("content", str(result))
            return str(result)

    async def search_hotel(self, location: str, **kwargs: Any) -> str:
        q = f"搜索{location}的酒店"
        if budget := kwargs.get("budget"):
            q += f"，预算{budget}元"
        return await self.query(q)


PROVIDER_SPEC = ProviderSpec(
    key=PROVIDER_KEY,
    name=PROVIDER_NAME,
    schema_builder=build_schema,
    validate_config=validate_config,
    setup_provider=setup_provider,
    token_url="http://t.ctrip.cn/28J6RhL",
    help_text="访问链接登录携程账号，申请 API Token 后填入 auth_token",
    allow_multiple=True,
)
