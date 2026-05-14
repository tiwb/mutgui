# 渲染职责迁移 — render 循环从 ViewPort 回归 View

**状态**：✅ 已完成
**日期**：2026-04-17
**类型**：重构

## 需求

1. 当前 ViewPort 同时承担"渲染引擎"和"传输管道"两个角色，render 循环、callback registry、子 View 管理全在 ViewPort（`_viewport_impl.py`）中
2. 同一 View 被 N 个 ViewPort 观察时，render() 被调用 N 次，产出完全相同的结果——render 输出取决于 View 状态，与 ViewPort/Channel 无关
3. callback registry `{(component_id, event_name): callable}` 也完全由 View.render() 输出决定，不依赖具体 ViewPort
4. 需要将渲染职责从 ViewPort 迁移到 View，使 ViewPort 回归"纯管道"定位

### 前置依赖

- `feature-session-sharing.md` — 核心抽象 Declaration 化（View/Channel/ViewPort），已完成

### 问题来源

`feature-session-sharing` 实施中发现：多个 ViewPort 观察同一 View 时，每个 ViewPort 独立调用 render() 再独立序列化——渲染结果完全相同，callback registry 完全相同，wire tree 完全相同。唯一不同的是发送目标（Channel）。

这不是新引入的耦合，而是从最初的 ViewSession 设计就存在的：ViewSession 把 render 循环、callback registry、子 View 管理、事件路由、传输全揉在一个类里。Declaration 化重构搬了架构但没拆职责。

## 关键参考

### 内部实现

- `mutgui/src/mutgui/view.py` — View Declaration（render/invalidate/on_event 桩方法）
- `mutgui/src/mutgui/viewport.py` — ViewPort Declaration（initialize/handle_event/flush/detach 桩方法）
- `mutgui/src/mutgui/_viewport_impl.py` — 当前全部渲染逻辑所在：
  - `ViewPortRuntime` Extension — `_callbacks`, `_children`, `_dirty` 等状态
  - `_render_and_send()` — render → process → send 循环
  - `_process_items()` / `_process_node()` / `_process_tagged()` — 组件树序列化
  - `_route_event()` — 事件路由
- `mutgui/src/mutgui/_view_impl.py` — ViewObservers Extension（当前只做 invalidate 通知）
- `mutgui/src/mutgui/events.py` — TAG_KEY, handler/bind/notify helper

### 设计文档

- `mutgui/docs/specifications/feature-session-sharing.md` — 上一次重构的完整设计（架构图、接口设计、集成模型）
- `mutgui/docs/explorations/2026-04-15-protocol-layer-design-exploration.md` — 协议层探索（Connection/ViewPort 概念）

### 当前架构（职责分布）

```
View (Declaration)                    ViewPort (Declaration)
├── render()          桩              ├── initialize()      桩
├── on_event()        桩              ├── handle_event()    桩
├── invalidate()      桩              ├── flush()           桩
│                                     └── detach()          桩
│
_view_impl.py                         _viewport_impl.py
├── ViewObservers Extension            ├── ViewPortRuntime Extension
│   └── _viewports: list                  ├── _view, _channel, _path
│                                         ├── _callbacks    ← View 的事
├── @impl invalidate                      ├── _children     ← View 的事
│   → 通知所有 ViewPort                    ├── _dirty        ← View 的事
├── @impl render → []                     │
└── @impl on_event → pass              ├── _render_and_send  ← View 的事
                                       ├── _process_items    ← View 的事
                                       ├── _process_tagged   ← View 的事
                                       ├── _route_event      ← View 的事
                                       └── _mark_dirty       ← View 的事
```

标注 "← View 的事" 的部分，其输出不依赖 ViewPort/Channel，只依赖 View 状态。

## 设计方案

### 目标架构

```
View (Declaration)                    ViewPort (Declaration)
├── render()          桩              ├── __init__(view, channel)  桩
├── on_event()        桩              ├── initialize()             桩
├── invalidate()      桩              ├── handle_event()           桩
├── handle_event()    桩（新增，async） └── detach()                 桩
├── rendered()        桩（新增，async）
│
_view_impl.py                         _viewport_impl.py
├── ViewRenderState Extension          ├── ViewPortRuntime Extension
│   ├── _callbacks: dict               │   ├── _channel
│   ├── _children: dict[id, View]      │   ├── _path
│   ├── _wire_tree: list (缓存)        │   └── _child_viewports: dict
│   ├── _dirty: bool                   │
│   ├── _render_scheduled: bool        ├── @impl initialize
│   └── _render_event: asyncio.Event   │   → 注册为 View 观察者
├── ViewObservers Extension            │   → 触发 View render（如需要）
│   └── _viewports: list              │
│                                      ├── @impl handle_event
├── @impl render → []                  │   → 转交 View.handle_event()
├── @impl on_event → pass              │
├── @impl invalidate                   └── @impl detach
│   → 标脏 + call_soon(render)             → 移除观察者
├── @impl handle_event（新增）
│   → 路由事件 → 查 callback → 调用
│   → invalidate()
│
├── _deferred_render (内部，async)
│   → render → serialize → cache
│   → push wire_tree 给所有 ViewPort
│
├── _render_and_cache (内部)
│   → render → serialize → 缓存
│   → 一次 render，N 个 ViewPort 共享
│
├── _process_items (内部)
├── _process_node (内部)
└── _process_tagged (内部)
```

