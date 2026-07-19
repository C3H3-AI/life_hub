# Life Hub - 生活服务集成

Home Assistant 自定义集成，聚合多个中国生活服务平台，提供统一的 API 接口。

## 支持的服务

### 🍔 一鸣真鲜奶吧 (yiming)

| 服务 | 说明 |
|------|------|
| `yiming.send_sms_code` | 发送短信验证码 |
| `yiming.register_by_sms` | 短信验证码登录 |
| `yiming.get_user_info` | 获取用户信息 |
| `yiming.get_balance` | 查询储值余额 |
| `yiming.get_member_info` | 查询会员等级/成长值 |
| `yiming.get_coupon_sum` | 查询优惠券统计 |
| `yiming.get_integral` | 查询当前积分 |
| `yiming.get_orders` | 查询最近订单 |
| `yiming.get_my_coupons` | 查询我的优惠券 |
| `yiming.get_qrcode` | 获取付款二维码 |
| `yiming.get_coupon_pools` | 查询可领优惠券池 |
| `yiming.receive_coupon` | 领取单张优惠券 |
| `yiming.receive_all_coupons` | 自动领取所有可领优惠券 |
| `yiming.get_nearest_store` | 查询最近可用门店 |
| `yiming.search_stores` | 搜索门店 |
| `yiming.get_menu` | 获取门店商品菜单 |
| `yiming.get_sku_info` | 获取商品SKU详情 |
| `yiming.get_delivery_time` | 获取配送时段 |
| `yiming.get_default_address` | 获取默认收货地址 |
| `yiming.get_nearby_addresses` | 获取附近地址列表 |
| `yiming.calculate_cart` | 计算购物车金额 |
| `yiming.pre_create_order` | 预创建订单 |
| `yiming.submit_order` | 提交订单（堂食/自取/外卖） |
| `yiming.get_order` | 查询订单详情 |

### ✈️ 飞猪旅行 (fliggy)

| 服务 | 说明 |
|------|------|
| `fliggy.fast_search` | 自然语言快速搜索（酒店/机票/景点） |
| `fliggy.ai_search` | AI 智能搜索（语义理解） |
| `fliggy.search_flight` | 机票搜索 |
| `fliggy.search_hotel` | 酒店搜索 |
| `fliggy.search_train` | 火车票搜索 |
| `fliggy.search_poi` | 景点门票搜索 |
| `fliggy.search_marriott_hotel` | 万豪酒店搜索 |
| `fliggy.search_marriott_package` | 万豪套餐搜索 |

### 🏨 携程旅行 (ctrip)

| 服务 | 说明 |
|------|------|
| `ctrip.query` | 携程问道 API 自然语言查询 |
| `ctrip.search_hotel` | 酒店搜索 |

### 🚄 同程旅行 (tongcheng)

| 服务 | 说明 |
|------|------|
| `tongcheng.search_hotel` | 酒店搜索 |
| `tongcheng.search_flight` | 机票搜索 |
| `tongcheng.get_orders` | 查询订单列表 |

### 🛵 美团旅行 (meituan_travel)

| 服务 | 说明 |
|------|------|
| `meituan_travel.search_hotel` | 酒店搜索 |
| `meituan_travel.get_orders` | 查询旅行订单 |

### 🛒 美团优惠下单 (meituan_order)

| 服务 | 说明 |
|------|------|
| `meituan_order.get_orders` | 查询优惠下单订单 |
| `meituan_order.get_coupons` | 查询优惠券列表 |

### 🍟 麦当劳 (mcdonalds)

| 服务 | 说明 |
|------|------|
| `mcdonalds.call_tool` | 调用麦当劳 MCP 平台工具（菜单/门店/订单等） |

### 🗺️ 百度地图 (baidu_map)

| 服务 | 说明 |
|------|------|
| `baidu_map.search` | POI 地点搜索 |
| `baidu_map.geocode` | 地理编码（地址 → 坐标） |
| `baidu_map.reverse_geocode` | 逆地理编码（坐标 → 地址） |

## 安装

### HACS 安装（推荐）

1. 在 HACS 中添加自定义仓库：`C3H3-AI/ha-life-hub`
2. 搜索 "Life Hub" 并安装
3. 重启 Home Assistant

### 手动安装

1. 下载 `custom_components/life_hub` 目录
2. 复制到 Home Assistant 的 `config/custom_components/` 目录
3. 重启 Home Assistant

## 配置

1. 进入 **设置 → 设备与服务 → 添加集成**
2. 搜索 "Life Hub" 并添加
3. 点击 **添加** 按钮，选择要添加的服务
4. 输入相应的 API Token 或凭证

## API Token 获取指南

| 服务 | 获取方式 |
|------|----------|
| 一鸣真鲜奶吧 | 手机号 + 验证码登录 |
| 飞猪旅行 | [飞猪 AI 开放平台](https://flyai.open.fliggy.com/) |
| 携程旅行 | [携程问道 API](https://qclaw.qq.com/docs/208231741261246464) |
| 同程旅行 | [同程 OAuth 授权](https://m.ly.com/memberauth/oauth2/authorize) |
| 美团旅行 | [美团开发者平台](https://developer.meituan.com/) |
| 美团优惠下单 | [美团开发者平台](https://developer.meituan.com/) |
| 麦当劳 | [麦当劳 MCP 平台](https://qclaw.qq.com/docs/215059947716583424) |
| 百度地图 | [百度地图开放平台](https://lbsyun.baidu.com/) |

## 传感器

每个已配置的服务都会创建一个连接状态传感器：

- `sensor.life_hub_<provider>_status` - 服务连接状态（connected/disconnected）

## 自动化示例

```yaml
# 一鸣领券自动化
automation:
  - alias: 一鸣每日领券
    trigger:
      - platform: time
        at: "09:00:00"
    action:
      - service: life_hub.yiming_receive_all_coupons

# 飞猪机票搜索
automation:
  - alias: 搜索特价机票
    trigger:
      - platform: state
        entity_id: input_boolean.search_flight
        to: "on"
    action:
      - service: life_hub.fliggy_search_flight
        data:
          origin: "杭州"
          destination: "北京"
```

## 注意事项

1. 部分服务需要有效的 API Token 才能使用
2. 服务调用可能有频率限制，请合理使用
3. 敏感信息（Token）存储在 Home Assistant 配置中，请确保系统安全
