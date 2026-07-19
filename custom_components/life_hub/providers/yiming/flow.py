"""Yiming phone verification code login flow."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigSubentryFlow, SubentryFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ...provider_flow import _load_channel_titles, _existing_count, _MAX_INSTANCES_PER_PROVIDER
from . import PROVIDER_KEY

_LOGGER = logging.getLogger(__name__)


class YimingProviderSubentryFlow(ConfigSubentryFlow):
    """Phone verification code based setup flow for Yiming."""

    _current: dict[str, Any]

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        if _existing_count(self, self._provider_spec) >= _MAX_INSTANCES_PER_PROVIDER:
            return self.async_abort(reason="max_instances_reached")

        errors: dict[str, str] = {}
        if user_input is not None:
            phone = user_input.get("phone", "").strip()
            if not phone or not phone.isdigit() or len(phone) != 11:
                errors["phone"] = "invalid_phone"
            else:
                self._current = {"phone": phone}
                session = async_get_clientsession(self.hass)
                try:
                    from .api import YimingApi
                    api_client = YimingApi(session, "")
                    if await api_client.send_sms_code(phone):
                        return await self.async_step_verify_code(None)
                    else:
                        errors["base"] = "code_send_failed"
                except Exception as err:
                    _LOGGER.warning("Failed to send verification code: %s", err)
                    errors["base"] = "code_send_failed"

        schema = vol.Schema({
            vol.Required("phone"): str,
        })
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_verify_code(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            code = user_input.get("verification_code", "").strip()
            if not code or not code.isdigit():
                errors["verification_code"] = "invalid_code"
            else:
                session = async_get_clientsession(self.hass)
                try:
                    from .api import YimingApi
                    api_client = YimingApi(session, "")
                    token = await api_client.register_by_sms(self._current["phone"], code)
                    if token:
                        title = "一鸣"
                        try:
                            logged_client = YimingApi(session, token)
                            balance = await logged_client.get_balance()
                            vipname = (balance or {}).get("vipname", "")
                            if vipname:
                                title = f"一鸣 - {vipname}"
                        except Exception:
                            pass
                        return self.async_create_entry(
                            title=title,
                            data={
                                "phone": self._current["phone"],
                                "token": token,
                                "refresh_interval": 30,
                            },
                        )
                    else:
                        errors["verification_code"] = "invalid_code"
                except Exception as err:
                    _LOGGER.warning("Yiming login failed: %s", err)
                    errors["verification_code"] = "invalid_code"

        schema = vol.Schema({
            vol.Required("verification_code"): str,
        })
        return self.async_show_form(
            step_id="verify_code",
            data_schema=schema,
            errors=errors,
            description_placeholders={"phone": self._current.get("phone", "")},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        current_data = dict(subentry.data)

        if user_input is not None:
            action = user_input.get("action", "")
            if action == "re_auth":
                return await self.async_step_reconfigure_phone()
            elif action == "save":
                new_data = {**current_data, "refresh_interval": user_input.get("refresh_interval", current_data.get("refresh_interval", 30))}
                entry = self._get_entry()
                result = self.async_update_and_abort(entry, subentry, data=new_data)

                async def _reload() -> None:
                    await self.hass.config_entries.async_reload(entry.entry_id)

                self.hass.async_create_task(_reload(), "life_hub_yiming_reload")
                return result

        schema = vol.Schema({
            vol.Optional(
                "refresh_interval",
                default=current_data.get("refresh_interval", 30),
            ): vol.All(vol.Coerce(int), vol.Range(min=10, max=1440)),
            vol.Required("action", default="save"): vol.In({"save": "保存设置", "re_auth": "重新登录（更换账号）"}),
        })
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
        )

    async def async_step_reconfigure_phone(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            phone = user_input.get("phone", "").strip()
            if not phone or not phone.isdigit() or len(phone) != 11:
                errors["phone"] = "invalid_phone"
            else:
                self._current = {"phone": phone}
                session = async_get_clientsession(self.hass)
                try:
                    from .api import YimingApi
                    api_client = YimingApi(session, "")
                    if await api_client.send_sms_code(phone):
                        return await self.async_step_reconfigure_verify_code(None)
                    else:
                        errors["base"] = "code_send_failed"
                except Exception as err:
                    _LOGGER.warning("Failed to send verification code: %s", err)
                    errors["base"] = "code_send_failed"

        schema = vol.Schema({
            vol.Required("phone"): str,
        })
        return self.async_show_form(
            step_id="reconfigure_phone",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_reconfigure_verify_code(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            code = user_input.get("verification_code", "").strip()
            if not code or not code.isdigit():
                errors["verification_code"] = "invalid_code"
            else:
                session = async_get_clientsession(self.hass)
                try:
                    from .api import YimingApi
                    api_client = YimingApi(session, "")
                    token = await api_client.register_by_sms(self._current["phone"], code)
                    if token:
                        title = "一鸣"
                        try:
                            logged_client = YimingApi(session, token)
                            balance = await logged_client.get_balance()
                            vipname = (balance or {}).get("vipname", "")
                            if vipname:
                                title = f"一鸣 - {vipname}"
                        except Exception:
                            pass
                        subentry = self._get_reconfigure_subentry()
                        current_data = dict(subentry.data)
                        new_data = {**current_data, "phone": self._current["phone"], "token": token}
                        entry = self._get_entry()
                        result = self.async_update_and_abort(entry, subentry, data=new_data, title=title)

                        async def _reload() -> None:
                            await self.hass.config_entries.async_reload(entry.entry_id)

                        self.hass.async_create_task(_reload(), "life_hub_yiming_reload")
                        return result
                    else:
                        errors["verification_code"] = "invalid_code"
                except Exception as err:
                    _LOGGER.warning("Yiming login failed: %s", err)
                    errors["verification_code"] = "invalid_code"

        schema = vol.Schema({
            vol.Required("verification_code"): str,
        })
        return self.async_show_form(
            step_id="reconfigure_verify_code",
            data_schema=schema,
            errors=errors,
            description_placeholders={"phone": self._current.get("phone", "")},
        )
