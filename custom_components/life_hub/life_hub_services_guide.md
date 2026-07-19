---
name: life-hub-services-guide
description: Life Hub 服务使用指南 - 整合了携程、飞猪、美团、麦当劳、一鸣等平台的服务调用说明
keywords:
  - 酒店搜索
  - 机票搜索
  - 火车票
  - 景点门票
  - 麦当劳
  - 一鸣
  - 美团
  - 跑腿
  - 地图
  - 旅游
  - hotel
  - flight
  - mcdonalds
  - yiming
  - meituan
tags:
  - travel
  - food
  - map
  - delivery
category: service-integration
---

# Life Hub 服务使用指南

Life Hub 是 Home Assistant 中的一个服务集成，整合了多个生活服务平台的能力。所有服务都通过 `life_hub` 域提供，支持返回值（`supports_response=OPTIONAL`）。

## 通用规则

1. **调用方式**：`life_hub.<service_name>` 服务调用，传入对应的字段参数
2. **返回值**：所有服务都返回 JSON 数据，需检查返回值中的具体字段
3. **定位信息**：涉及门店搜索、配送等场景时，会自动使用 HA 配置中的经纬度
4. **错误处理**：如果返回空结果或异常，请提示用户检查配置或重试

---

## 一、飞猪 (Fliggy) - 旅游出行

### 1. 快速搜索 `fliggy_fast_search`
- **参数**：`query`（必填）- 自然语言搜索关键词
- **场景**：用户想搜索酒店、机票、景点等信息，但不确定具体分类时
- **示例**：`{"query": "明天北京到上海的机票"}`

### 2. AI 智能搜索 `fliggy_ai_search`
- **参数**：`query`（必填）- 完整的自然语言查询
- **场景**：复杂语义搜索，理解用户意图后返回结构化结果
- **示例**：`{"query": "帮我找一家上海外滩附近，价格500以内的酒店"}`

### 3. 机票搜索 `fliggy_search_flight`
- **参数**：`origin`（必填）出发地 | `destination`（选填）目的地 | `dep_date`（选填）出发日期 YYYY-MM-DD
- **场景**：用户明确要搜索机票时
- **示例**：`{"origin": "北京", "destination": "上海", "dep_date": "2026-07-20"}`

### 4. 酒店搜索 `fliggy_search_hotel`
- **参数**：`dest_name`（必填）目的地城市 | `key_words`（选填）关键词 | `check_in_date`（选填）入住日期 | `check_out_date`（选填）离店日期
- **场景**：搜索酒店信息
- **示例**：`{"dest_name": "杭州", "key_words": "西湖", "check_in_date": "2026-07-20", "check_out_date": "2026-07-22"}`

### 5. 火车票搜索 `fliggy_search_train`
- **参数**：`origin`（必填）出发地 | `destination`（选填）目的地 | `dep_date`（选填）出发日期
- **场景**：搜索火车票信息

### 6. 景点搜索 `fliggy_search_poi`
- **参数**：`city_name`（必填）城市 | `keyword`（选填）景点关键词
- **场景**：搜索景点门票信息

### 7. 万豪酒店搜索 `fliggy_search_marriott_hotel`
- **参数**：`dest_name`（必填）目的地 | `check_in_date`（选填）入住日期 | `check_out_date`（选填）离店日期
- **场景**：专门搜索万豪集团旗下酒店

### 8. 万豪套餐搜索 `fliggy_search_marriott_package`
- **参数**：`dest_name`（必填）目的地 | `check_in_date`（选填）入住日期 | `check_out_date`（选填）离店日期
- **场景**：搜索万豪酒店套餐（含住宿+餐饮等）

---

## 二、携程 (Ctrip) - 旅行问答与酒店

### 1. 携程问答 `ctrip_query`
- **参数**：`query`（必填）- 自然语言查询
- **场景**：用户问旅行相关问题，如景点推荐、行程规划等
- **示例**：`{"query": "北京三日游推荐"}`

### 2. 酒店搜索 `ctrip_search_hotel`
- **参数**：`location`（必填）目的地 | `budget`（选填）每晚预算（元）
- **场景**：搜索酒店，可根据预算筛选
- **示例**：`{"location": "成都", "budget": 500}`

---

## 三、美团 (Meituan) - 通用 API 调用

