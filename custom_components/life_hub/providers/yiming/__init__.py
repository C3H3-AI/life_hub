"""Yiming (一鸣真鲜奶吧) provider for Life Hub."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..base import ProviderSpec
from ...models import ProviderRuntime

_LOGGER = logging.getLogger(__name__)

PROVIDER_KEY = "yiming"
PROVIDER_NAME = "一鸣真鲜奶吧"


def build_schema(current: dict[str, Any]) -> vol.Schema:
    return vol.Schema({
        vol.Required("phone", default=current.get("phone", "")): str,
        vol.Optional("verification_code", default=current.get("verification_code", "")): str,
        vol.Optional("refresh_interval", default=current.get("refresh_interval", 30)): vol.All(
            vol.Coerce(int), vol.Range(min=10, max=1440)
        ),
    })


async def validate_config(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any] | None:
    """Validate config. Only checks token validity if token exists.
    
    Login operations (SMS sending, token exchange) are handled by flow.py.
    """
    token = data.get("token", "")
    phone = data.get("phone", "")
    
    if not token and not phone:
        raise ValueError("请填写手机号或 Token")
    
    # If token exists, validate it
    if token:
        from .api import YimingApi
        session = async_get_clientsession(hass)
        client = YimingApi(session, token)
        try:
            await client.get_user_info()
        except Exception as err:
            raise ValueError(f"Token 验证失败: {err}")
    
    return None


async def setup_provider(
    hass: HomeAssistant,
    config: dict[str, Any],
    subentry_id: str,
) -> ProviderRuntime:
    token = config.get("token", "")
    session = async_get_clientsession(hass)
    status = "connected"

    from .api import YimingApi
    client = YimingApi(session, token)

    async def stop() -> None:
        pass

    def get_status() -> str:
        return status

    async def _health_check() -> bool:
        try:
            await client.get_user_info()
            return True
        except Exception as err:
            _LOGGER.warning("Yiming health check failed: %s", err)
            return False

    return ProviderRuntime(
        key=PROVIDER_KEY, title=PROVIDER_NAME, subentry_id=subentry_id,
        client=client, stop=stop, status=get_status, status_check=_health_check,
    )


from .flow import YimingProviderSubentryFlow

PROVIDER_SPEC = ProviderSpec(
    key=PROVIDER_KEY,
    name=PROVIDER_NAME,
    schema_builder=build_schema,
    validate_config=validate_config,
    setup_provider=setup_provider,
    allow_multiple=True,
    flow_handler=YimingProviderSubentryFlow,
)
