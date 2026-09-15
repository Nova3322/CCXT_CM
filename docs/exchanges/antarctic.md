# Antarctic 参考代码审计与迁移前提

## 结论

附件可用于理解其 REST 路由、私有签名和 WebSocket protobuf/JSON 分流，但**不宜直接发布为 CCXT 标准适配器**。
本次没有把 Antarctic 注册进运行时，也没有声称该交易所已通过实盘验证。没有将压缩包整体上传，也没有执行其中脚本。

来源：用户提供的 `marketmaker-prod 2.zip`。
SHA-256：`b15c45cc67e6091814010869dd8661b82ed13b76fdd0117f8c2d98c62814e008`。
下表路径均相对压缩包中的 `marketmaker-prod/market_maker/data_processing/exchange/antarctic/`，行号指原始附件，不是本仓库示例。

## 已确认的问题

| 位置 | 观察到的事实 | 对标准接入的影响 |
|---|---|---|
| `async_support_antarctic.py:755` | `create_order` 顺序为 symbol、**side、type**、amount… | 与 CCXT symbol、**type、side**… 相反，直接替换调用会错位 |
| 同文件 `441–443`、`695–697` | `fetch_trades`、`fetch_orders` 为 `pass`，但 has 声明支持 | 会用空返回冒充支持，应先标 False 并显式抛 NotSupported |
| 同文件 `662–697` | `fetch_open_orders` / `fetch_orders` 未按标准接收 since/limit | 方法契约不兼容 |
| 同文件 `662–684` | fetch_open_orders 最多再取一次下一页 | 大量未完成订单时可能截断，不能当全量账户事实 |
| 同文件 `755–781` | 下单 ACK 后填 open、filled=0、average=0，并把当前时间设为成交时间 | 这些字段并非由 ACK 证明，应保留未知或查询实际状态 |
| 同文件 `857–872` | 撤单注释假定快速撤单成功，随后直接设 canceled | ACK 与最终撤单状态混淆 |
| 同文件 `819–855` | 批量订单路径直接返回原始 response | 与标准 Order 列表/逐项结果语义未统一 |
| 同文件 `22`、`420–439`、`783–784` | 杠杆缓存在类级可变 dict，默认值 10 | 可能跨实例串账户状态；配置未知不应填默认交易杠杆 |
| 同文件 `251–400` | market 解析把 PERPETUAL 同时归入 future，默认 contractSize=1，并混入 minQty × contractSize 换算 | 需重新核对永续/交割分类、amount 单位与市场状态 |
| `antarctic_pro.py:261–290` | depth 增量直接变更当前缓存，没有此处可见的序号连续性校验 | 不能据此宣称已实现断档检测 |
| `antarctic_pro.py:62–137` 等 | 部分解析错误只记录日志/traceback | 等待中的 watch 可能不及时收到异常，需 reject 和缓存失效设计 |
| REST/Pro `describe()` | 大量泛化 has=True；端点包含占位值，声明范围大于已证明能力 | 应逐项重建能力矩阵，而不是照搬 |

这些结论来自静态检查。没有登录该交易所，没有对签名或生产端点做真实认证，也没有把附件中的协议当成当前官方文档。

## 可参考但需重做测试的部分

- `antarctic_abstract.py` 中使用 `Entry` 的 implicit endpoint 组织方式。
- REST 的 symbol、order、balance、position 解析意图和私有签名流程。
- `public_ws.proto` 描述的二进制消息结构；公开行情和私有事件使用不同载荷的分流。
- 单个/批量订单、账户余额/持仓，以及专有 endpoint 的接入需求。

本库的本机示例采用不同的虚构协议，不冒充实现上述 Antarctic 接口。

## 真正接入前需要的资料

1. 当前有效 API 文档与版本，生产/测试 HTTPS/WSS 地址，以及发布该适配器需要的代码/协议许可。
2. 脱敏的真实市场、订单、成交、余额、持仓、错误响应；确认单位、状态和时间字段。
3. 下单/撤单 ACK 与最终结果的区别；clientOrderId 是否可查询、服务端是否去重。
4. WS 认证 ACK、订阅 ACK、完整快照/增量、sequence/checksum/重放规则、断连行为。
5. 有效 protobuf schema 与可重现代码生成，测试二进制样本。
6. 各 endpoint 的限流成本、权限与批量逐项错误格式。

然后按 `docs/adding-exchanges.md` 分阶段实现，先 REST 只读与解析，再写接口，再 Pro；每项 has 只在对应实现和测试完成后打开。无需修改 CCXT_CM 工厂。
