# Bifu 能力与验收矩阵

这是 Bifu 重写的唯一进度表。每完成一个功能，都要同时更新代码、测试、中文解读和本表。
昨天未进入 `Jacky` 分支的实现不算当前完成状态。

## 状态含义

- `未开始`：尚未写本轮失败测试。
- `红灯`：失败测试已证明缺少该能力。
- `离线通过`：协议转换和错误路径自动化测试通过，尚未连测试环境。
- `程序在线通过`：测试环境自动验收通过，尚未由 Jacky 亲自验收。
- `Jacky 已验收`：Jacky 亲自运行并能解释输入、输出和结果。
- `待资料`：缺少明确协议、URL、权限或测试数据，不能猜。
- `不支持`：有证据确认不支持，并在 `has` 中如实声明。

## 当前矩阵

| 阶段 | 能力 | 分类 | 自动化 | 测试环境 | Jacky 人工验收 | 备注/证据 |
|---|---|---|---|---|---|---|
| 0 | 官方 CCXT 对照实验 | 基础学习 | 对象检查通过；全量 69 项通过 | 未通过：Binance 连接被拒，OKX 超时 | 未开始 | 2026-09-17 18:43 CST；见 `docs/learning/00-ccxt-core.md` |
| 1 | 创建 Bifu 实例 / 环境隔离 | 基础设施 | 9 项通过 | 公共主机探活通过；业务接口未开始 | Jacky 已验收（2026-09-18） | 生产配置禁用；测试、生产 URL 和实例不得混用 |
| 2 | `load_markets` / markets | 普通接口 | 13 项通过 | 程序在线通过 | Jacky 已验收（2026-09-18） | 24 个现货市场；交易对、精度、限额已标准化 |
| 3 | ticker / order book | 普通接口 | 未开始 | 未开始 | 未开始 | 行情与盘口方向 |
| 4 | `fetch_trades` / OHLCV | 普通接口 | 未开始 | 未开始 | 未开始 | 公共成交记录，不是创建订单 |
| 5 | `fetch_balance` | 普通接口 | 未开始 | 未开始 | 未开始 | free / used / total |
| 6 | `create_order`、查询、撤单 | 普通接口 | 未开始 | 未开始 | 未开始 | `create_order` 是正常下单；ACK、成交、撤单完成分开判断 |
| 7 | 批量下单、批量撤单 | 普通接口 | 未开始 | 未开始 | 未开始 | 部分成功与逐项关联 |
| 8 | 当前挂单、历史订单、`fetch_my_trades` | 普通接口 | 未开始 | 未开始 | 未开始 | 账户成交记录、状态和分页 |
| 9 | WebSocket 行情、订单、余额 | 普通接口 | 未开始 | 未开始 | 未开始 | 心跳、重连、重新认证 |
| 10 | `mock` 刷量 | **唯一特殊接口** | 未开始 | 待资料 | 未开始 | 分类已确认；路径、参数、鉴权、返回和错误语义待协议证据 |
| 11 | 生产公共/私有只读 | 普通接口 | 未开始 | 测试环境全部完成后再做 | 未开始 | 单独生产 URL / Key，禁止写入 |

## 每轮验收记录模板

复制下面这段到本文件末尾，只保留**脱敏后的**原始结果。Key、Secret、签名、token、账户 ID、
订单 ID、clientOrderId、精确余额和其他账户/客户数据都必须替换为 `[REDACTED]`，不能进入仓库：

```text
日期时间（Asia/Shanghai）：
功能：
代码版本 / commit：
自动化命令与结果：
测试环境命令与结果：
Jacky 手动命令与结果：
我对这个功能的解释：
异常或限制：
复审与清理结果：
```

## 验收记录

### 2026-09-17：阶段 0 仓库基线与中文学习入口

- 日期时间：2026-09-17 18:43–18:50 CST（Asia/Shanghai）。
- 代码版本：以本记录所在 commit 为准；Python 3.14.7、CCXT 4.5.78、uv 0.12.15。
- 锁定环境：`uv sync --frozen`，exit 0。
- 静态检查：`uv run ruff check .`，exit 0；`uv run ruff format --check .`，exit 0，
  31 files already formatted。
- 全量测试：`uv run pytest -q --cov=ccxt_cm --cov-report=term-missing`，exit 0；
  **69 passed**，核心包 statement/branch coverage **100%**，3 条为 aiohttp/CPython 依赖层
  `DeprecationWarning`。
- 构建：`uv build`，exit 0；生成 `ccxt_cm-0.1.0.tar.gz` 和
  `ccxt_cm-0.1.0-py3-none-any.whl`（构建产物由 `.gitignore` 排除）。
- 对象检查：官方 Binance 工厂对象为 `ccxt.pro.binance`，能力声明可读；这只证明工厂复用和
  能力声明，不证明在线接口可用。
- 公共在线检查：Binance 返回 `ExchangeNotAvailable`（连接被拒）；OKX 返回
  `RequestTimeout`。两项均未使用 Key、未下单，在线状态保持“未通过”。
- Jacky 手动验收：未开始；完成 `docs/learning/00-ccxt-core.md` 的五个问题后再更新。
- 双轴复审：规范审查与需求审查指出可复现命令、证据脱敏、协议来源和重复阶段编号问题，均已
  修正。变更只有文档与索引，没有新增运行时代码或调用点；敏感值扫描无命中。

