# Life Hub — Code Review 报告

**日期:** 2026-07-17
**审查范围:** `D:\ai-hub\integrations\life_hub\custom_components\life_hub` 全量代码
**集成设计:** QClaw 生态连接器代理，非独立 HA 集成

---

## 目录

- [P0 — 必须修复：配置后无法正常工作](#p0-必须修复配置后无法正常工作)
- [P1 — 建议修复：有 bug 或维护风险](#p1-建议修复有-bug-或维护风险)
- [P2 — 代码整洁：可优化但优先级低](#p2-代码整洁可优化但优先级低)

---

## P0 — 必须修复：配置后无法正常工作

### P0-① 一鸣传感器/coordinator 从未接入主 setup flow

**问题：** 主 `__init__.py` 声明 `PLATFORMS = [Platform.SENSOR]` 然后调 `async_forward_entry_setups`，这只会调用**主** `sensor.py` 的 `async_setup_entry`，在其中为每个 provider 创建 1 个 `ProviderStatusSensor`。

而 `yiming/sensors.py` 的 `async_setup_entry` **没有任何代码调用**它。里面需要 `hass.data[DOMAIN][entry.entry_id]` 有 coordinator，也没人写过。

**结果：** 用户配了一鸣，只看到一个"连接状态"传感器，余额/积分/优惠券/会员等级等 17 个传感器全部不会出现。

**修复方向：**
- 方案 A：修改主 `__init__.py` / `sensor.py`，在 `async_setup_entry` 中检测 `yiming` 并触发其专属 coordinator 和传感器注册
- 方案 B：让 `yiming` 不要走 `PLATFORMS` 通道，而是直接在 `async_setup_entry` 里用 `async_create_task` 加载传感器
- 方案 C：在 `yiming/PROVIDER_SPEC` 上加钩子，让主框架能按 provider 注册自定义平台

**涉及文件：**
- `__init__.py` — 主 setup entry
- `sensor.py` — 主传感器入口
- `providers/yiming/__init__.py` — PROVIDER_SPEC 定义
- `providers/yiming/coordinator.py` — DataUpdateCoordinator
- `providers/yiming/sensors.py` — 17 个传感器定义

---

### P0-② YimingClient vs YimingApi 双客户端

**问题：** `providers/yiming/__init__.py` 定义了 `YimingClient`，包含 `get_user_info / get_balance / get_orders` 等基本方法。`PROVIDER_SPEC.setup_provider` 创建的是 `YimingClient`。

而 `providers/yiming/api.py` 定义了另一个独立的 `YimingApi` 类，功能更全（`receive_all_coupons / submit_order / send_sms_code / get_qrcode` 等）。主 `services.py` 和 `yiming/services.py` 引用的是 `YimingApi`。

但 `setup_provider` 返回的是 `YimingClient` 实例 → services 调 `await client.receive_all_coupons()` 会 **AttributeError**。

**具体影响的服务：** 所有 yiming 域的服务（领券、门店、下单、登录等约 15 个）只要有 API 调用就会崩。

**修复方向：** 删除 `__init__.py` 中的 `YimingClient`，改由 `setup_provider` 创建 `YimingApi` 实例赋值给 `client`。

**涉及文件：**
- `providers/yiming/__init__.py` — 删除 YimingClient 类
- `providers/yiming/api.py` — 保持 YimingApi（功能完整）
- `services.py` — 引用 YimingApi（正确）
- `providers/yiming/services.py` — 引用 YimingApi（正确）

---

### P0-③ 一鸣订单签名需 pycryptodome 依赖

**问题：** `api.py` 的 `_generate_sign` 函数（用于 submit_order 的 AES-128-CBC 加密签名）：

```python
from Crypto.Cipher import AES
```

`Crypto` 是 `pycryptodome` 包，HA 默认**不含**该库。如果 `submit_order` 服务被调用，会直接抛 ImportError。

**修复方向：**
- 在 `manifest.json` 的 `requirements` 中声明 `pycryptodome>=3.21`
- 或使用 Python 标准库 `hashlib` + 纯 Python AES 实现替代

**涉及文件：**
- `manifest.json` — 加依赖声明
- `providers/yiming/api.py` — `_generate_sign` 函数

---

### P0-④ 飞猪加密需 cryptography 依赖

**问题：** `fliggy/__init__.py` 的 `_build_x_ff_ctx` 函数：

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
```

`cryptography` 包不一定存在于目标 HA 环境。该函数在 `validate_config` 和每次 API 请求时都会调用。

**修复方向：** 在 `manifest.json` 的 `requirements` 中声明 `cryptography>=42.0`。

**涉及文件：**
- `manifest.json` — 加依赖声明

---

### P0-⑤ 主 services.py 与 yiming/services.py 重复

**问题：** 两个文件实现了同一组业务逻辑，但注册方式不同：
- 主 `services.py` 以 `"yiming_receive_all_coupons"` 为服务名注册（`hass.services.async_register(DOMAIN, ...)`）
- `yiming/services.py` 以 `"yiming.receive_all_coupons"` 为服务名注册

虽然 `yiming/services.py` 实际未被执行（不在 import 链），但代码冗余且容易混淆。同时两个文件都定义了自己到 `_get_yiming_client` 逻辑细节不同，维护时容易不一致。

**修复方向：**
- 方案 A：删除 `yiming/services.py`，保留主 `services.py`（已注册且可用）
- 方案 B：删除主 `services.py`，让 `yiming/services.py` 在 `async_setup_entry` 中被 import

**涉及文件：**
- `services.py` — 全局服务注册
- `providers/yiming/services.py` — 局部服务注册
- `__init__.py` — 当前 import 主 services.py

---

### P0-⑥ 一鸣 validate_config 登录流程混乱

**问题：** `providers/yiming/__init__.py` 的 `validate_config` 在表单提交时直接发送验证码并兑换 token。同时 `flow.py` 的两步式（phone → verify_code）也发验证码并兑换 token。两条路径做了重复工作。

更关键的是，`validate_config` 的语义是"校验配置"——它是**同步校验**，不适合在内部做发验证码、兑换 token 这种多步骤交互式操作。如果验证码发送成功后 `validate_config` 才返回异常，用户无法在表单上输入验证码。

**修复方向：** `validate_config` 仅校验 token 有效性（如果 token 存在）；发验证码和兑换 token 的逻辑全部由 `flow.py` 的 `async_step_*` 处理。

**涉及文件：**
- `providers/yiming/__init__.py` — `validate_config` 函数
- `providers/yiming/flow.py` — 两步式 login flow

---

## P1 — 建议修复：有 bug 或维护风险

### P1-⑦ provider_flow.py 使用 HA 私有 API

**问题：** `provider_flow.py` 中的 `_get_entry` 和 `_get_reconfigure_subentry` 函数：

```python
def _get_entry(flow):
    if hasattr(flow, "_get_entry"):
        return flow._get_entry()
    # fallback: via context...
```

`ConfigSubentryFlow._get_entry` 和 `_get_reconfigure_subentry` 是 HA 核心的 `@internal` 方法（下划线前缀）。虽然当前 HA 2024.12 支持且写了 fallback，但**不保证** HA 2025.x 还能用。

**影响：** 所有 provider 的 flow 创建和重配置功能。

**修复方向：** 依赖当前的 fallback 逻辑（走 `flow.context` 和 `entry.subentries`），持续监控 HA 版本升级兼容性。建议在 release notes 中注明约束。

**涉及文件：**
- `provider_flow.py`

---

### P1-⑧ 携程/美团外卖 validate_config 不校验 token

**问题：**

```python
# ctrip/__init__.py
async def validate_config(hass, data):
    token = data.get("api_token", "")
    if not token:
        raise ValueError("api_token is required")

# meituan_waimai/__init__.py  
async def validate_config(hass, data):
    token = data.get("token", "")
    if not token:
        raise ValueError("token is required")
```

两者都只检查非空，不做任何 HTTP 校验。用户输入错误 token 要等到实际调用 API 时才能发现。

**修复方向：** 如果 token 来自 QClaw 外部生成（用户自行申请），建议加轻量级 HTTP 校验。如果 token 禁止外部校验，则维持现状并在 README 中说明。

**涉及文件：**
- `providers/ctrip/__init__.py`
- `providers/meituan_waimai/__init__.py`

---

### P1-⑨ flow.py 导入 provider_flow 的下划线私有函数

**问题：** `yiming/flow.py` 和 `tongcheng/flow.py` 都导入 `provider_flow.py` 的下划线前缀函数：

```python
from ...provider_flow import _load_channel_titles, _existing_count, _MAX_INSTANCES_PER_PROVIDER
```

Python 下划线前缀表示"内部实现，外部不应直接调用"。如果未来重构 `provider_flow.py`，这些外部引用可能被忽略导致 break。

**修复方向：** 将这些函数改为公开（去掉下划线前缀或提供公开别名），或将这些工具函数移到共享模块（如 `utils.py`）。

**涉及文件：**
- `provider_flow.py` — 改为公开函数
- `providers/yiming/flow.py`
- `providers/tongcheng/flow.py`

---

### P1-⑩ captcha.py 回调解析脆弱

**问题：** `captcha.py` 的 JSONP 回调解析：

```python
json_str = text[text.index("(") + 1 : text.rindex(")")]
```

假设腾讯云验证码的响应永远是 `_aq(...)` 格式。如果腾讯云改版返回纯 JSON 或不同回调函数名，直接报 `substring not found` 异常，且异常信息对用户不友好（callback 场景无错误提示）。

**修复方向：** 加 `try/except` 或用正则兜底 `re.match(r'^\w+\((.*)\);?$', text)`。

**涉及文件：**
- `providers/yiming/captcha.py`

---

## P2 — 代码整洁：可优化但优先级低

### P2-⑪ 一鸣 const.py 死常量

`const.py` 定义了 `SERVICE_RECEIVE_ALL_COUPONS = "receive_all_coupons"` 等字符串常量，但在 `yiming/services.py` 中被硬编码覆盖，从未 import。

### P2-⑫ 一鸣 sensors.py 类型注解抑制

`coordinator.py` 用 `@property` 暴露 `device_info`，`sensors.py` 中引用时用 `# type: ignore[attr-defined]` 抑制类型检查。可以改为在 `YimingDataUpdateCoordinator` 上通过 `typing` 声明公开属性来消除抑制。

### P2-⑬ 一鸣付款码硬编码 60s 刷新间隔

`_refresh_interval = timedelta(seconds=60)` 固定写死，不支持用户配置。可以改为从 entry 配置中读取。

### P2-⑭ 缺少英文翻译更新

新增的 provider（如 `meituan_waimai`、`fliggy`）的 subentry 描述、sensor 状态值在 `en.json` 中可能缺失部分翻译项。

---

## 修改建议优先级

| 优先级 | 事项 | 复杂度 | 影响面 |
|--------|------|--------|--------|
| **P0-②** | 统一双客户端（最影响功能） | 低 | 一鸣所有服务 |
| **P0-①** | 一鸣传感器接入主流程 | 中 | 一鸣所有传感器 |
| **P0-③** | pycryptodome 依赖声明 | 低 | 一鸣下单 |
| **P0-④** | cryptography 依赖声明 | 低 | 飞猪全部 |
| **P0-⑥** | validate_config 登录逻辑清理 | 中 | 一鸣配置流程 |
| **P0-⑤** | services 冗余清理 | 低 | 代码维护 |
| **P1-⑧** | 缺 token 校验 | 低 | 携程/美团外卖配置 |
| **P1-⑨** | 私有函数公开化 | 低 | 代码卫生 |
| **P1-⑩** | captcha 解析加固 | 低 | 一鸣登录 |
| **P1-⑦** | 私有 API 监控 | 低 | 长期兼容性 |
| **P2-⑪~⑭** | 代码整洁 | 低 | 无功能影响 |
