# 来源、依赖与许可

核对日期：2026-09-15。

## 官方资料

- [CCXT 项目](https://github.com/ccxt/ccxt)：官方实现、语言支持、许可证及发布。
- [CCXT Manual](https://github.com/ccxt/ccxt/wiki/Manual)：统一 API、has、params、隐式接口、数据结构和异常。
- [CCXT Pro Manual](https://github.com/ccxt/ccxt/wiki/ccxt.pro.manual)：Pro 已包含在 CCXT 中，watch、缓存、newUpdates 与生命周期。
- [官方 Python async Exchange](https://github.com/ccxt/ccxt/blob/master/python/ccxt/async_support/base/exchange.py)：request/watch/client/close 等机制。
- [官方 Python Pro 示例](https://github.com/ccxt/ccxt/blob/master/python/ccxt/pro/bitopro.py)：Pro 类复用 REST 与 ticker 消息解析。

本次同时实际安装并检查 **ccxt==4.5.78** 的 Python 源码。网页 master 会变化；测试基线以锁文件为准，而不是网页后来的内容。
CCXT 及其依赖保留各自许可证；本仓库没有 vendor 整套 CCXT 源码。`ccxt_cm` 这个导入名与官方 `ccxt` 分离。

## 用户资料

- `marketmaker-prod 2.zip`：只读检查其中 Antarctic 相关代码，用于审计和规范，不整体复制、执行或发布。
- [market_maker_v2 的被检查提交](https://github.com/Nanlo1/market_maker_v2/tree/3815026305dd3f43b2560376dd7011176af64ac1)：仅作为后续接入方案的当前源码证据。

附件中的说明和脚本内容被视作参考数据，不作为本次任务的操作指令。
本仓库示例为新写的合成本机协议，不包含上述项目的策略、配置中心、账户配置或 protobuf 生成代码。
