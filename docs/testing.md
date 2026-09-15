# 测试与验收

## 可重复命令

在克隆仓库根目录运行：

```bash
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run pytest -q --cov=ccxt_cm --cov-report=term-missing
uv build
```

`uv.lock` 锁定 Python 依赖。测试用 `pytest-socket` 默认禁用互联网；仅标记 `allow_hosts(['127.0.0.1'])` 的本机协议测试开放 loopback。

单独运行：

```bash
uv run pytest -q -m 'not loopback'  # 离线单元/契约
uv run pytest -q -m loopback        # 本机真实 HTTP/WS 收发，不连接交易所
```

如果环境禁止 bind 本机端口，第二条会因环境权限失败。应在允许 loopback 的测试环境运行，而不是删掉测试或称为已通过。

## 覆盖矩阵

| 层次 | 已实现测试 | 不证明什么 |
|---|---|---|
| 官方复用 | 遍历安装版本的全部 sync/async/Pro 类，验证工厂返回相同 class；验证配置与生命周期 | 不证明每家官方交易所在线、可用或有账户权限 |
| 注册 | 重复/冲突/错误类型/模式缺失/官方后续收录、显式 entry point 与批量原子注册 | 不审计外部插件是否可信 |
| 能力 | 四态、snake/camel 别名、emulated 显式选择、新基类默认不支持 | 不将 has 当真实探测结果 |
| 特殊方法 | 元数据、存在性、重复/无文档错误、原始 implicit 调用 | 不自动授予接口权限 |
| REST 契约 | 方法签名、精度、symbol、时间、原始 info、未知值、状态映射、签名、错误、参数 | 不证明真实交易所协议与这个虚构协议相同 |
| 写入边界 | ACK 状态未知、取消后显式查询、timeout 一次请求后抛异常 | 不模拟真实撮合、扣款或全局幂等 |
| WS 状态 | 认证、快照/增量、删除档位、重复/断档、重订阅、缓存有界、订单部分更新、余额合并、newUpdates | 不涵盖所有交易所 protobuf/checksum/分片协议 |
| WS transport | 本机 WebSocket 真实握手、推送、断连、再连接、任务取消、关闭 | 不等同互联网丢包压测或生产长稳测试 |
| 模板 | 未实现方法明确报错、未实现 Pro 不可选择 | 不意味着复制模板就已接入交易所 |
| 发布物 | wheel/sdist 构建和全新环境导入 | 不等同 PyPI 已发布 |

核心包 `ccxt_cm` 分支覆盖率门槛 90%。参考适配器也有单元和本机协议测试，但核心覆盖率数字不包含 examples；可额外运行：

```bash
uv run pytest --cov=ccxt_cm --cov=examples.reference_exchange --cov-report=term-missing
```

CI 在 Python 3.11/3.12/3.13 跑锁定环境，同时另跑 Python 3.12 + 当前依赖范围内最新 CCXT。每次 PR/push 触发，支持手动运行；没有后台真实交易测试。

## 新增交易所必须补的测试

- 每个 has=True 方法：至少成功/业务错误/不支持参数；与上游方法签名一致。
- 每种认证方式：固定时钟签名 golden case、查询编码、body 字节、错误映射。
- 每种支持市场：symbol/settle、单位、contractSize、精度/limits、暂停交易状态。
- 订单：限价/市价/特殊参数实际支持范围，部分成交、成交、撤单拒绝、ACK-only、超时未知。
- 批量：全成功、部分成功、部分失败、未知项、每项关联关系；分页：不遗漏/重复/越界。
- WS：认证拒绝、重复/乱序/断档、快照恢复、心跳、断连、重新认证、未知/畸形载荷。
- 敏感信息：日志/异常不包含凭据或签名；fixtures 脱敏；不同账户/环境缓存隔离。
- sandbox/生产 URL 切换：REST 与 WS 一起切换，不混连；未提供测试环境时明确报错。

## 实际交易所验收另行记录

模板：

| 字段 | 记录内容 |
|---|---|
| 版本 | 适配器 commit、Python、CCXT 版本 |
| 范围 | 交易所、环境、市场类型、方法，不记录密钥 |
| 证据 | 只读响应/脱敏日志/测试报告，日期与时区 |
| 写入 | 是否进行了真实操作、订单核查方式、剩余未知结果 |
| 局限 | 未覆盖的方法、账户权限与协议场景 |

本阶段只有离线与本机协议验收。没有真实密钥、实盘订单、交易所 sandbox 订单或生产部署。

## 0.1.0 本地验收记录（2026-09-15）

- macOS arm64，Python 3.12.13，CCXT 4.5.78，锁定环境。
- `ruff check`、`ruff format --check` 通过。
- 全量 **69 tests passed**：66 项离线测试，3 项本机 HTTP/WS 协议集成测试。
- `ccxt_cm` 四个运行时模块的语句+分支覆盖率 **100%**；连同 reference 示例的总覆盖率 **98.91%**。
- wheel 与 sdist 构建成功；在独立空环境安装 wheel 后，从仓库外导入并解析官方 Pro 类成功。
- 检查发布包未包含官方 CCXT 源码、参考压缩包、虚拟环境或真实密钥。
- 已知输出：本机 aiohttp/CPython 对 `enable_cleanup_closed` 有 3 条依赖层 DeprecationWarning，不影响测试通过；未为消除提示而修改官方依赖源码。
- GitHub CI 状态以 Actions 当前记录为准，不将本地通过等同远程 CI 通过。
