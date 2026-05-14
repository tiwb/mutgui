# mutgui demo 日志输出与 WebSocket 断连处理 设计规范

**状态**：✅ 已完成
**日期**：2026-04-30
**类型**：Bug修复

## 需求

1. `demo/examples/action.py` 当前点击调色板主按钮会触发后端异常，但 demo 终端几乎看不到有效日志，排查成本高。
2. `demo/framework/_server.py` 当前会吞掉 WebSocket 事件循环中的异常，导致前端只看到“网络断开”，后端没有可见 traceback。
3. 页面刷新或浏览器主动断开连接时，Windows 下可能出现 `ConnectionResetError` 等 asyncio / transport 层异常；这类“预期断连”不应污染上层业务代码或误导使用者。
4. 需要明确 mutgui demo 的默认日志行为：是否初始化 `logging`、默认 console level 是什么、是否需要文件/内存日志。
5. 需要评估断连异常的归一化应落在 `mutgui` 还是 `mutio`：目标是尽量由底层吸收 transport 噪音，而不是让每个 demo / app 单独绕过。

## 关键参考

### mutgui 现状

- `demo/framework/_server.py` — mutgui demo 的 WebSocket 生命周期；当前对业务异常存在静默吞掉问题
- `demo/examples/action.py` — 当前能稳定复现调色板按钮断连问题的 demo
- `demo/standalone/starlette.py` — 另一个 demo server 入口，同样需要统一日志与断连处理预期

### mutio 现状

- `mutio/src/mutio/net/server.py` — `WebSocketDisconnect` 语义定义
- `mutio/src/mutio/net/_server_impl.py` — websocket route 外层异常处理；潜在的统一收口位置
- `mutio/src/mutio/net/_protocol.py` — `WSProtocol` / transport 断开与 close 帧处理；预期断连归一化的底层候选位置
- `mutio/docs/specifications/bugfix-websocket-disconnect-normalization.md` — 本次底层断连归一化的 mutio 规范文档

### mutbot 参考实现

- `mutbot/src/mutbot/web/server.py` — logging 初始化、console/file/memory handler、asyncio exception handler
- `mutbot/src/mutbot/web/routes.py` — `WebSocketDisconnect` 与其他 websocket 异常的分级处理
- `mutbot/src/mutbot/auth/setup_view.py` — mutgui 风格 viewport websocket 的断连处理参考
- `mutbot/src/mutbot/web/supervisor.py` — `ConnectionResetError` / `BrokenPipeError` / `OSError` 作为预期传输层异常的处理方式

## 设计方案

- mutgui demo framework 直接初始化最小 stdout logging：默认 `INFO`，加 `--debug` 时切换为 `DEBUG`，不引入 file/memory handler。
- Gallery 入口 `python -m demo` 增加 `--debug`；demo framework 的 `run_gallery()` / `run_single()` 同步接受 `debug` 参数，保证 Gallery 和单 demo 行为一致。
- mutgui demo 的 websocket 生命周期不再静默吞异常：`WebSocketDisconnect` 仅记 `DEBUG`，真实异常输出 traceback。
- 预期断连优先在 mutio 吸收：把 `ConnectionResetError`、`BrokenPipeError`、常见 Windows `OSError` 识别为 transport 噪音，并在 websocket protocol / asyncio exception handler 中统一降级。
- `demo/standalone/starlette.py` 同步提供 `--debug` 并区分正常断连与真实异常，保持示例体验一致。

## 实施步骤清单

- [x] 为 mutgui demo 增加最小 stdout logging 与 `--debug` 参数
- [x] 修复 mutgui demo websocket 生命周期中的静默吞异常问题
- [x] 在 mutio websocket transport / asyncio 边界归一化预期断连
- [x] 补充 mutio 相关测试并运行受影响测试
