# mutgui 内置导航命令与 command demo 迭代

**状态**：✅ 已完成
**日期**：2026-04-29
**类型**：功能设计

## 需求

1. `command` demo 当前用 `data:` URL 演示 `mutgui.redirect`，体验不直观，用户容易误判为“没有反应”。
2. mutgui 目前只有 `mutgui.redirect({ url, replace? })`，还没有 `history.back()`、`history.forward()`、`reload()` 这类浏览器导航原语。
3. mutbot 以前出现过多种导航语义，但这些不应直接塞进 mutgui core；mutgui 应只提供通用浏览器导航能力。

## 关键参考

- `frontend/src/core.tsx` — 当前内置 `mutgui.redirect` 的注册位置
- `frontend/src/core/commands.ts` — 命令注册表与命令上下文
- `demo/examples/command.py` — 当前 command demo，使用 `data:` URL
- `tests/test_command_channel.py` — command wire message 单元测试
- `tests/integration/test_command_channel.py` — redirect 与 unknown command 的真实浏览器测试
- `docs/specifications/feature-protocol-command-channel.md` — command channel 的原始协议设计

## 设计方案

### mutgui 只内置浏览器导航原语

本轮内置命令限定为浏览器自身已有的基础导航操作：

- `mutgui.redirect({ url, replace? })`
- `mutgui.history({ delta })`
- `mutgui.reload()`

这样 mutgui 提供的是“浏览器原语的后端触发入口”，而不是应用级路由框架。像 mutbot 的 workspace/hash/返回策略，仍然由上层应用决定。

### 命令语义

#### redirect

- `replace` 缺省为 `false`
- `replace=false` 时执行普通整页导航
- `replace=true` 时覆盖当前 history 记录

前端实现改为 `window.location.assign(url)` / `window.location.replace(url)`，便于测试，也更明确表达浏览器导航语义。

#### history

- `delta` 为整数
- `-1` 等价于 back
- `1` 等价于 forward
- 其他值直接映射到 `history.go(delta)`

mutgui 不单独内置 `back` / `forward` 多个命令，避免命令面增长过快。

#### reload

- 无参数
- 直接执行 `window.location.reload()`

### command demo 改造

`command` demo 改成多路由示例，不再依赖 `data:` URL：

- `/`：命令首页，提供普通 redirect、replace redirect、reload、unknown command 按钮
- `/redirected/`：普通跳转目标页，提供 `history(-1)` 返回上一页按钮
- `/replaced/`：replace 跳转目标页，说明 replace 会覆盖当前 history 记录，并提供普通 redirect 返回首页按钮

首页额外显示当前 websocket `channel_id`，用于让 `reload()` 的“重建连接”效果可见。

### 测试策略

- 前端单元测试：验证内置导航命令分别调用 `location.assign`、`location.replace`、`history.go`、`location.reload`
- Python 集成测试：
  - 普通 redirect 能到达目标页
  - 目标页触发 `history(-1)` 能返回来源页
  - `reload()` 会重新建立 websocket 连接，并产生新的 `channel_id`
  - unknown command 仍然只 warning、不崩溃

## 消费者场景

| 消费者 | 场景 | 依赖的输出 | 验收标准 |
|--------|------|-----------|---------|
| mutgui demo | 在 gallery 中理解 command channel 能做什么 | 直观的导航目标页与返回行为 | 点击后能看到明确页面变化，不需要猜 `data:` URL 是否成功 |
| mutbot 等上层应用 | 需要从后端触发浏览器基础导航 | `redirect/history/reload` 三个内置命令 | 可直接复用浏览器原语；应用级路由语义仍由上层自己扩展 |

## 实施步骤清单

- [x] 新增导航命令迭代文档，并明确 mutgui / 应用层的职责边界
- [x] 扩展 mutgui 前端内置命令，提供 `history` 与 `reload`
- [x] 改造 command demo 为可观察的多路由导航示例
- [x] 补前端与 Python 测试，并完成浏览器验收

## 测试验证

- `npm --prefix frontend run test`
- `npm --prefix frontend run build`
- `python -m pytest tests/test_command_channel.py`
- 浏览器验收（chrome-cdp）
  - 首页 `reload` 后 `channel_id` 从 `1` 变为 `2`
  - `redirected/` 页面可通过 `history(-1)` 返回首页
  - `replaced/` 页面正常到达，且通过普通 redirect 返回首页
  - unknown command 仅输出 warning，不影响页面继续使用
