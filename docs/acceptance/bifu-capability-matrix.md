# Bifu 能力与验收矩阵

这是 Bifu 重写的唯一进度表。自 2026-09-18 起，项目只按下面三个部分执行和汇报；旧的单接口
阶段编号仅作为历史记录，不再作为后续项目阶段。每完成一个接口，仍要同时更新代码、测试、中文
解读和本表。昨天未进入 `Jacky` 分支的实现不算当前完成状态。

## 状态含义

- `未开始`：尚未写本轮失败测试。
- `红灯`：失败测试已证明缺少该能力。
- `离线通过`：协议转换和错误路径自动化测试通过，尚未连测试环境。
- `程序在线通过`：测试环境自动验收通过，尚未由 Jacky 亲自验收。
- `Jacky 已验收`：Jacky 亲自运行并能解释输入、输出和结果。
- `待资料`：缺少明确协议、URL、权限或测试数据，不能猜。
- `不支持`：有证据确认不支持，并在 `has` 中如实声明。

## 当前三部分计划

| 部分 | 范围 | 当前状态 | 完成后汇报内容 |
|---|---|---|---|
| 1 | 所有公共及私有 REST 接口，支持异步；Bifu 特殊刷量接口作为交易所私有专有方法单独处理 | 进行中；已完成能力必须按新计划重新归类和复核 | 方法清单、`has`、自动化结果、测试环境真实调用、CCXT 结构与异常映射、遗留问题 |
| 2 | 公共及私有 WebSocket | 未开始 | `watch*` 清单、订阅与鉴权、真实更新、心跳/断线/重连、CCXT 结构、遗留问题 |
| 3 | 全功能测试、问题修复、全量回归、代码复审和正式交付 | 未开始 | 全接口矩阵、修复记录、全库测试、复审与清理、构建产物、最终交付说明 |

测试环境和生产环境不是两个开发阶段；两者共用同一适配器，通过不同 URL、Key 和参数选择环境。
每个部分内部仍逐接口测试，重点确认真实数据、CCXT 标准格式和 CCXT 异常映射。每个部分只有在
形成领导汇报并完成确认后，才进入下一部分。

### 第一部分当前进度（2026-09-18）

| 统一方法 | 自动化 | 测试环境在线 | 当前结论 |
|---|---|---|---|
| `load_markets` / `fetch_markets` | 通过 | 通过 | 24 个现货市场；Bifu `BTC-USDT` 映射为 CCXT `BTC/USDT` |
| `fetch_ticker` | 通过 | 通过 | 标准 Ticker；不伪造未提供的 bid/ask |
| `fetch_tickers` | 通过 | 通过 | FULL 形态按 symbol 筛选；不把 meta 外的 instrument 伪装成市场 |
| `fetch_order_book` | 通过 | 通过 | 实取买卖各 5 档；标准时间戳和 nonce；校验响应 instrument |
| `fetch_ohlcv` | 通过 | 通过 | 实取 2 行标准六字段 OHLCV；校验响应 instrument |
| `fetch_trades` | 通过 | 通过 | 实取 2 条标准 Trade；金额使用 CCXT 精确乘法；校验响应 instrument |
| `fetch_balance` | 通过 | 通过 | 真实测试 Key 鉴权成功；不记录精确余额；meta 未知资产以原始 ID 保留 |
| `fetch_open_orders` | 通过 | 通过 | 当前 `BTC/USDT` 挂单为 0；兼容测试环境用 `{}` 表示空结果 |
| `fetch_closed_orders` | 通过 | 通过 | 实取 1 条历史样本并标准化为 `canceled`；当前只返回一页 |
| `fetch_my_trades` | 通过 | 通过 | 实取 1 条个人成交，识别为 maker；标准 Trade 与手续费结构通过 |
| `fetch_order` | 通过 | 部分通过 | 请求、解析、ID 校验与 `OrderNotFound` 映射通过；未知状态保持 `None`，按计价币金额买入的市价单不伪造 `amount=0`，已知手续费已标准化；现有历史样本 ID 经单笔接口返回 `OrderNotFound`，原因待用新测试订单复核 |

统一入口、显式测试/生产配置和签名已完成。本表只记录当前中间进度，不表示第一部分已经完成；
创建/撤销订单、批量接口、资金流水、异常矩阵和 Bifu 专有 `mock` 完成并复审后，才形成第一
部分领导汇报。

当前全库回归：**128 passed**；核心包 statement/branch coverage **94.61%**；Ruff 检查和格式检查
通过。44 条 warning 均来自 aiohttp 在 Python 3.14 下的依赖层弃用提示，不是适配器失败。

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

> 下列“阶段 0/1/2/3a”是三部分计划确定前的历史验收快照，其中关于手工注册、禁止生产 URL、
> 能力仍为 False 等描述只反映当时版本，不能作为当前使用说明。当前行为以本文件顶部三部分计划、
> `docs/learning/01-bifu-environment.md` 和现行代码为准。

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

### 2026-09-18：阶段 3a `fetch_ticker`

