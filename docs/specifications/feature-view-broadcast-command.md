# View.broadcast_command —— View 级广播命令原语

**状态**：✅ 已完成
**日期**：2026-05-15
**类型**：功能设计（mutgui 新增 API）

> **驱动场景**：多 ViewPort 场景下 URL hash 不同步——同一 mutgui 应用被多个浏览器 tab 打开（多个 ViewPort 观察同一个 View）。Tab A 触发应用内导航后，Tab A 的 UI 和 URL 均正确更新，Tab B 的 UI 也自动重渲染（由 `View.invalidate()` 驱动），但 **Tab B 的地址栏 URL 不变**——仍显示旧 hash，与实际显示的页面不一致。
>
> 此 bug 由下游 mutagent 的 `Conversation.navigate_to` 暴露，但根因和修复点都在 mutgui：缺少与 `send_command` 配对的 View 级广播原语。mutagent 端属于消费者适配（详见末尾「下游消费者迁移指引」）。

## 需求

1. mutgui 提供 View 级的命令广播原语，覆盖「View 状态变更需要同步到所有观察者 ViewPort」的场景（如 URL hash、跨 tab 共享的客户端状态）。
2. 与现有 ViewPort 级 `send_command` 形成正交配对，调用方按状态作用域显式选择。
3. 不应引入循环事件：与现有的「`pushState`/`replaceState` 不触发 `hashchange`」防循环机制保持兼容。
4. 不应影响单 ViewPort（单 tab）场景的现有行为，不破坏 `send_command` 的语义。
5. mutgui 不感知 route / hash 等应用语义，只暴露通用广播原语（延续 `feature-system-events-and-hash-nav.md` 的设计原则）。

## 问题分析

### 根因：两个 API 的作用域不一致

| API | 作用域 | 实现 |
|-----|--------|------|
| `View.invalidate()` | **View 级** → 通知所有 ViewPort 重渲染 | `ViewObservers.viewports` 全量推送 |
| `View.send_command(name, **args)` | **ViewPort 级** → 仅当前 ViewPort | `get_current_viewport()` → `ext.channel.send()` |

当应用层（如 mutagent 的 `Conversation.navigate_to`）同时调用两者时：

```python
async def navigate_to(self, route):
    self.current_route = route
    await self.send_command("mutgui.setHash", hash=new_hash)  # → 只到 Tab A
    self.invalidate()                                          # → Tab A + Tab B 都重渲染
```

- Tab A：收到 render + 收到 setHash → UI ✅ URL ✅
- Tab B：收到 render，没收到 setHash → UI ✅ URL ❌（显示设置页但地址栏是旧 hash）

### 为什么 send_command 天生是 ViewPort 级的

`send_command` 每次调用都在某个 ViewPort 的异步上下文中（用户点击 → 事件路由 → handler 执行 → `send_command`），`get_current_viewport()` 返回的是触发该事件的 ViewPort。这是正确的默认行为——大多数命令（滚动位置、focus、动画触发、toast）就应该只影响操作的那个 tab。

问题在于 `setHash` 是 View 级状态（URL 对应的是 `current_route`，属于 View 状态，不属于某个 ViewPort），却走了一条 ViewPort 级的通道。

### 时序验证（不需要改的部分）

mutagent 的 `_server_impl.py` 中根 ViewPort 的创建已正确通过 `_client` 传入初始 hash（已在 `feature-system-events-and-hash-nav.md` 中实现）。**初始握手场景**（新 tab 直接打开 `#/settings/mcp`）工作正常，本次不动。

问题仅出现在**运行期**：一个 tab 触发导航后，其他 tab 的 URL 不被更新。

## 关键参考

