"""同程旅行 provider for Life Hub（同程程心 API）。

登录方式：连接登录（同程程心授权）。
请在 QClaw 中完成授权后，将获取到的 token 填入 auth_token 字段。
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

PROVIDER_KEY = "tongcheng"
PROVIDER_NAME = "同程旅行"

TONGCHENG_API_BASE = "https://m.ly.com"


def build_schema(current: dict[str, Any]) -> vol.Schema:
    return vol.Schema({
        vol.Required("auth_token", default=current.get("auth_token", "")): str,
        vol.Optional("refresh_interval", default=current.get("refresh_interval", 30)): vol.All(
            vol.Coerce(int), vol.Range(min=10, max=1440)
        ),
    })


async def validate_config(hass: HomeAssistant, data: dict[str, Any]) -> None:
    token = data.get("auth_token", "")
    if not token:
        raise ValueError("auth_token is required（请先在 QClaw 中完成同程程心授权）")
    session = async_get_clientsession(hass)
    try:
        async with session.get(
            f"{TONGCHENG_API_BASE}/api/member/user/info",
            headers={"Authorization": f"Bearer {token}"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status == 401:
                raise ValueError("Token 无效 (401)，请重新授权")
            resp.raise_for_status()
    except ValueError:
        raise
    except Exception as err:
        raise ValueError(f"Connection failed: {err}") from err


async def setup_provider(
    hass: HomeAssistant,
    config: dict[str, Any],
    subentry_id: str,
) -> ProviderRuntime:
    token = config["auth_token"]
    session = async_get_clientsession(hass)
    status = "connected"

    client = TongchengClient(session, token)

    async def stop() -> None:
        pass

    def get_status() -> str:
        return status

    async def _health_check() -> bool:
        try:
            await client.get_user_info()
            return True
        except Exception as err:
            _LOGGER.warning("Tongcheng health check failed: %s", err)
            return False

    return ProviderRuntime(
        key=PROVIDER_KEY, title=PROVIDER_NAME, subentry_id=subentry_id,
        client=client, stop=stop, status=get_status, status_check=_health_check,
    )


class TongchengClient:
    def __init__(self, session: aiohttp.ClientSession, token: str) -> None:
        self._session = session
        self._token = token
        self._headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async def _req(self, method: str, path: str, **kwargs: Any) -> dict:
        url = f"{TONGCHENG_API_BASE}{path}"
        async with self._session.request(
            method, url, headers=self._headers,
            timeout=aiohttp.ClientTimeout(total=15), **kwargs,
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def get_user_info(self) -> dict:
        return await self._req("GET", "/api/member/user/info")

    async def search_hotel(self, city: str, **kwargs: Any) -> dict:
        params = {"city": city}
        if check_in := kwargs.get("check_in"):
            params["checkIn"] = check_in
        if check_out := kwargs.get("check_out"):
            params["checkOut"] = check_out
        if budget := kwargs.get("budget"):
            params["maxPrice"] = budget
        return await self._req("GET", "/api/hotel/search", params=params)

    async def search_flight(self, **kwargs: Any) -> dict:
        params = {}
        if origin := kwargs.get("origin"):
            params["departureCity"] = origin
        if destination := kwargs.get("destination"):
            params["arrivalCity"] = destination
        if date := kwargs.get("date"):
            params["departureDate"] = date
        return await self._req("GET", "/api/flight/search", params=params)

    async def get_orders(self) -> list:
        body = await self._req("GET", "/api/member/order/list")
        return body.get("data", {}).get("list", [])


PROVIDER_SPEC = ProviderSpec(
    key=PROVIDER_KEY,
    name=PROVIDER_NAME,
    schema_builder=build_schema,
    validate_config=validate_config,
    setup_provider=setup_provider,
    docs_url="https://qclaw.qq.com/docs/chengxin",
    token_url="https://www.ly.com",
    help_text="在同程程心 QClaw 集成面板完成授权后，将 token 粘贴到 auth_token 字段",
    allow_multiple=True,
)