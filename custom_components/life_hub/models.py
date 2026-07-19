"""Data models for Life Hub."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ProviderRuntime:
    """Runtime state for a single provider instance."""

    key: str
    title: str = ""
    subentry_id: str = ""
    subentry_type: str = ""
    client: Any = None
    stop: Callable[[], Any] = None
    status: Callable[[], str] = None
    refresh_interval: int = 30
    sensors: dict[str, Any] = field(default_factory=dict)
    status_check: Callable[[], Awaitable[bool]] | None = None


@dataclass(slots=True)
class HubRuntime:
    """Runtime state for the entire hub."""

    providers: dict[str, ProviderRuntime]