- `mutgui/src/mutgui/view.py` — `View.send_command` / `View.invalidate` 声明
- `mutgui/src/mutgui/_view_impl.py` — `View.send_command` / `View.invalidate` 实现；`ViewObservers` 追踪 View→ViewPort 映射；`_deferred_render` 遍历 `viewports` 推送渲染
- `mutgui/src/mutgui/_viewport_impl.py` — `ViewPort.send_command` 实现（`ext.channel.send`）；`viewport_initialize` 初始 hash 握手
- `mutgui/src/mutgui/viewport.py` — `ViewPort` 声明，`_client` 参数
- `mutgui/frontend/src/core/navigation.ts` — `runSetHashCommand`（pushState / replaceState，幂等）
- `mutgui/frontend/src/core/system-events.ts` — `$hashchange` 事件通道（W3C 防循环）
- `mutgui/docs/specifications/feature-system-events-and-hash-nav.md` — 现有 hash 导航设计（✅ 已完成），本次延续其防循环约束
- `mutgui/docs/specifications/feature-multi-app-shell-container.md` — 多应用 shell 容器愿景（前向兼容性参考）

**下游消费者参考**（不在本仓库改动范围）：

- `mutagent/src/mutagent/webui/_conversation_impl.py` — `Conversation.navigate_to`，将作为新 API 的首个消费者适配（独立 commit，不在本文档实施清单内）
- `mutagent/src/mutagent/webui/_server_impl.py` — 根 ViewPort 创建（已传 `_client`，与本期无关）

## 设计方案

### 总体思路

mutgui 在 `View` 上新增 `broadcast_command(name, **args)`，与 `send_command` 配对：

| API | 作用域 | 适用场景 |
|-----|-------|---------|
| `View.send_command` | 当前 ViewPort | ViewPort 私有状态：滚动位置、focus、动画触发、toast |
| `View.broadcast_command` | 所有观察该 View 的 ViewPort | View 级共享状态：URL hash、跨 tab 同步的客户端状态 |

mutagent 的 `Conversation.navigate_to` 把 `send_command("mutgui.setHash", ...)` 改为 `broadcast_command("mutgui.setHash", ...)`，问题即修复。

mutgui 不感知 route 概念，只暴露"广播命令"原语，由调用方按需选择 ViewPort 级 / View 级。这与 `feature-system-events-and-hash-nav.md` 已确立的「mutgui 不引入路由语义」原则一致。

### 方案选择记录

需求文档列出 3 个方向，选择 A 的理由：

| 方向 | 决策 | 理由 |
|------|------|------|
| **A. `broadcast_command` 与 `send_command` 配对** | ✅ 采纳 | 概念正交；复用现成的 `ViewObservers.viewports`；mutgui 不引入路由语义；调用方显式选择 |
| B. `ViewBlock` 携带 `$hash` meta，前端 render 后自动同步 | ❌ 否决 | 改动 wire 协议；失去 `replace` 控制权；让 renderer 隐式接管 URL，违背「mutgui 不感知 route」原则 |
| C. ViewPort push 前自动检查 `view.current_route` | ❌ 否决 | mutgui 需要知道 `current_route` 这种应用语义，违背原则 |

### `View.broadcast_command` 声明

文件：`mutgui/src/mutgui/view.py`

```python
async def broadcast_command(self, name: str, /, **args: Any) -> None:
    """向所有观察此 View 的 ViewPort 广播命令。

    与 send_command 的差异：
    - send_command：仅当前 ViewPort（事件触发那个 tab） —— 适合 ViewPort 私有状态
      （滚动位置、focus、动画触发、toast 等）。要求当前异步上下文存在 ViewPort。
    - broadcast_command：所有观察此 View 的 ViewPort —— 适合 View 级共享状态
      （URL hash、跨 tab 同步的客户端状态）。**不**要求当前上下文存在 ViewPort，
      可在后台任务、定时器、agent 事件回调中调用。

    单个 ViewPort 发送失败（断连等）不影响其他 ViewPort。
    无观察者时静默 no-op。
    """
    raise NotImplementedError
```

### 实现

文件：`mutgui/src/mutgui/_view_impl.py`

