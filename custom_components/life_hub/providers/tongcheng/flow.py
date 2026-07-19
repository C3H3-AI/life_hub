"""同程程心 OAuth 链接登录 flow。"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigSubentryFlow, SubentryFlowResult

_LOGGER = logging.getLogger(__name__)

PROVIDER_KEY = "tongcheng"
PROVIDER_NAME = "同程旅行"

AUTH_URL = (
    "https://m.ly.com/memberauth/oauth2/authorize"
    "?client_id=qclaw-288267139f9f1d"
    "&redirect_uri=https%3A%2F%2Fauth.ap-guangzhou.tencentags.com"
    "%2Fidentities%2Foauth2%2Fcallback%2F2d131483-3941-424d-8b9b-21b368953736"
    "&response_type=code&scope=read%20write"
)


class TongchengSubentryFlow(ConfigSubentryFlow):
    """链接登录 flow for 同程旅行."""

    _current: dict[str, Any]

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        self._current = {}
        return await self.async_step_auth_link(None)

    async def async_step_auth_link(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if user_input is not None:
            return await self.async_step_set_token(None)

        return self.async_show_form(
            step_id="auth_link",
            data_schema=vol.Schema({}),
            description_placeholders={
                "auth_url": AUTH_URL,
            },
        )

    async def async_step_set_token(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            token = user_input.get("auth_token", "").strip()
            if not token:
                errors["auth_token"] = "token_required"
            if not errors:
                return self.async_create_entry(
                    title=PROVIDER_NAME,
                    data={
                        "auth_token": token,
                        "refresh_interval": user_input.get("refresh_interval", 30),
                    },
                )

        return self.async_show_form(
            step_id="set_token",
            data_schema=vol.Schema({
                vol.Required("auth_token"): str,
                vol.Optional("refresh_interval", default=30): vol.All(
                    vol.Coerce(int), vol.Range(min=10, max=1440)
                ),
            }),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        current_data = dict(subentry.data)

        if user_input is not None:
            new_data = {
                **current_data,
                "auth_token": user_input.get("auth_token", current_data.get("auth_token", "")),
                "refresh_interval": user_input.get("refresh_interval", current_data.get("refresh_interval", 30)),
            }
            entry = self._get_entry()
            result = self.async_update_and_abort(entry, subentry, data=new_data)

            async def _reload() -> None:
                await self.hass.config_entries.async_reload(entry.entry_id)

            self.hass.async_create_task(_reload(), "life_hub_tongcheng_reload")
            return result

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({
                vol.Required("auth_token", default=current_data.get("auth_token", "")): str,
                vol.Optional("refresh_interval", default=current_data.get("refresh_interval", 30)): vol.All(
                    vol.Coerce(int), vol.Range(min=10, max=1440)
                ),
            }),
        )
