"""Generic provider subentry flow builder."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigSubentryFlow, SubentryFlowResult

from .providers.base import ProviderSpec

_LOGGER = logging.getLogger(__name__)

_TRANSLATIONS_DIR = Path(__file__).parent / "translations"
_TITLE_CACHE: dict[str, dict[str, str]] = {}
_MAX_INSTANCES_PER_PROVIDER = 3


def _load_channel_titles(lang: str) -> dict[str, str]:
    if lang in _TITLE_CACHE:
        return _TITLE_CACHE[lang]
    for candidate in (lang, "en"):
        path = _TRANSLATIONS_DIR / f"{candidate}.json"
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            titles = {k: v.get("channel_title", k) for k, v in data.get("config_subentries", {}).items()}
            _TITLE_CACHE[lang] = titles
            return titles
    return {}


def _next_title(flow: ConfigSubentryFlow, spec: ProviderSpec) -> str:
    titles = _load_channel_titles(flow.hass.config.language)
    base = titles.get(spec.key, spec.name)
    n = _existing_count(flow, spec)
    return base if n == 0 else f"{base} #{n + 1}"


def _get_entry(flow: ConfigSubentryFlow):
    """Get the config entry via HA's built-in subentry flow method.

    NOTE: do NOT use flow.context["entry_id"] — in current HA the subentry
    reconfigure flow does not populate context["entry_id"]; the framework
    manages the entry id on the flow instance via self._entry_id. Using the
    built-in _get_entry() avoids a spurious KeyError that HA retries in a loop.
    """
    try:
        return flow._get_entry()
    except Exception:
        return None


def _get_reconfigure_subentry(flow: ConfigSubentryFlow):
    """Get the subentry being reconfigured via HA's built-in flow method."""
    try:
        return flow._get_reconfigure_subentry()
    except Exception:
        return None


def _existing_count(flow: ConfigSubentryFlow, spec: ProviderSpec) -> int:
    entry = _get_entry(flow)
    if entry is None:
        return 0
    return sum(1 for sub in entry.subentries.values() if sub.subentry_type == spec.key)


def _current_data(flow: ConfigSubentryFlow) -> dict[str, Any]:
    if flow.source == "user":
        return {}
    sub = _get_reconfigure_subentry(flow)
    if sub is None:
        return {}
    return dict(sub.data)


async def _complete(flow: ConfigSubentryFlow, spec: ProviderSpec, data: dict[str, Any]) -> SubentryFlowResult:
    # Get the config entry via flow._entry_id (HA internal property) to avoid
    # the None-return trap in _get_entry(). If _entry_id is somehow invalid,
    # async_get_known_entry will raise a proper error.
    entry_id = flow._entry_id
    entry = flow.hass.config_entries.async_get_known_entry(entry_id)

    if flow.source == "user":
        result = flow.async_create_entry(title=_next_title(flow, spec), data=data)
    else:
        result = flow.async_update_and_abort(entry, _get_reconfigure_subentry(flow), data=data)

    async def _delayed_reload() -> None:
        await flow.hass.config_entries.async_reload(entry.entry_id)

    flow.hass.async_create_task(_delayed_reload(), "life_hub_reload_after_config")
    return result


async def _set_options(flow: ConfigSubentryFlow, spec: ProviderSpec, user_input: dict[str, Any] | None) -> SubentryFlowResult:
    import voluptuous as vol
    errors: dict[str, str] = {}
    current = getattr(flow, "_current", _current_data(flow))
    if user_input is not None:
        current = {**current, **user_input}
        try:
            result = await spec.validate_config(flow.hass, current)
            # If validate_config returns updated data (e.g. token from login), use it
            if isinstance(result, dict):
                current = result
            return await _complete(flow, spec, current)
        except Exception as err:
            _LOGGER.warning("Provider validation failed (%s): %s", spec.key, err)
            errors["base"] = "cannot_connect"

    base_schema = spec.schema_builder(current)
    flow._current = current
    placeholders = {}
    if spec.token_url:
        placeholders["token_url"] = spec.token_url
    if spec.help_text:
        placeholders["help_text"] = spec.help_text
    return flow.async_show_form(
        step_id="set_options", data_schema=base_schema,
        errors=errors, description_placeholders=placeholders,
    )


def build_simple_provider_flow(spec: ProviderSpec) -> type[ConfigSubentryFlow]:
    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        count = _existing_count(self, spec)
        if not spec.allow_multiple and count > 0:
            return self.async_abort(reason="already_configured")
        if spec.allow_multiple and count >= _MAX_INSTANCES_PER_PROVIDER:
            return self.async_abort(reason="max_instances_reached")
        return await async_step_set_options(self, user_input)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        self._current = _current_data(self)
        return await async_step_set_options(self, user_input)

    async def async_step_set_options(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        return await _set_options(self, spec, user_input)

    return type(
        f"{spec.key.title().replace(' ', '')}ProviderSubentryFlow",
        (ConfigSubentryFlow,),
        {
            "_provider_spec": spec,
            "async_step_user": async_step_user,
            "async_step_reconfigure": async_step_reconfigure,
            "async_step_set_options": async_step_set_options,
        },
    )