### 通用接口 `meituan_call_api`
- **参数**：`method`（必填）方法名 | `params`（选填，JSON 对象）
- **可用方法**：`search_hotel`, `search_flight`, `search_train`, `search_poi`, `plan_itinerary`, `get_travel_orders`, `get_orders`, `get_coupons`, `claim_coupon`, `claim_all_coupons`, `login`, `get_address_list`, `search_poi_waimai`, `preview_order`, `submit_order`, `get_order_status`, `get_store_info`, `search_stores`
- **场景**：通过统一接口调用美团旅行、优惠下单、外卖/跑腿的所有功能
- **示例**：`{"method": "search_hotel", "params": {"query": "广州酒店"}}`、`{"method": "get_coupons"}`

---

## 四、同程 (Tongcheng) - 酒店、机票与订单

### 1. 酒店搜索 `tongcheng_search_hotel`
- **参数**：`city`（必填）目的地城市
- **示例**：`{"city": "深圳"}`

### 2. 机票搜索 `tongcheng_search_flight`
- **参数**：`origin`（选填）出发地 | `destination`（选填）目的地 | `date`（选填）出发日期
- **示例**：`{"origin": "北京", "destination": "深圳", "date": "2026-07-20"}`

### 3. 获取订单列表 `tongcheng_get_orders`
- **参数**：无
- **场景**：查询同程订单

---

## 五、麦当劳 (McDonald's) - MCP 工具调用

### 1. 调用 MCP 工具 `mcdonalds_call_tool`
- **参数**：`tool_name`（必填）工具名称 | `arguments`（选填）JSON 参数对象
- **场景**：通过 MCP 协议调用麦当劳的工具，包括查询菜单、门店、下单等
- **示例**：`{"tool_name": "get_nearby_stores", "arguments": {"lat": 39.9, "lng": 116.4}}`
- **注意**：返回结果包含 MCP 工具的响应数据，需根据 tool_name 解析

---

## 六、一鸣 (Yiming) - 通用 API 调用

### 通用接口 `yiming_call_tool`
- **参数**：`method`（必填）方法名 | `params`（选填）参数 JSON 对象
- **场景**：通过统一接口调用一鸣的所有功能

#### 查询类方法（无 params 或少量 params）

| 方法名 | 用途 | params 参数 |
|--------|------|-------------|
| `get_balance` | 获取余额 | 无 |
| `get_member_info` | 获取会员信息 | 无 |
| `get_coupon_sum` | 获取优惠券总数 | 无 |
| `get_integral` | 获取积分 | 无 |
| `get_user_info` | 获取用户信息 | 无 |
| `get_app_notice` | 获取应用公告 | 无 |
| `get_coupon_pools` | 获取优惠券池 | 无 |
| `get_recharge_list` | 获取充值列表 | 无 |
| `get_app_equity` | 获取应用权益 | 无 |
| `get_user_info_v2` | 获取用户信息V2 | 无 |
| `get_qrcode` | 获取二维码 | 无 |
| `get_transaction_details` | 获取交易明细 | 无 |
| `get_default_address` | 获取默认地址 | 无 |

#### 分页查询类（需要 page_num/page_size）

| 方法名 | 用途 | params 参数 |
|--------|------|-------------|
| `get_orders` | 获取订单列表 | `page_num`(默认1), `page_size`(默认5) |
| `get_my_coupons` | 获取我的优惠券 | `page_num`(默认1), `page_size`(默认20), `usable`(默认1) |
| `get_integral_detail` | 获取积分明细 | `page_num`(默认1), `page_size`(默认5) |

#### 门店/位置类（需要 shop_code/store_code）

| 方法名 | 用途 | params 参数 |
|--------|------|-------------|
| `get_nearest_store` | 获取最近门店 | 无（自动定位） |
| `get_menu` | 获取菜单 | `shop_code`(选填) |
| `get_sku_info` | 获取SKU详情 | `goods_id`(必填), `shop_code`(必填) |
| `search_stores` | 搜索门店 | `city`(选填), `keyword`(选填) |
| `get_delivery_time` | 获取配送时间 | `store_code`(必填), `order_type`(选填, 默认"3") |
| `get_nearby_addresses` | 获取附近地址 | 无 |
| `get_store_info` | 获取门店信息 | `store_code`(必填) |
| `get_region_list` | 获取区域列表 | `user_city`(选填) |
| `get_current_city` | 获取当前城市 | 无（自动定位） |
| `query_nearly_store` | 查询附近门店 | `city`(选填) |
| `query_nearly_store_by_distance` | 按距离查询门店 | `distance`(选填, 默认3000米) |
| `get_nearly_store_one_km` | 获取1公里内门店 | 无 |

