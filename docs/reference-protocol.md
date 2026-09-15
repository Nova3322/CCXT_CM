# 本机参考适配器协议

`cm_reference` 是**虚构现货交易所**，仅接受显式 `http://127.0.0.1` 和 `ws://127.0.0.1`。
默认端口 1，不自动启动服务，不注册进默认工厂；测试创建进程内模拟服务并传入端口。
代码在 `examples/reference_exchange.py`，不进入发布 wheel，不是生产可用的交易所适配器。

## 能力矩阵

| 能力 | REST | Pro | 说明 |
|---|---|---|---|
| markets / ticker / order book / public trades | True | 继承 REST | 单个合成 BTC/USDT 现货市场 |
| create_order / cancel_order / fetch_order / fetch_open_orders | True | 继承 REST | 仅 limit buy/sell；支持 clientOrderId 透传，不承诺服务端幂等 |
| balance | True | 继承 REST | free/used/total，未知不补零 |
| watch ticker / order book / orders / balance | False | True | 真正的 WS 消息，非 REST 轮询 |
| WS 下单撤单 / watch trades / OHLCV / positions / unwatch | False | False | 未实现 |
| 批量订单 / market 单 / postOnly / reduceOnly / 衍生品 | False 或参数拒绝 | 同 REST | 不假装支持 |
| fetch_account_limits | 专有方法 | 继承 REST | private、只读、返回原始额度对象 |
| 同步模式 | 未提供 | 不适用 | 注册表抛 NotSupported |

`createOrder=True` 只表示有限价单实现，不意味支持市场单等全部变体。默认 `newUpdates` 由 CCXT 控制；订单流代码处理 true/false，测试覆盖两种。

## REST 编码与签名

统一响应 `{"data": ...}`；错误 `{"error": "AUTH"}` 等。测试只使用字符串 `fixture-key` / `fixture-secret`，它们不是有效凭据。

GET 参数按键排序并 urlencode；非 GET JSON 使用排序键和紧凑分隔符。
私有请求 header 为 `X-Key`、`X-Nonce`、`X-Signature`；签名为
`HMAC-SHA256(secret, nonce + METHOD + path_with_query + body)` 的十六进制字符串。
这是演示协议，不适用于任何真实交易所。

| Method/path | 作用 | 返回 data |
|---|---|---|
| GET `/markets` | 市场元数据 | 含 base/quote/tick/step/minAmount/minCost 的列表 |
| GET `/ticker` `/book` `/trades` | 公共行情 | 原始 ticker、快照或成交列表 |
| GET `/balance` | 私有余额 | currency → free/used/total |
| POST `/order` | 限价委托 | ACK，含 ID、请求字段；不提供 fills/status |
| GET `/order?id=...` | 查询状态 | 订单状态 NEW/PARTIAL/FILLED/CANCELED/... |
| GET `/orders` | 当前订单 | 模拟服务内 NEW 订单列表；无远程分页 |
| POST `/cancel` | 撤单请求 | ACK，不等同最终 canceled |
| GET `/account/limits` | 私有特殊只读接口 | requestsPerMinute |

市场价格步长 0.1，数量步长 0.001，最小数量 0.001，最小名义金额 1。支持参数仅 `clientOrderId`；其他订单 params 抛 NotSupported。每个 endpoint 成本至少 1。

## WebSocket

- `{"op":"login","key":...,"nonce":...,"signature":...}`，签名为 nonce 的 HMAC-SHA256；等待 `{"event":"login","ok":true}`。
- `{"op":"subscribe","channel":"book","symbol":"BTC_USDT"}`；私有 `orders/balance` 在登录后订阅。
- `{"channel":"book","data":{"symbol":"BTC_USDT","kind":"snapshot","sequence":10,"bids":[...],"asks":[...]}}`。
- `kind=delta` 必须 `sequence == last + 1`。重复/旧消息丢弃，断档抛 InvalidNonce 并清缓存；下次 watch 重订阅获取快照。
- `orders` data 为订单对象列表；同 symbol+id 更新可为部分字段，保留前值。
- `balance` 无 delta 表示快照，`delta=true` 表示按币种和字段合并；首次应有快照。
- 使用 WebSocket 控制帧心跳。断连由官方 client 传播异常；下一次 watch 建立新连接。

局限：该测试服务不是撮合引擎，不验证撮合、资金扣减或真实账户余额，不实现时间戳重放窗口、分页、交易所特定频率规则或生产容灾。