```python
@impl(View.broadcast_command)
async def view_broadcast_command(self: View, name: str, /, **args: Any) -> None:
    obs = ViewObservers.get(self)
    if obs is None:
        return
    # 顺序串行：channel.send 通常只是 enqueue，无需并发；
    # 单点失败不影响其余 ViewPort。
    for vp in list(obs.viewports):
        try:
            await vp.send_command(name, **args)
        except Exception:
            _logger.exception(
                "broadcast_command(%s) to viewport failed", name,
            )
```

实现要点：

- **不依赖 `get_current_viewport()`**：与 `send_command` 形成对称差异，可在任何上下文调用。
- **顺序而非并发（`asyncio.gather`）**：`channel.send` 几乎只是写 WebSocket buffer，串行延迟可忽略；顺序更易排查（出错栈直观、不需要 `return_exceptions`）。
- **try/except 兜底**：单个 ViewPort 的 channel 已断或 send 抛异常时，记录日志继续处理其他 ViewPort——`broadcast` 的语义就是「尽力发给所有人」。
- **`list(obs.viewports)` 浅拷贝**：防止 send 过程中 `viewports` 列表被异步修改（如某 ViewPort 收到错误后 detach）造成迭代异常。
- **不触发 render**：`broadcast_command` 只发命令，调用方仍负责显式 `invalidate()`，与 `send_command` 行为一致。

### 子 ViewPort 场景

`ViewObservers.viewports` 包含某个 View 的**所有**观察者。多 tab 场景下，每个 tab 的根 ViewPort 都直接挂在 root View 上，broadcast 一次即覆盖所有 tab。

如果同一个子 View 实例被同一 tab 内的多处嵌入（理论存在），`broadcast` 会在该 tab 内重复发送 `mutgui.setHash`——但 `runSetHashCommand` 改的是浏览器全局 URL，与 `viewId` 无关，重复 push 同一 URL 幂等无副作用。无需特殊处理。

### 防循环验证

沿用 `feature-system-events-and-hash-nav.md` 的 W3C 天然行为：

- 后端 `broadcast_command("mutgui.setHash", ...)` → 每个 ViewPort 的 channel 各发一条 command 帧
- 前端各 tab `runSetHashCommand` → `history.pushState/replaceState`
- W3C 规定 pushState/replaceState **不**触发 `hashchange` / `popstate`
- 没有事件回流 → 不会循环 ✓

不引入新的标记位、setTimeout、内部方法绕过等机制。

### 与多应用 shell 容器愿景的兼容

`feature-multi-app-shell-container.md` 设想 mutbot 演化为基于 mutgui 的 shell，把多个 sub-app 嵌入同一入口、共享浏览器 hash。届时：

- root View 不再是 `Conversation` 而是 `AppContainer`
- `AppContainer.navigate_to` 调用 `broadcast_command("mutgui.setHash", ...)` 时，shell 拦截层（命令 dispatch 之前）按 sub-app 重写 hash 子段——这一拦截发生在前端 `runSetHashCommand` 之前，与 `broadcast_command` 后端行为正交

`broadcast_command` 不引入「root 一定是某种应用 View」的假设，前向兼容良好。

### 兼容性

- `View.send_command` 行为不变：仍是 ViewPort 级，调用方语义不变。
- 既有调用 `send_command` 的代码无需修改：默认 ViewPort 私有的命令（滚动/focus 等）应保持原行为。
- 仅 mutagent `Conversation.navigate_to` 一处需要改用 `broadcast_command`。
- 前端零改动。
- 协议零改动。

### 影响范围

| 文件 | 改动 |
|------|------|
| `mutgui/src/mutgui/view.py` | 声明 `broadcast_command` |
| `mutgui/src/mutgui/_view_impl.py` | `@impl` 实现 + 模块顶部加 logger（如尚无） |
| `mutgui/tests/integration/test_multi_viewport.py`（新） | 多 ViewPort 广播集成测试 |
| `mutgui/tests/test_view.py` 或 `tests/unit/test_broadcast_command.py`（新或扩展） | 单元测试：无观察者 no-op、单点失败不影响其他、调用顺序 |
| `mutgui/docs/specifications/feature-system-events-and-hash-nav.md` | 在「后端 send_command 的使用」一节补一段：跨 tab 同步场景请用 `broadcast_command` |