- 候选版本：未提交工作区，基于远端
  `Jacky@321cf49ef17557098fde99d0f172421f8bc39948`。Python 3.14.7、CCXT 4.5.78、uv
  0.12.15。
- 协议依据：Bifu 公开文档的 `GET /market/v1/ticker`。请求参数为 `instrument_id`；成功响应是指定
  标的的 24h 滚动成交统计，字段包括最新、开盘、最高、最低价格，基础币成交量、计价币成交额、
  价格变化、百分比和交易所时间戳。接口不需要鉴权。
- 功能：`fetch_ticker("BTC/USDT")` 先通过 markets 找到原始 ID，再请求 Bifu 并返回 CCXT 标准
  Ticker；开启 `fetchTicker` 能力声明。响应标的 ID 不一致、时间戳非法或响应不是 JSON 对象时
  明确抛 `BadResponse`；业务码 `6005`（标的存在但无成交）映射为 `BadResponse`，不会误报整个
  交易所不可用；不接受未经确认的额外 `params`。
- 字段边界：`last/open/high/low/baseVolume/quoteVolume/change/percentage/timestamp` 来自 Bifu
  明确字段；`bid/ask` 保持 `None`，因为买一卖一属于独立 `bookTicker` 接口，不能用最新成交价
  伪造。
- 自动化：`pytest -q tests/test_bifu_ticker.py`，**9 passed**。覆盖标准映射、固定标的 ID、未知
  参数、错配标的、非法时间戳、非对象响应、空涨跌幅、业务码 `6005`、验收工具输出和只读工具
  首次超时后重试一次。
- 全库复测：2026-09-18 15:27 CST，`pytest -q --cov=ccxt_cm --cov-report=term-missing`，
  **100 passed**，核心包 statement/branch coverage **100%**；20 条仍为 aiohttp/CPython
  依赖层 `DeprecationWarning`。
- 静态与发布物：`ruff check .`、43 文件格式检查通过；wheel/sdist 构建通过。隔离构建首次因
  执行环境无法解析 PyPI 失败，安装 `pyproject.toml` 已声明的 Hatchling 后使用现有环境完成构建；
  代码与依赖约束未改变。
- 测试环境：2026-09-18 15:07 CST 公开只读在线验收通过。BTC/USDT 返回原始
  `instrument_id=90000001`、交易所毫秒时间戳、24h 价格和成交量；本次快照中 `last=538944.47`、
  `baseVolume=0.44998`、`quoteVolume=242966.07064`。行情会变化，这些数字只作为当次链路证据。
- 安全边界：没有使用 Key，没有访问账户，没有下单或撤单；生产 URL 仍关闭。人工验收工具首次
  超时只重试一次，核心适配器不自动重试。
- Jacky 手动验收：未开始。运行 `uv run python -m examples.inspect_bifu_ticker BTC/USDT`，完成
  `docs/learning/03-bifu-fetch-ticker.md` 的五个问题后再更新。
- 复审与清理：第一轮规范审查通过；需求审查发现业务码 `6005` 被 CCXT 默认误映射为
  `ExchangeNotAvailable`，已增加明确映射和回归测试。最终双轴复审待复测后补记。

### 2026-09-19：第一部分中间验收——私有只读订单查询

- 功能：`fetch_open_orders`、`fetch_closed_orders`、`fetch_order` 和 `fetch_my_trades`；本轮只读，
  没有创建、修改或撤销订单。
- 自动化：全库 **128 passed**，核心包 statement/branch coverage **94.61%**，exit 0；44 条
  warning 均来自 aiohttp 在 Python 3.14 下的依赖层弃用提示。Ruff 检查、格式检查和 diff 检查
  通过。
- 测试环境：当前挂单 0 条；取得 1 条 `canceled` 历史订单和 1 条 maker 成交；订单与成交的
  CCXT 标准字段检查通过。现有历史样本 ID 经单笔查询返回 `OrderNotFound`，因此
  `fetch_order` 在线状态仍为部分通过，待创建新测试订单后复核，未猜测服务端原因。
- 协议边界：未知订单状态保持 `None`；按计价币金额买入的市价单不把 `orig_qty=0` 误报为
  `amount=0`；已知累计手续费转换为 CCXT 标准 `fee`；历史订单和个人成交当前只读取一页。
- 安全：测试样本、验收工具和仓库敏感信息扫描无真实 Key、Secret、账户 ID、订单 ID 或成交 ID；
  验收工具输出同样不显示这些字段。
- 复审：规范和需求双轴复审均通过，无 blocker；复审发现的未知状态排序和教学标题问题已修复并
  补回归测试。
- Jacky 手动验收：2026-09-19 已完成。Jacky 在 `Jacky` 分支工作区亲自执行
  `python -m examples.inspect_bifu_orders BTC/USDT` 并得到上述脱敏结果；已确认理解公共成交与账户
  成交、空挂单、历史与单笔查询、单页历史以及按计价币金额买入市价单这五个边界。
