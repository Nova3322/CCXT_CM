# 第 1 课：创建 Bifu 实例并分清测试与生产环境

这一课只解决一个问题：**程序准备连接的是测试环境还是生产环境？**

不读取 Key、不查询账户、不下单。行情、余额和订单功能会在后续各自完成测试后再开放。

## 1. 先理解“实例”

可以把一个交易所实例理解成一部专用手机：它保存这一套环境的地址、Key、限流器和连接状态。

- 测试环境使用一个实例。
- 生产环境使用另一个实例。
- 两个实例不能共享地址、Key 或连接状态。

本项目不把 Bifu 偷偷注册进 CCXT。调用方要先显式注册 `BIFU_EXTENSION`，这样能清楚知道
当前程序加载了哪个非官方交易所适配器。

## 2. 测试环境怎么创建

```python
from ccxt_cm import Registry
from ccxt_cm.exchanges.bifu import BIFU_EXTENSION

registry = Registry()
registry.register(BIFU_EXTENSION)
exchange = registry.create_exchange("bifu", mode="async")
exchange.set_sandbox_mode(True)
```

`set_sandbox_mode(True)` 是 CCXT 的标准测试环境开关，而且必须在其他调用之前执行。当前 Bifu
公开文档只列出了开发环境：

- REST：`https://flame-api.bifu.dev`
- WebSocket：`wss://flame-api.bifu.dev`

环境隔离验收完成后，市场加载能力已在第 2 课开放，所以当前 `fetchMarkets=True`；余额、行情和
订单等尚未实现的能力仍保持 `False`。参见 `docs/learning/02-bifu-load-markets.md`。

## 3. 生产环境为什么暂时不能连接

Bifu 当前公开文档没有提供生产 REST/WS 地址，因此适配器不会猜域名。新实例默认的生产地址均为
`None`，这叫 **fail closed（默认关闭）**。

即使现在手工传入一个看起来像生产环境的 URL，代码也会直接拒绝。只有测试环境所有功能完成，
进入生产只读验收阶段后，才会在新一轮测试中开放生产 URL 配置。

生产环境不会调用 `set_sandbox_mode(True)`。生产 Key 也不能交给测试实例。

## 4. 当前协议资料状态

资料核对时间为 2026-09-17（Asia/Shanghai），来源是 Bifu Flame Gateway 公开文档：

- 文档没有标注版本号，当前版本记为“待资料”，后续接口变更时需要重新核对。
- 公开行情无需鉴权。
- 私有现货接口使用 `X-API-KEY`、毫秒 `X-TS` 和规范化请求的 HMAC-SHA256 小写 hex
  `X-SIGN`；本阶段只记录，不实现签名。
- 文档给出了 `RATE_LIMITED` / `RESOURCE_EXHAUSTED` 错误，但没有公布每秒请求额度，具体频率
  限制记为“待资料”。

## 5. Jacky 第一次手动验收

在仓库根目录运行：

```bash
uv sync --frozen
uv run python -m examples.inspect_bifu_environment test
uv run python -m examples.inspect_bifu_environment production
```

第一条检查命令应该看到：

- `environment` 是 `test`；
- `sandbox` 是 `true`；
- `configured` 是 `true`；
- URL 是 `flame-api.bifu.dev`。

第二条检查命令应该看到：

- `environment` 是 `production`；
- `sandbox` 是 `false`；
- `configured` 是 `false`；
- 三个 URL 都是 `null`。

这两个命令只查看配置，不联网，也不会读取或打印 Key。

## 6. 你要能回答的三个问题

1. 为什么测试环境和生产环境要使用两个实例？
2. `set_sandbox_mode(True)` 应该在什么时候调用？
3. 为什么生产环境显示 `configured: false` 反而是当前正确结果？

你亲自运行命令并能回答这三个问题后，本阶段才从“程序在线通过”改成“Jacky 已验收”。