下游 mutagent 仓库的适配独立 commit，不在本文档影响范围。

## 设计决策记录

- **API 命名**：`broadcast_command`。"send"（点对点）vs "broadcast"（一对多）是网络通信通用术语，比 `send_command_all` 更短且不暴露 viewport 抽象。
- **ViewPort 上不加 `broadcast_command`**：`broadcast` 的天然主语是 View（消息源是 View 级状态变更），从 ViewPort 出发表达不自然。需要广播时通过 `view.broadcast_command(...)` 即可。
- **`exclude_current` 参数不加**：YAGNI。`mutgui.setHash` 重复发给当前 tab 幂等无副作用。未来有真实用例再加。
- **不在 mutgui 包 `set_hash` 便利方法**：延续「mutgui 不感知 route」原则。如果 mutagent 多处需要，在 mutagent 内部封 helper。

## 测试规划

### 单元测试

- `broadcast_command` 在 View 无观察者时静默 no-op
- `broadcast_command` 顺序遍历 `viewports` 调用每个 ViewPort 的 `send_command`
- 某个 ViewPort 的 `send_command` 抛异常时，其他 ViewPort 仍被调用，不向上抛
- `broadcast_command` 在没有 `current_viewport` 上下文时也能调用（与 `send_command` 行为差异）

### 集成测试

新建 `tests/integration/test_multi_viewport.py`：

- **case 1**：一个 View 挂两个 channel（模拟两 tab）；调 `view.broadcast_command("mutgui.setHash", hash="#/x")`；断言两个 channel 都收到 `command` 帧
- **case 2 回归**：`send_command` 仍只发当前 viewport（一个 channel 收到 / 另一个未收到）
- **case 3**：广播过程中一个 channel 已 detach；另一个 channel 仍能正常收到命令

## 实施步骤清单（mutgui 仓库）

- [x] `mutgui/src/mutgui/view.py` — 声明 `View.broadcast_command`
- [x] `mutgui/src/mutgui/_view_impl.py` — `@impl` 实现 `broadcast_command`（顺序遍历 viewports、单点失败不影响其余、无观察者 no-op）
- [x] mutgui 单元测试：无观察者 no-op、顺序调用 ViewPort、单点失败不抛异常、无 ViewPort 上下文也能调用
- [x] mutgui 集成测试：多 channel 都收到 command、send_command 仍只发当前 ViewPort、广播中某 channel detach 不影响其余
- [x] `mutgui/docs/specifications/feature-system-events-and-hash-nav.md` — 补一段：跨 tab 同步用 `broadcast_command`

> **下游 mutagent 适配**（独立 commit，不计入本文档进度）：见末尾「下游消费者迁移指引」。

## 消费者场景

| 消费者 | 场景 | 受影响的行为 | 验收标准 |
|--------|------|-------------|---------|
| mutagent SettingsPage 路由 | 两个 tab 打开同一 session，Tab A 进入设置页 | Tab B 显示设置页但 URL 仍是 `/` | Tab A 触发 `navigate_to("settings")` 后，Tab A 和 Tab B 的 URL **与** UI 始终一致（地址栏均显示 `#/settings`） |
| mutagent 浏览器 back/forward | Tab A 点后退，Tab B 应同频显示但 URL 不强求联动 | Tab B 的 UI 通过 invalidate 重渲染 | Tab A 后退后两个 tab 的 UI 一致；Tab B 的 URL 维持原值（浏览器原生行为，不强求跨 tab 同步） |
| 未来多 tab SPA 应用 | 任何需要 hash 路由的 mutgui 应用，多 tab 场景 | URL 与页面内容可能不一致 | 调用方使用 `broadcast_command("mutgui.setHash", ...)` 即可让多 ViewPort 场景下 URL 与 UI 一致 |
| 未来需要跨 tab 同步的 View 级命令（如全局主题切换 toast） | 广播自定义命令 | 命令仅发到当前 tab | `broadcast_command("app.theme_changed_toast")` 让所有 tab 都弹 toast |