### 核心变更

**1. 渲染逻辑迁移到 View 侧**

render → serialize → 缓存 wire_tree 全部在 `_view_impl.py` 中完成。View render 一次，结果缓存，所有 ViewPort 共享同一份 wire_tree。

**2. View 驱动 render 周期（push 模型）**

当前是 ViewPort 拉取式（flush 时检查 dirty → render）。迁移后改为 View 推送式：

- `invalidate()` → 标 View dirty + schedule render（`call_soon`）
- render callback 执行时：render → serialize → cache → push wire_tree 给所有 ViewPort
- ViewPort 被动接收 wire_tree 并发送到 channel

这消除了当前的 workaround：demo/app.py 手动循环 flush 其他 ViewPort、测试中手动调用 `vp_b.flush()`。

**render 调度机制**（标准 asyncio coalescing 模式）：

```python
def invalidate(self):
    self._dirty = True
    if self._render_scheduled:        # 已有调度在排队
        return
    self._render_scheduled = True
    try:
        loop = asyncio.get_running_loop()
        loop.call_soon(lambda: asyncio.ensure_future(self._deferred_render()))
    except RuntimeError:
        pass                           # 无事件循环时只标脏

async def _deferred_render(self):
    self._render_scheduled = False     # 先重置 flag（render 中若再 invalidate 能重新调度）
    if not self._dirty:                # 防御性检查
        return
    self._dirty = False
    wire_tree = self._render_and_cache()
    for vp in self._viewports:
        await vp._send(wire_tree)      # channel.send() 是 async
```

- `_render_scheduled` flag 去重，多次 invalidate 合并为一次 render
- `call_soon` 在当前事件循环 tick 结束后执行，同步调用栈内的所有 invalidate 自然合并
- 无事件循环时降级为只标脏（`__init__` 或纯同步代码），render 由后续的 initialize 或 handle_event 触发
- 未来若需节流（如 30ms 最多 render 一次），只需将 `call_soon` 改为 `call_later(0.03, ...)`，模式不变

**3. callback registry 迁移到 View 侧**

`_callbacks` 放在 `ViewRenderState` Extension 中。callback 查找和调用也在 View 侧——View 新增 `handle_event()` 桩方法，由 @impl 提供事件路由和 callback 调用。

**4. 子 View 管理迁移到 View 侧**

`_children` 从 `dict[id, ViewPort]` 变为 `dict[id, View]`——父 View 持有子 View 引用，不再持有子 ViewPort。子 View 的 ViewPort 按需创建（当 ViewPort 收到 push 时，为子 View 找到或创建对应的子 ViewPort）。

**5. ViewPort 变为纯管道**

ViewPort 只剩：
- `_channel`：发送目标
- `_path`：viewId 路径（用于嵌套 View 的 JSON 消息中的 `viewId` 字段）
- 转发事件给 View
- 接收 View push 的 wire_tree 并发送到 channel
- 按需为子 View 创建/管理子 ViewPort

**6. dirty 状态迁移到 View**

dirty 是"View 的状态变了，需要重新 render"——这是 View 的事，不是 ViewPort 的事。`invalidate()` 标 View dirty 并 schedule render，render 后自动 push 给所有 ViewPort。

### 数据流对比

**当前**（N 个 ViewPort 各自 render，其他 ViewPort 需手动 flush）：
```
View.invalidate()
  → 标脏所有 ViewPort（_schedule_flush 只标 dirty）
  → handle_event 内 flush 自己：render() → serialize → send(channel_A)
  → 其他 ViewPort 需外部手动 flush：render() → serialize → send(channel_B)
  render() 调用 N 次，serialize N 次，且需要 workaround
```

**目标**（View render 一次，主动 push 给所有 ViewPort）：
```
View.invalidate()
  → call_soon: render() → serialize → cache wire_tree
  → push: ViewPort A → send(wire_tree, channel_A)
  → push: ViewPort B → send(wire_tree, channel_B)
  render() 调用 1 次，serialize 1 次，send N 次，无需 workaround
```

### 公开接口变更

**View 新增**：
```python
# view.py
class View(Declaration):
    ...
    async def handle_event(self, event: dict[str, Any]) -> None:
        """处理前端事件 — 路由到 callback 或 fallback 到 on_event()。"""
        ...

    async def rendered(self) -> None:
        """等待 deferred render 完成。如果不 dirty，立即返回。"""
        ...
```

- `handle_event()`：async，完整的事件处理入口（路由 + callback 查找 + 调用）。callback 返回 coroutine 时自动 await，支持异步回调（如网络请求、LLM 调用）。ViewPort 收到事件后直接转交
- `rendered()`：等待下一次 deferred render 完成的 awaitable。内部用 `asyncio.Event`，`_deferred_render` 完成时 set。用于需要确认 render 已完成的场景（测试、initialize 后发额外消息等）
- 原有的 `on_event()` 保持不变，作为 fallback

