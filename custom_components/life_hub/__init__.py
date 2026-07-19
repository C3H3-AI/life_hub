"""Life Hub integration for Home Assistant."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .models import HubRuntime
from .providers.registry import get_provider_spec

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 5


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    return True


async def _migrate_subentry_links(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Persistently link existing life_hub entities AND devices to their subentries.

    HA does NOT backfill ``config_subentry_id`` when an entity/device is reloaded,
    so those created before the linkage was added stay orphaned and are shown as
    "not part of this subentry" in the UI.

    IMPORTANT: in this HA version both ``entity_registry.async_update_entity`` and
    ``device_registry.async_update_device`` are SYNC methods that return the updated
    entry/device directly. Awaiting them raises "object can't be awaited" and the
    link is never written, so they must be called WITHOUT await.
    """
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import entity_registry as er

    reg = er.async_get(hass)
    dreg = dr.async_get(hass)

    # Valid subentry ids for this entry (used to validate any parsed candidate)
    valid_subids = {sub.subentry_id for sub in entry.subentries.values()}
    # type -> [sub_id, ...] fallback map (used only when unique_id parsing fails)
    type_to_subids: dict[str, list[str]] = {}
    for sub in entry.subentries.values():
        type_to_subids.setdefault(sub.subentry_type, []).append(sub.subentry_id)

    linked = 0
    for ent in er.async_entries_for_config_entry(reg, entry.entry_id):
        if ent.platform != DOMAIN or ent.config_subentry_id:
            continue
        if not ent.unique_id:
            continue

        sub_id = None
        # Primary: unique_id is "{entry_id}_{type}:{subid}_{suffix}", so the
        # subentry_id is embedded directly and survives multiple same-type subs.
        parts = ent.unique_id.split("_")
        if len(parts) >= 2 and ":" in parts[1]:
            candidate = parts[1].split(":", 1)[1]
            if candidate in valid_subids:
                sub_id = candidate
        # Fallback: resolve via device identifier (DOMAIN, entry_id, sub_type[, subentry_id])
        if sub_id is None and ent.device_id:
            dev = dreg.async_get(ent.device_id)
            if dev is not None:
                for ident in dev.identifiers:
                    ident_list = list(ident)
                    if (
                        len(ident_list) >= 3
                        and ident_list[0] == DOMAIN
                        and ident_list[1] == entry.entry_id
                    ):
                        sub_id = (type_to_subids.get(ident_list[2]) or [None])[0]
                        break

        if sub_id:
            try:
                # `async_update_entity` is a SYNC method in this HA version
                # (returns the RegistryEntry directly); awaiting it raises
                # "RegistryEntry object can't be awaited". Do NOT await it.
                reg.async_update_entity(
                    ent.entity_id, config_subentry_id=sub_id
                )
                linked += 1
            except Exception:  # noqa: BLE001
                _LOGGER.exception(
                    "Failed to link entity %s to subentry %s",
                    ent.entity_id, sub_id,
                )

    # Devices: subentry devices have config_entry_id=None and are linked via
    # config_subentry_id, so async_entries_for_config_entry does NOT return them.
    # Iterate all devices, match by identifier, and call async_update_device with
    # BOTH add_config_entry_id AND add_config_subentry_id (HA raises without the
    # former). This also re-attaches the device to its config_entry.
    dev_linked = 0
    for dev in dreg.devices.values():
        # Match both 3-element (old) and 4-element (new) identifiers
        def _dev_ident_matches(ident) -> bool:
            if not isinstance(ident, (tuple, frozenset)):
                return False
            ident_list = list(ident)
            return len(ident_list) >= 3 and ident_list[0] == DOMAIN and ident_list[1] == entry.entry_id
        if not any(_dev_ident_matches(ident) for ident in dev.identifiers):
            continue
        # DeviceEntry has NO config_subentry_id attribute in this HA version;
        # the link lives in config_entries_subentries[entry_id] (a set).
        # async_update_device(add_config_subentry_id=...) is idempotent, so we
        # simply (re)apply it for every matching device.
        sub_type = None
        sub_id = None
        for ident in dev.identifiers:
            ident_list = list(ident)
            if (
                len(ident_list) >= 3
                and ident_list[0] == DOMAIN
                and ident_list[1] == entry.entry_id
            ):
                sub_type = ident_list[2]
                # For 4-element identifiers, extract subentry_id directly
                if len(ident_list) >= 4:
                    sub_id = ident_list[3]
                break
        if sub_id is None:
            sub_id = (type_to_subids.get(sub_type) or [None])[0]
        if sub_id:
            try:
                # In this HA version `async_update_device` is a SYNC method that
                # returns the updated DeviceEntry directly. Awaiting it raises
                # "DeviceEntry object can't be awaited" and the link is never
                # written, so do NOT await it.

                # Remove any existing subentries for this config entry that
                # don't match the correct sub_id (add_config_subentry_id is
                # additive, so old wrong links would persist otherwise).
                existing = dev.config_entries_subentries.get(entry.entry_id, [])
                for old_sub_id in list(existing):
                    if old_sub_id != sub_id:
                        dreg.async_update_device(
                            dev.id,
                            remove_config_subentry_id=old_sub_id,
                        )

                dreg.async_update_device(
                    dev.id,
                    add_config_entry_id=entry.entry_id,
                    add_config_subentry_id=sub_id,
                )
                dev_linked += 1
            except Exception:  # noqa: BLE001
                _LOGGER.exception(
                    "Failed to link device %s to subentry %s",
                    dev.id, sub_id,
                )

    _LOGGER.warning(
        "life_hub migrate: linked %d orphaned entities and %d devices to their subentries",
        linked, dev_linked,
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    runtimes = {}
    failed_subentries: list[str] = []

    _LOGGER.debug("async_setup_entry started, subentries count=%d", len(entry.subentries))
    for sub_id, sub in entry.subentries.items():
        _LOGGER.debug("subentry %s: type=%s title=%s", sub_id, sub.subentry_type, sub.title)

    for sub in entry.subentries.values():
        # 通过 get_provider_spec 解析历史别名（如 meituan_travel -> meituan），保留原 token
        spec = get_provider_spec(sub.subentry_type)
        if spec is None:
            _LOGGER.warning("Unknown provider in subentry: %s", sub.subentry_type)
            continue

        rt = None
        last_error: Exception | None = None
        for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
            try:
                rt = await spec.setup_provider(
                    hass, dict(sub.data), subentry_id=sub.subentry_id,
                )
                rt.title = sub.title
                break
            except Exception as err:
                last_error = err
                _LOGGER.warning(
                    "Provider %s setup failed (attempt %d/%d): %s",
                    sub.subentry_type, attempt, MAX_RETRY_ATTEMPTS, err,
                )
                if attempt < MAX_RETRY_ATTEMPTS:
                    await asyncio.sleep(RETRY_DELAY_SECONDS)

        if rt is not None:
            rt.subentry_type = sub.subentry_type
            rt.refresh_interval = sub.data.get("refresh_interval", 30)
            runtimes[f"{sub.subentry_type}:{sub.subentry_id}"] = rt
        else:
            failed_subentries.append(sub.title or sub.subentry_type)
            _LOGGER.error(
                "Provider %s failed after %d attempts: %s",
                sub.subentry_type, MAX_RETRY_ATTEMPTS, last_error,
            )

    if failed_subentries:
        _LOGGER.error("Failed providers: %s", ", ".join(failed_subentries))

    entry.runtime_data = HubRuntime(providers=runtimes)

    # Build O(1) client lookup map for services.py
    hass.data[DOMAIN]["client_map"] = {
        f"{rt.subentry_type}:{sid}": (rt.client, rt)
        for sid, rt in runtimes.items()
        if hasattr(rt, "client") and rt.client is not None
    }

    # Clean up stale devices — only remove devices for subentry types that
    # no longer exist in the config at all (user deleted the subentry).
    # Devices for subentries that merely failed to set up are preserved so
    # they can be linked when the provider succeeds on the next restart.
    active_subentry_types = {sub.subentry_type for sub in entry.subentries.values()}
    active_subentry_ids = {sub.subentry_id for sub in entry.subentries.values()}
    dev_reg = dr.async_get(hass)

    # Phase 1: Remove devices for subentry types that no longer exist.
    # Phase 2: Deduplicate — when both 3-element (old) and 4-element (new)
    #          devices exist for the same subentry type, remove the old one.
    # Phase 3: Remove devices whose 4-element identifier points to a subentry
    #          that no longer exists (user deleted the subentry from config).
    type_to_dev_ids: dict[str, set[str]] = {}  # subentry_type -> {device_id}
    type_to_old_dev_ids: dict[str, set[str]] = {}  # subentry_type -> {device_id} (3-element identifiers)

    for dev in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        _sub_type = None
        _is_new = False
        _sub_id = None
        for ident in dev.identifiers:
            if not isinstance(ident, (tuple, frozenset)):
                continue
            ident_list = list(ident)
            if (
                len(ident_list) >= 3
                and ident_list[0] == DOMAIN
                and ident_list[1] == entry.entry_id
                and ident_list[2] in active_subentry_types
            ):
                _sub_type = ident_list[2]
                _is_new = len(ident_list) >= 4
                if _is_new:
                    _sub_id = ident_list[3]
                break
        if _sub_type is None:
            # Type no longer exists — remove the device entirely
            dev_reg.async_remove_device(dev.id)
        elif _is_new and _sub_id and _sub_id not in active_subentry_ids:
            # Phase 3: Subentry was deleted from config but device survived
            dev_reg.async_remove_device(dev.id)
        elif _is_new:
            type_to_dev_ids.setdefault(_sub_type, set()).add(dev.id)
        else:
            type_to_old_dev_ids.setdefault(_sub_type, set()).add(dev.id)

    # Phase 2: Remove old 3-element devices if a new 4-element device exists
    for sub_type, old_ids in type_to_old_dev_ids.items():
        if sub_type in type_to_dev_ids:
            for dev_id in old_ids:
                dev_reg.async_remove_device(dev_id)

    # Try to preload the sensor module to ensure it's available
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        _LOGGER.debug("async_forward_entry_setups completed")
    except Exception as exc:
        _LOGGER.debug("async_forward_entry_setups failed: %s", exc)

    # Verify sensor platform was set up by checking if any entities were added
    from homeassistant.helpers import entity_registry as er
    reg = er.async_get(hass)
    entry_entities = er.async_entries_for_config_entry(reg, entry.entry_id)
    _LOGGER.debug("entities after forward_setup: %d", len(entry_entities))
    for ent in entry_entities[:5]:
        _LOGGER.debug("  entity: %s platform=%s", ent.entity_id, ent.platform)

    # Setup services for all providers
    from .services import async_setup_services
    await async_setup_services(hass)
    _LOGGER.debug("async_setup_services completed, runtimes=%d", len(runtimes))

    # Persistently link existing entities AND devices to their subentries (HA
    # does not backfill config_subentry_id on reload, so orphaned ones stay
    # shown as "not part of this subentry" in the UI).
    await _migrate_subentry_links(hass, entry)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    for rt in entry.runtime_data.providers.values():
        try:
            result = rt.stop()
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            _LOGGER.exception("Error stopping provider %s", rt.key)

    # 清理所有注册的 service，避免卸载后残留
    for svc_name in list(hass.services.async_services_for_domain(DOMAIN)):
        hass.services.async_remove(DOMAIN, svc_name)

    # 清理 client_map
    hass.data[DOMAIN].pop("client_map", None)

    return unload_ok