#### 下单/购物车类

| 方法名 | 用途 | params 参数 |
|--------|------|-------------|
| `calculate_cart` | 计算购物车 | `goods_list`(必填, JSON数组) |
| `pre_create_order` | 预创建订单 | `shop_code`(选填), `goods_list`(必填, JSON数组) |
| `submit_order` | 提交订单 | `shop_code`, `shop_name`, `goods_list`(JSON数组), `order_type`(1=堂食/2=自取/3=外卖), `pay_type`(1=微信/2=余额/10=到店付), `mobile`, `remark` |

#### 优惠券类

| 方法名 | 用途 | params 参数 |
|--------|------|-------------|
| `receive_all_coupons` | 领取所有优惠券 | 无 |
| `receive_coupon` | 领取单张优惠券 | `equity_pool_id`(必填), `coupon_code`(必填), `receive_num`(选填, 默认1) |

#### 收藏类

| 方法名 | 用途 | params 参数 |
|--------|------|-------------|
| `collect_store_query` | 查询收藏门店 | `city`(选填) |
| `collect_store_create` | 收藏门店 | `store_id`(必填) |

**示例**：
```json
{"method": "get_balance", "params": {}}
{"method": "get_menu", "params": {"shop_code": "YM0001"}}
{"method": "submit_order", "params": {"shop_code": "YM0001", "goods_list": [{"goods_id": 123, "quantity": 2}], "order_type": "3", "mobile": "13800138000"}}
{"method": "receive_coupon", "params": {"equity_pool_id": 12345, "coupon_code": "COUPON2024"}}
```

---

## 七、百度地图 (Baidu Map) - 位置服务

### 1. POI搜索 `baidu_map_search`
- **参数**：`query`（必填）关键词 | `region`（选填）城市
- **场景**：搜索地点、商户、景点等
- **示例**：`{"query": "火锅", "region": "北京"}`

### 2. 地理编码 `baidu_map_geocode`
- **参数**：`address`（必填）地址文本
- **场景**：将地址文字转为经纬度坐标

### 3. 逆地理编码 `baidu_map_reverse_geocode`
- **参数**：`latitude`（必填）纬度 | `longitude`（必填）经度
- **场景**：将经纬度转为地址文字

---

## 八、高德地图 (Gaode Map) - 位置服务

### 1. POI搜索 `gaode_search_poi`
- **参数**：`keywords`（必填）关键词 | `region`（选填, 默认"全国"） | `city_limit`（选填, 默认false）
- **场景**：搜索地点信息

### 2. 附近搜索 `gaode_search_poi_nearby`
- **参数**：`location`（必填）经纬度 "lng,lat" | `keywords`（选填） | `radius`（选填, 默认3000米）
- **场景**：搜索指定位置附近的POI

### 3. 地理编码 `gaode_geocode`
- **参数**：`address`（必填） | `city`（选填）
- **场景**：地址转坐标

### 4. 逆地理编码 `gaode_reverse_geocode`
- **参数**：`location`（必填）经纬度 "lng,lat"
- **场景**：坐标转地址

### 5. 驾车路线规划 `gaode_get_route`
- **参数**：`origins`（必填）起点 | `destination`（必填）终点 | `type`（选填, 1=驾车/2=步行/3=骑行）
- **场景**：计算两点间的驾车/骑行/步行路线

### 6. 两点直线距离 `gaode_calculate_distance`
- **参数**：`lat1`, `lng1`, `lat2`, `lng2`（均为必填float）
- **场景**：简单计算两点间直线距离（纯几何计算）

### 7. 多边形碰撞检测 `gaode_check_in_polygon`
- **参数**：`lat`, `lng`, `polygon`（必填, 经纬度坐标列表）
- **场景**：判断坐标点是否在指定区域内

---

## 使用建议

### 酒店搜索场景
- 优先用 `fliggy_search_hotel`（飞猪酒店数据全）
- 结合 `ctrip_search_hotel`（携程价格对比）
- 可以对比多个平台结果

### 机票搜索场景
- 优先用 `fliggy_search_flight`（飞猪机票覆盖广）
- 结合 `tongcheng_search_flight`（同程比价）

### 美食外卖场景
- 麦当劳用 `mcdonalds_call_tool`（MCP协议）
- 一鸣用 `yiming_call_tool`（通用API调用）

### 地图/位置场景
- 国内用高德地图（`gaode_*` 系列）
- 通用搜索用百度地图（`baidu_map_*` 系列）