**ViewPort 变更**：
- 去掉 `flush()` 桩 — render 统一由 View 通过 call_soon 驱动，ViewPort 不再主动触发 render
- `initialize()` 不再保证返回时客户端已收到初始树。如需等待，调用方 `await view.rendered()`
- `handle_event()` 变为纯转发：`view.handle_event(event)`，render 由 invalidate → call_soon 自动发生

### 嵌套 View 的处理

当前嵌套 View 在 render 时由父 ViewPort 为子 View 创建子 ViewPort。迁移后：

- 父 View render 时识别子 View 实例，记录在 `_children: dict[id, View]`
- wire_tree 中生成 `{"$view": id}` 占位符（与当前相同）
- ViewPort 收到 push 时，检查 View._children，为新子 View 按需创建子 ViewPort（绑定同一 channel），触发子 View 初始 render
- 子 View 状态变化时独立 invalidate → 独立 schedule render → push 给自己的 ViewPort 观察者
- 子 View 的 callback registry 和 dirty 状态在子 View 自己的 ViewRenderState 中

### 与 mutbot 集成

集成接口不变：
```python
class GuiSession(Session):
    async def on_connect(self, channel, ctx):
        vp = ViewPort(self.view, adapter)
        await vp.initialize()
    async def on_message(self, channel, raw, ctx):
        vp = self._find_viewport(channel)
        await vp.handle_event(raw)     # ViewPort 转交 → View.handle_event()
```

集成方不再需要手动 flush 其他 ViewPort —— invalidate() 自动 schedule render 并 push 给所有观察者。

### Q1 决策：子 ViewPort 的生命周期管理

子 ViewPort 由 ViewPort 在收到 push 时按需创建（lazy），持有在 ViewPortRuntime Extension 中。View 侧只管 `_children: dict[id, View]`，不涉及 ViewPort。父 ViewPort detach 时递归 detach 子 ViewPort。

### Q2 决策：wire_tree 缓存的失效时机

缓存在 render 时更新，invalidate() 标 dirty。下次 render 时重新生成并更新缓存。多次 invalidate 合并为一次 render（dirty coalescing），与当前行为一致。

### Q3 决策：render 统一延迟，无立即路径

所有 render 统一走 `call_soon` 延迟调度，不区分"事件触发"和"程序化触发"。handle_event 后不立即 render —— 与标准 UI 框架一致（事件改状态，render 延迟到下一帧）。需要等待 render 完成时，使用 `await view.rendered()`。

### Q4 决策：去掉 ViewPort.flush()

ViewPort 完全被动，不主动触发 render。render 由 View 的 invalidate → call_soon 统一驱动。原 flush() 的使用场景由 `await view.rendered()` 覆盖。

## 实施步骤清单

- [x] View Declaration 新增 `handle_event()` 和 `rendered()` 桩方法，去掉 ViewPort 的 `flush()` 桩方法
- [x] 新建 `ViewRenderState` Extension（_callbacks, _children, _wire_tree, _dirty, _render_scheduled, _render_event）
- [x] 迁移序列化逻辑到 `_view_impl.py`（_process_items, _process_node, _process_tagged, _make_bind_callback）
- [x] 实现 `_render_and_cache`（调用 view.render → 序列化 → 更新缓存/callbacks/children）
- [x] 实现 `_deferred_render`（async：检查 dirty → _render_and_cache → push wire_tree 给所有 ViewPort → set _render_event）
- [x] 更新 `invalidate()` @impl（标 dirty + call_soon 调度 _deferred_render，_render_scheduled 去重，无事件循环降级）
- [x] 实现 `handle_event()` @impl（async，事件路由 + callback 查找，callback 返回 coroutine 时自动 await，从 _viewport_impl.py 迁移 _route_event 逻辑）
- [x] 实现 `rendered()` @impl（await _render_event，不 dirty 时立即返回）
- [x] 简化 ViewPortRuntime Extension（只保留 _channel, _path, _child_viewports）
- [x] 更新 ViewPort.initialize()（注册观察者 + invalidate 触发首次 render）
- [x] 更新 ViewPort.handle_event()（纯转发给 View.handle_event）
- [x] 实现 ViewPort._send()（接收 wire_tree + 为子 View 按需创建/管理子 ViewPort + 发送到 channel）
- [x] 更新 ViewPort.detach()（移除观察者 + 递归 detach 子 ViewPort）
- [x] 更新 demo/app.py（去掉手动 flush workaround；重构布局——submit 按钮和结果从 SubscriptionView 移到 RootView，RootView 增加 render counter，覆盖父 View 自有组件 + 子 View 混排 + 跨 View 读取状态三种场景）
- [x] 更新测试（适配延迟 render 模型，使用 `await view.rendered()` 或 `asyncio.sleep(0)` 等待 render）
- [x] 运行全部测试验证
