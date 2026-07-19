"""MCP JSON-RPC 2.0 client base class.

Shared by fliggy, mcdonalds, and any future MCP providers.
Reduces _call_tool boilerplate to a single `_do_rpc()` hook.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)


class McpClientBase:
    """Base class for MCP JSON-RPC 2.0 providers.

    Subclasses must implement:
        _build_headers(self, body: str) -> dict[str, str]
    Optionally override:
        _do_rpc(self, body: str, headers: dict) -> dict  (default: POST body as string)
    """

    def __init__(self, session: aiohttp.ClientSession, endpoint: str) -> None:
        self._session = session
        self._endpoint = endpoint

    # ── override point: headers ────────────────────────────────────────────

    def _build_headers(self, body: str) -> dict[str, str]:
        """Return HTTP headers for a JSON-RPC request."""
        return {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

    # ── override point: transport (body serialization) ────────────────────

    async def _do_rpc(self, body: str, headers: dict[str, str]) -> dict:
        """Execute the JSON-RPC POST and return the parsed response dict.

        Default: POST with raw body string. Override if the provider uses
        aiohttp's ``json=`` kwarg or requires a different transport.
        """
        async with self._session.post(
            self._endpoint,
            headers=headers,
            data=body,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    # ── public API ─────────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        """Verify the MCP endpoint is reachable by listing tools."""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {},
        }
        body = json.dumps(payload, separators=(",", ":"))
        headers = self._build_headers(body)
        try:
            resp = await self._do_rpc(body, headers)
            return resp.get("result", {}).get("tools") is not None
        except Exception:
            return False

    async def call_tool(self, tool_name: str, arguments: dict | None = None) -> dict:
        """Send a JSON-RPC 2.0 tools/call request.

        Returns the full response dict. Use ``parse_mcp_content()`` to extract
        the inline text payload.
        """
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments or {}},
        }
        body = json.dumps(payload, separators=(",", ":"))
        headers = self._build_headers(body)
        return await self._do_rpc(body, headers)


def parse_mcp_content(response: dict) -> dict | list | None:
    """Extract content from an MCP JSON-RPC response.

    Tries, in order:
      1. ``content[].text`` parsed as JSON (common for structured tool results).
      2. ``structuredContent`` (some MCP servers put the real data here while
         ``content`` only carries a human-readable markdown description).
      3. the raw ``content[].text`` string if it isn't valid JSON.

    Returns a dict/list (parsed), a string (raw text), or None.
    """
    result = response.get("result", {})
    content = result.get("content", [])
    if content and isinstance(content, list):
        for item in content:
            if item.get("type") == "text":
                try:
                    return json.loads(item["text"])
                except (json.JSONDecodeError, KeyError, TypeError):
                    # 文本非 JSON（如 MCP 返回说明性 markdown），退回结构化内容
                    pass
    # 回退：优先使用结构化内容（部分 MCP 真数据在此）
    sc = result.get("structuredContent")
    if sc is not None:
        return sc
    # 最后兜底：若 content 文本未能解析为 JSON，返回原始文本
    if content and isinstance(content, list):
        for item in content:
            if item.get("type") == "text":
                return item.get("text")
    return None
