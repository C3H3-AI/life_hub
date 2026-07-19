"""Gaode Maps (高德地图) provider for Life Hub.

基于 ha_gaode_server 实现，提供：
- GPSLogger 数据存储
- GCJ-02 坐标转换
- 距离计算
- 多边形范围计算
- 设备追踪器配置
"""

from __future__ import annotations

import logging
import math
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..base import ProviderSpec
from ...models import ProviderRuntime

_LOGGER = logging.getLogger(__name__)

PROVIDER_KEY = "gaode"
PROVIDER_NAME = "高德地图"

GAODE_API_BASE = "https://restapi.amap.com"
GAODE_SERVER_API = "https://restapi.amap.com/v5"


def build_schema(current: dict[str, Any]) -> vol.Schema:
    return vol.Schema({
        vol.Required("api_key", default=current.get("api_key", "")): str,
        vol.Optional("security_code", default=current.get("security_code", "")): str,
        vol.Optional("refresh_interval", default=current.get("refresh_interval", 30)): vol.All(
            vol.Coerce(int), vol.Range(min=10, max=1440)
        ),
    })


async def validate_config(hass: HomeAssistant, data: dict[str, Any]) -> None:
    key = data.get("api_key", "")
    if not key:
        raise ValueError("api_key is required")
    session = async_get_clientsession(hass)
    try:
        async with session.get(
            f"{GAODE_API_BASE}/v3/place/text",
            params={"keywords": "天安门", "region": "北京", "key": key, "output": "json"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            body = await resp.json()
            if body.get("status") != "1":
                raise ValueError(f"API Key 无效: {body.get('info', '未知错误')}")
    except ValueError:
        raise
    except Exception as err:
        raise ValueError(f"连接失败: {err}") from err


async def setup_provider(
    hass: HomeAssistant,
    config: dict[str, Any],
    subentry_id: str,
) -> ProviderRuntime:
    api_key = config["api_key"]
    security_code = config.get("security_code", "")
    session = async_get_clientsession(hass)
    status = "connected"

    client = GaodeClient(session, api_key, security_code)

    async def stop() -> None:
        pass

    def get_status() -> str:
        return status

    async def _health_check() -> bool:
        try:
            await client.search_poi("天安门", "北京")
            return True
        except Exception as err:
            _LOGGER.warning("Gaode health check failed: %s", err)
            return False

    return ProviderRuntime(
        key=PROVIDER_KEY, title=PROVIDER_NAME, subentry_id=subentry_id,
        client=client, stop=stop, status=get_status, status_check=_health_check,
    )


class GaodeClient:
    """高德地图客户端"""
    
    def __init__(self, session: aiohttp.ClientSession, api_key: str, security_code: str) -> None:
        self._session = session
        self._api_key = api_key
        self._security_code = security_code

    # ========== 基础地图服务 ==========

    async def search_poi(self, keywords: str, region: str = "全国", city_limit: bool = False) -> list:
        """POI 关键字搜索"""
        params = {
            "keywords": keywords,
            "region": region,
            "key": self._api_key,
            "output": "json",
            "city_limit": str(city_limit).lower(),
        }
        async with self._session.get(
            f"{GAODE_API_BASE}/v3/place/text",
            params=params,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            body = await resp.json()
            return body.get("pois", [])

    async def search_poi_nearby(self, location: str, keywords: str = "", radius: int = 3000) -> list:
        """POI 周边搜索"""
        params = {
            "location": location,
            "key": self._api_key,
            "output": "json",
            "radius": str(radius),
        }
        if keywords:
            params["keywords"] = keywords
        async with self._session.get(
            f"{GAODE_API_BASE}/v3/place/around",
            params=params,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            body = await resp.json()
            return body.get("pois", [])

    async def geocode(self, address: str, city: str = "") -> dict | None:
        """地理编码（地址 → 坐标）"""
        params = {
            "address": address,
            "key": self._api_key,
            "output": "json",
        }
        if city:
            params["city"] = city
        async with self._session.get(
            f"{GAODE_API_BASE}/v3/geocode/geo",
            params=params,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            body = await resp.json()
            geocodes = body.get("geocodes", [])
            return geocodes[0] if geocodes else None

    async def reverse_geocode(self, location: str) -> dict | None:
        """逆地理编码（坐标 → 地址）"""
        params = {
            "location": location,
            "key": self._api_key,
            "output": "json",
        }
        async with self._session.get(
            f"{GAODE_API_BASE}/v3/geocode/regeo",
            params=params,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            body = await resp.json()
            return body.get("regeocode")

    async def get_distance(self, origins: str, destination: str, type_: int = 1) -> dict:
        """路线规划"""
        params = {
            "origins": origins,
            "destination": destination,
            "key": self._api_key,
            "output": "json",
            "type": str(type_),
        }
        async with self._session.get(
            f"{GAODE_API_BASE}/v3/direction/driving",
            params=params,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            body = await resp.json()
            return body.get("route", {})

    # ========== 设备追踪器相关 ==========

    async def convert_gcj02_to_wgs84(self, lng: float, lat: float) -> tuple[float, float]:
        """GCJ-02 坐标转 WGS-84"""
        # 简化的转换算法
        lng, lat = self._gcj02_to_wgs84(lng, lat)
        return lng, lat

    async def convert_wgs84_to_gcj02(self, lng: float, lat: float) -> tuple[float, float]:
        """WGS-84 坐标转 GCJ-02"""
        lng, lat = self._wgs84_to_gcj02(lng, lat)
        return lng, lat

    def _gcj02_to_wgs84(self, lng: float, lat: float) -> tuple[float, float]:
        """GCJ-02 → WGS-84"""
        PI = 3.14159265358979324
        a = 6378245.0
        ee = 0.00669342162296594323
        dlat = self._transform_lat(lng - 105.0, lat - 35.0)
        dlng = self._transform_lng(lng - 105.0, lat - 35.0)
        radlat = lat / 180.0 * PI
        magic = math.sin(radlat)
        magic = 1 - ee * magic * magic
        sqrtmagic = math.sqrt(magic)
        dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * PI)
        dlng = (dlng * 180.0) / (a / sqrtmagic * math.cos(radlat / 180.0 * PI) * PI)
        return lng - dlng, lat - dlat

    def _wgs84_to_gcj02(self, lng: float, lat: float) -> tuple[float, float]:
        """WGS-84 → GCJ-02"""
        PI = 3.14159265358979324
        a = 6378245.0
        ee = 0.00669342162296594323
        dlat = self._transform_lat(lng - 105.0, lat - 35.0)
        dlng = self._transform_lng(lng - 105.0, lat - 35.0)
        radlat = lat / 180.0 * PI
        magic = math.sin(radlat)
        magic = 1 - ee * magic * magic
        sqrtmagic = math.sqrt(magic)
        dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * PI)
        dlng = (dlng * 180.0) / (a / sqrtmagic * math.cos(radlat / 180.0 * PI) * PI)
        return lng + dlng, lat + dlat

    def _transform_lat(self, lng: float, lat: float) -> float:
        ret = -100.0 + 2.0 * lng + 3.0 * lat + 0.2 * lat * lat + 0.1 * lng * lat + 0.2 * math.sqrt(abs(lng))
        ret += (20.0 * math.sin(6.0 * lng * math.pi) + 20.0 * math.sin(2.0 * lng * math.pi)) * 2.0 / 3.0
        ret += (20.0 * math.sin(lat * math.pi) + 40.0 * math.sin(lat / 3.0 * math.pi)) * 2.0 / 3.0
        ret += (160.0 * math.sin(lat / 12.0 * math.pi) + 320.0 * math.sin(lat * math.pi / 30.0)) * 2.0 / 3.0
        return ret

    def _transform_lng(self, lng: float, lat: float) -> float:
        ret = 300.0 + lng + 2.0 * lat + 0.1 * lng * lng + 0.1 * lng * lat + 0.1 * math.sqrt(abs(lng))
        ret += (20.0 * math.sin(6.0 * lng * math.pi) + 20.0 * math.sin(2.0 * lng * math.pi)) * 2.0 / 3.0
        ret += (20.0 * math.sin(lng * math.pi) + 40.0 * math.sin(lng / 3.0 * math.pi)) * 2.0 / 3.0
        ret += (150.0 * math.sin(lng / 12.0 * math.pi) + 300.0 * math.sin(lng * math.pi / 30.0)) * 2.0 / 3.0
        return ret

    async def calculate_distance(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """计算两点距离（米）"""
        # Haversine 公式
        R = 6371000  # 地球半径（米）
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lng = math.radians(lng2 - lng1)
        a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    async def check_in_polygon(self, point_lat: float, point_lng: float, polygon: list[tuple[float, float]]) -> bool:
        """检查点是否在多边形内"""
        n = len(polygon)
        inside = False
        p1_lat, p1_lng = polygon[0]
        for i in range(n + 1):
            p2_lat, p2_lng = polygon[i % n]
            if point_lng > min(p1_lng, p2_lng):
                if point_lng <= max(p1_lng, p2_lng):
                    if point_lat <= max(p1_lat, p2_lat):
                        if p1_lng != p2_lng:
                            point_lon_intersects = (point_lat - p1_lat) * (p2_lng - p1_lng) / (p2_lat - p1_lat) + p1_lng
                        if p1_lng == p2_lng or point_lng <= point_lon_intersects:
                            inside = not inside
            p1_lat, p1_lng = p2_lat, p2_lng
        return inside


PROVIDER_SPEC = ProviderSpec(
    key=PROVIDER_KEY,
    name=PROVIDER_NAME,
    schema_builder=build_schema,
    validate_config=validate_config,
    setup_provider=setup_provider,
    allow_multiple=True,
)
