"""Music provider for Life Hub (QQ音乐 / 网易云音乐)."""

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

PROVIDER_KEY = "music"
PROVIDER_NAME = "音乐"

MUSIC_PLATFORMS = {
    "qq": "QQ音乐",
    "netease": "网易云音乐",
    "kugou": "酷狗音乐",
    "kuwo": "酷我音乐",
}

QQMUSIC_API_BASE = "https://u.y.qq.com/cgi-bin/musicu.fcg"


def build_schema(current: dict[str, Any]) -> vol.Schema:
    return vol.Schema({
        vol.Required("platform", default=current.get("platform", "qq")): vol.In(MUSIC_PLATFORMS),
        vol.Optional("api_key", default=current.get("api_key", "")): str,
        vol.Optional("cookie", default=current.get("cookie", "")): str,
        vol.Optional("refresh_interval", default=current.get("refresh_interval", 30)): vol.All(
            vol.Coerce(int), vol.Range(min=10, max=1440)
        ),
    })


async def validate_config(hass: HomeAssistant, data: dict[str, Any]) -> None:
    platform = data.get("platform", "qq")
    if platform not in MUSIC_PLATFORMS:
        raise ValueError(f"不支持的平台: {platform}")
    session = async_get_clientsession(hass)
    try:
        if platform == "qq":
            api_key = data.get("api_key", "")
            cookie = data.get("cookie", "")
            if not api_key and not cookie:
                raise ValueError("QQ音乐需要填写 API Key 或 Cookie")
            headers = {"Referer": "https://y.qq.com/"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            if cookie:
                headers["Cookie"] = cookie
            payload = {
                "comm": {"ct": 24, "cv": 0},
                "req_1": {
                    "module": "music.search.SearchCgiService",
                    "method": "DoSearchForQQMusicDesktop",
                    "param": {"query": "test", "page_size": 1, "page_num": 1},
                },
            }
            async with session.post(
                QQMUSIC_API_BASE, json=payload, headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 401:
                    raise ValueError("QQ音乐凭据无效，请检查 API Key 或 Cookie")
                resp.raise_for_status()
                body = await resp.json()
                if body.get("code") != 0:
                    raise ValueError(f"QQ音乐验证失败: {body.get('message', '未知错误')}")
        else:
            _LOGGER.info("平台 %s 暂无需验证，将使用本地模式", MUSIC_PLATFORMS.get(platform))
    except ValueError:
        raise
    except Exception as err:
        raise ValueError(f"连接失败: {err}") from err


async def setup_provider(
    hass: HomeAssistant,
    config: dict[str, Any],
    subentry_id: str,
) -> ProviderRuntime:
    platform = config["platform"]
    api_key = config.get("api_key", "")
    cookie = config.get("cookie", "")
    session = async_get_clientsession(hass)
    status = "connected"

    client = MusicClient(session, platform, api_key, cookie)

    async def stop() -> None:
        pass

    def get_status() -> str:
        return status

    async def _health_check() -> bool:
        try:
            await client.search_songs("test", 1)
            return True
        except Exception as err:
            _LOGGER.warning("Music health check failed: %s", err)
            return False

    return ProviderRuntime(
        key=PROVIDER_KEY, title=MUSIC_PLATFORMS[platform], subentry_id=subentry_id,
        client=client, stop=stop, status=get_status, status_check=_health_check,
    )


class MusicClient:
    def __init__(
        self, session: aiohttp.ClientSession, platform: str,
        api_key: str = "", cookie: str = "",
    ) -> None:
        self._session = session
        self._platform = platform
        self._api_key = api_key
        self._cookie = cookie

    @property
    def platform_name(self) -> str:
        return MUSIC_PLATFORMS.get(self._platform, self._platform)

    async def _qq_request(self, module: str, method: str, param: dict) -> dict:
        """Call QQ Music API."""
        headers = {"Referer": "https://y.qq.com/"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        if self._cookie:
            headers["Cookie"] = self._cookie

        payload = {
            "comm": {"ct": 24, "cv": 0},
            "req_1": {"module": module, "method": method, "param": param},
        }
        async with self._session.post(
            QQMUSIC_API_BASE, json=payload, headers=headers,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            body = await resp.json()
            return body.get("req_1", {})

    async def search_songs(self, keyword: str, limit: int = 10) -> list:
        """Search songs on QQ Music."""
        if self._platform != "qq":
            return [{"platform": self.platform_name, "note": "仅QQ音乐支持搜索"}]
        result = await self._qq_request(
            "music.search.SearchCgiService", "DoSearchForQQMusicDesktop",
            {"query": keyword, "page_size": limit, "page_num": 1},
        )
        return result.get("data", {}).get("body", {}).get("song", {}).get("list", [])

    async def get_playlist(self, category: str = "全部", limit: int = 20) -> list:
        """Get QQ Music playlists."""
        if self._platform != "qq":
            return []
        result = await self._qq_request(
            "music.playlist.PlaylistBase", "get_category_list", {},
        )
        return result.get("data", {}).get("list", [])[:limit]

    async def get_ranking(self) -> list:
        """Get QQ Music ranking lists."""
        if self._platform != "qq":
            return []
        result = await self._qq_request(
            "music.toplist.Toplist", "get_all", {},
        )
        return result.get("data", {}).get("group", [])

    async def get_recommendations(self) -> list:
        """Get recommended songs."""
        if self._platform != "qq":
            return []
        result = await self._qq_request(
            "music.recommend.Recommend", "get_recommend_songs", {},
        )
        return result.get("data", {}).get("song", [])


PROVIDER_SPEC = ProviderSpec(
    key=PROVIDER_KEY,
    name=PROVIDER_NAME,
    schema_builder=build_schema,
    validate_config=validate_config,
    setup_provider=setup_provider,
    allow_multiple=True,
)