### 2026-09-17：阶段 1 创建 Bifu 实例与环境隔离

- 日期时间：2026-09-17 22:34 CST（Asia/Shanghai）。
- 候选版本：working tree，基于 `origin/Jacky@c8f870b`；适配器 commit 在 Jacky 手动验收并同步
  分支后补记。Python 3.14.7、CCXT 4.5.78。
- 功能：显式注册 Bifu async REST 类；使用 CCXT `set_sandbox_mode(True)` 选择测试环境；生产
  URL 默认关闭且当前禁止注入；测试实例与关闭的生产占位实例不共享凭据和 URL。
- 自动化：`pytest -q tests/test_bifu_environment.py`，**9 passed**。
- 全库复测：`pytest -q --cov=ccxt_cm --cov-report=term-missing`，**78 passed**，核心包
  statement/branch coverage **100%**；3 条仍为 aiohttp/CPython 依赖层 `DeprecationWarning`。
- 静态与构建：ruff 检查、36 文件格式检查通过；wheel/sdist 构建通过，wheel 已核对包含
  `ccxt_cm/exchanges/bifu.py`。
- 安全保护：测试环境全部完成前，任何非空生产 URL 都直接拒绝。
- 测试环境：公开 `/market/v1/meta` 探活返回 HTTP 200；响应包含 `assets`、`spots`、`globals`，
  当时为 69 个资产、24 个现货标的。命令：
  `curl --max-time 30 https://flame-api.bifu.dev/market/v1/meta`。本次没有使用 Key，没有发出
  交易请求。
- 协议资料：公开文档未标版本号；私有接口为 API Key + 毫秒时间戳 + HMAC-SHA256 签名；具体
  请求频率限制待资料。本阶段不实现鉴权。
- 能力边界：本阶段所有 Bifu 业务 `has` 仍为 `False`；探活成功不表示 `fetch_markets` 已实现。
- Jacky 手动验收：2026-09-18 已完成。Jacky 亲自运行测试/生产两个离线检查命令，结果分别为
  `sandbox=true, configured=true` 和 `sandbox=false, configured=false`；能说明测试与生产资金及
  账户不能混用、测试开关要在创建交易所实例后且调用任何接口前打开，以及生产地址不配置可防止
  误连真实账户。

### 2026-09-18：阶段 2 `load_markets` / markets

- 代码版本：以本记录所在 commit 为准；基于远端
  `Jacky@b7ffa9b0c253a31c84dd706e7db4cc8395427334` 开发并完成 Jacky 人工验收。Python
  3.14.7、CCXT 4.5.78、uv 0.12.15。
- 功能：调用测试环境公开 `/market/v1/meta`，将 Bifu 现货标的转换为 CCXT 标准市场结构；开启
  `fetchMarkets`、`publicAPI` 和 `spot` 能力声明。
- 自动化：`pytest -q tests/test_bifu_markets.py`，**13 passed**。覆盖正常标准化、固定查询编码、
  未支持参数、生产关闭、暂停/未知状态、畸形元数据，以及只读验收工具首次超时后重试一次；
  网络测试只连接本机回环服务。
- 全库复测：2026-09-18 13:57 CST，`pytest -q --cov=ccxt_cm --cov-report=term-missing`，
  **91 passed**，核心包 statement/branch coverage **100%**；12 条仍为 aiohttp/CPython 依赖层
  `DeprecationWarning`。
- 静态与发布物：`ruff check .`、39 文件格式检查通过；wheel/sdist 构建通过，wheel 内的
  `ccxt_cm/exchanges/bifu.py` 与工作区一致。
- 测试环境：公开只读在线验收通过，共返回 **24** 个现货市场；`BTC-USDT` 转为 `BTC/USDT`，
  `market.id` 使用原始 `instrument_id=90000001`；数量步长 `0.00001`、价格步长 `0.01`、最小
  数量 `0.00001`、最小名义金额 `5 USDT`。
- 精度示例：数量 `1.23456789` 转为 `1.23456`，价格 `100.129` 转为 `100.13`。
- 稳定性：人工验收时曾出现 `GET /market/v1/meta` 超时；同一链路随后直接请求及程序复测均成功，
  判断为测试环境或 Cloudflare 链路的短暂波动。只读人工验收工具使用 30 秒超时，首次超时会明确
  提示并只重试一次；适配器本身仍尊重调用方传入的 CCXT `timeout`，不会自动重试，避免未来写
  接口出现重复下单。
- 安全边界：不读取 Key、不访问账户、不下单；生产 URL 仍关闭，其他业务 `has` 仍为 `False`；
  原始 `margin` 对象不足以证明保证金交易可用，市场 `margin` 保守保持 `False`。
- Jacky 手动验收：2026-09-18 14:06 CST 已完成。Jacky 亲自运行只读命令，得到测试环境、24 个
  现货市场及 `BTC/USDT` 的标准化结果；能说明 `BTC-USDT` 是 Bifu 原生格式、`BTC/USDT` 是
  CCXT 统一格式且二者不能在程序中混用，订单名义金额低于 `5 USDT` 不能下单，并确认 markets
  验收不代表余额或下单功能已经完成。
