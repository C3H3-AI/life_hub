"""美团优惠下单 — 扫码登录 Flow（类似 cn_im_hub 微信登录）。

流程：
1. 生成授权链接/二维码（调用美团 Passport API 或引导用户到 QClaw 扫码）
2. 用户扫描确认
3. 获取 token 并创建子条目
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigSubentryFlow, SubentryFlowResult

_LOGGER = logging.getLogger(__name__)


class MeituanOrderSubentryFlow(ConfigSubentryFlow):
    """美团优惠下单扫码登录 Flow。"""

    VERSION = 1
    _provider_spec: Any
    _current: dict[str, Any]

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """第一步：扫码或填入现有 token。"""

        if user_input is not None:
            token = user_input.get("auth_token", "").strip()
            if token:
                # 手动填入 token
                return self.async_create_entry(
                    title="美团优惠下单",
                    data={"auth_token": token, "refresh_interval": 30},
                )
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({
                    vol.Optional("auth_token", default=""): str,
                }),
                errors={"auth_token": "请输入 token 或前往 QClaw 扫码"},
                description_placeholders={
                    "qr_help": "请前往 QClaw → 集成面板 → 美团跑腿助手完成扫码授权，"
                               "然后将获取到的 token 粘贴到上方输入框中。",
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Optional("auth_token", default=""): str,
            }),
            description_placeholders={
                "qr_help": "请前往 QClaw → 集成面板 → 美团跑腿助手完成扫码授权，"
                           "然后将获取到的 token 粘贴到上方输入框中。",
            },
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """更新配置：替换 token。"""
        subentry = self._get_reconfigure_subentry()
        current_data = dict(subentry.data)

        if user_input is not None:
            new_data = {**current_data, **user_input}
            entry = self._get_entry()
            result = self.async_update_and_abort(entry, subentry, data=new_data)

            async def _reload() -> None:
                await self.hass.config_entries.async_reload(entry.entry_id)

            self.hass.async_create_task(_reload(), "meituan_order_reload")
            return result

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({
                vol.Required("auth_token", default=current_data.get("auth_token", "")): str,
            }),
        )
