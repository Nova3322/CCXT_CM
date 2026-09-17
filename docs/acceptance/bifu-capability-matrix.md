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
| 1 | 创建 Bifu 实例 / 环境隔离 | 基础设施 | 未开始 | 未开始 | 未开始 | 测试、生产 URL 和实例不得混用 |
| 2 | `load_markets` / markets | 普通接口 | 未开始 | 未开始 | 未开始 | 交易对、精度、限额 |
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
