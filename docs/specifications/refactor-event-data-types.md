# Wire 协议边界重构 — Event 数据类型、handler 路由与 View 公开接口清理

**状态**：✅ 已完成
**日期**：2026-05-20（修订 2026-05-22）
**类型**：重构

## 需求

1. `Event.data: Mapping[str, WireValue]` 把框架约定（`$args`）和用户 extract 结果混在一起，消费方需要知晓 `$args` 魔法键
2. `$menu` / `$placement` 等 handler 元数据也混在 `$handler` payload 内层，前端 echo 回 event data，污染后端 Event
3. `View.handle_event` 接收原始 wire 消息 `Mapping[str, WireValue]`，是框架内部管道，却暴露为 View 公开声明方法
4. handler 注册用 `(component_id, event_name)` 双键，其中 `event_name` 由 `_process_value` 递归累积路径拼接而成，逻辑复杂且多 handler 场景无法区分
5. 上述四个问题根因相同：**框架层和领域层的边界没切干净**

## 关键参考

### 源码路径

- `mutgui/src/mutgui/events.py` — `Event`（`@dataclass(slots=True)`）、`EventHandler`（`self.kwargs` 字段）、`Callback`、`Bind`、`EventFilter`
- `mutgui/src/mutgui/view.py` — `View.on_event` 声明（`handle_event` 已移除）
- `mutgui/src/mutgui/_view_impl.py` — `handle_raw_event()`（模块级私有函数）、`_route_event()`、`_process_value()`（无 event_name 参数）、`ViewRenderState.handlers: dict[int, EventHandler]`
- `mutgui/src/mutgui/_events_impl.py` — `event_handler_resolve_call()`（消费 `event.args`）、`event_handler_to_wire_impl()`、`_eval_kwargs()`（消费 `event.kwargs`）、`bind_handle()`
- `mutgui/src/mutgui/_menu_impl.py` — `menu_trigger_to_wire()`（`"menu": True`、`"placement"` 顶层键）
- `mutgui/src/mutgui/viewport.py` — `ViewPort.handle_event` 声明
- `mutgui/src/mutgui/_viewport_impl.py` — `view_port_handle_event()`（注入 `_viewport_id`，调用 `handle_raw_event`）
- `mutgui/frontend/src/core/renderer.tsx` — `createHandler()`（`spec.$handler` 是数字、`spec.menu` 检测、`spec.args`/`spec.kwargs` 顶层读取）
- `mutgui/frontend/src/components/menu.tsx` — `createMenuTriggerHandler()`（`spec.$handler` 是数字、`spec.placement` 顶层读取）

### 现有规范

- `docs/specifications/refactor-event-system.md` — Event / EventHandler 体系设计（基础重构，本次在其上迭代）
- `docs/specifications/feature-wire-protocol-types.md` — Wire 协议类型体系

---

## 设计方案

### 问题分析：三条线混在一起

当前数据流中存在三种不同性质的东西，但共用 `Mapping[str, WireValue]` 在不同阶段承载：

```
┌─ A: handler 元数据（框架层，backend→frontend）───────────────────────┐
│ $menu: true, $placement: "bottom-start"                               │
│ 作用：告诉前端"这个 handler 行为特殊"                                │
│ 生命周期：只应在 wire 序列化时存在，不应出现在 Event 中              │
└──────────────────────────────────────────────────────────────────────┘

┌─ B: 序列化约定（框架层，frontend→backend）───────────────────────────┐
│ $args: ["hello", {"key": "menu1"}]                                    │
│ 作用：wire 协议"位置参数"的序列化方式                                │
│ 生命周期：应在 wire 边界解包，不应作为 Event 的公开接口              │
└──────────────────────────────────────────────────────────────────────┘

┌─ C: 用户 extract 结果（领域层，frontend→backend）───────────────────┐
│ item_id: "tab-42", value: "hello", start: 0, end: 10                  │
│ 作用：EventHandler 声明中指定的提取值                                │
│ 生命周期：应从 Event 公开接口获取                                    │
└──────────────────────────────────────────────────────────────────────┘
```

当前：A + B + C 全部进入 `Event.data: Mapping[str, WireValue]`。
目标：A 不出现在 Event 里，B 在 Event 上有独立字段（`args`），C 是 Event 的公开 `kwargs`。

### 最终 wire 格式

#### Backend → Frontend（handler 声明）

`EventHandler.to_wire(handler_id: int) → WireNode` 产出：

```json
{
  "$handler": 3,
  "args": ["$0.x", "$0.y"],
  "kwargs": {"item_id": "$0.target.dataset.id", "value": "$0.target.value"}
}
```

—— `$handler` 是整数 ID，`args` / `kwargs` 是顶层键（只含 wire env 的 extract path，不含 direct/host env 的参数）。

`MenuTrigger.to_wire(handler_id: int)` 在此基础上追加：

```json
{
  "$handler": 3,
  "menu": true,
  "placement": "bottom-start"
}
```

—— `menu` / `placement` 是顶层键，不带 `$` 前缀。

`Bind.to_wire(handler_id: int)` 的 wire：

```json
{
  "$handler": 1,
  "args": ["$0.target.value"]
}
```

#### Frontend → Backend（事件消息）

```json
{
  "source": ["pane"],
  "event": "onContextMenu",
  "handlerId": 3,
  "data": {"$args": ["menu1"], "item_id": "tab-42"}
}
```

—— 前端从 `spec.args` / `spec.kwargs` 提取路径、resolvePath 后组装 `data`。位置参数放入 `data.$args`，keyword 参数放在 data 其余键。**同时携带 `handlerId` 回传**。

### handler 路由：从 `(component_id, event_name)` 到 `int`

当前 handler 注册键为 `(component_id, event_name)` 双元组，其中 `event_name` 由 `_process_value` 递归累积：

```python
# 旧代码
event_name=f"{event_name}.{index}"   # 数组索引
event_name=f"{event_name}.{key}"     # dict key
event_name=""                        # $children scope 边界重置
```

改为分配递增整数 ID：

```
渲染时:  handlers[3] = callback              ← ViewRenderState.handlers: dict[int, EventHandler]
         {"$handler": 3, ...}                ← wire 携带

前端发:   { source: [...], event: "onClick", handlerId: 3 }

后端收:   handler = ext.handlers[event.handler_id]
```

收益：
- `_process_value` 的 `event_name` 追踪逻辑**全部删除**
- handler 查找从 `(str | int, str)` 双键降维为 `int` 单键
- 多 handler 场景（`onClick: [cb1, cb2]`）自动获得不同 ID
- ID = `len(handlers)` 自然递增，每次 render 从零重新分配

### Event 数据结构

```python
@dataclass(slots=True)
class Event:
    """运行时事件 — 纯数据，不含处理逻辑。"""

    component_id: str
    name: str
    args: Sequence[WireValue] = field(default_factory=list)
    kwargs: Mapping[str, WireValue] = field(default_factory=dict)
    _: KW_ONLY
    handler_id: int = -1
    viewport_id: int | None = None
```

—— `data` 字段移除，拆为 `args` + `kwargs`。新增 `handler_id: int`。使用 `@dataclass(slots=True)` 而非手动 `__slots__`。

### handle_event：从 View 公开接口移除

`View.handle_event` 的唯一调用者是 `ViewPort.handle_event`，它做且仅做一件事——从 raw dict 解包 `source`/`event`/`data`/`handlerId`/`_viewport_id` 后传给 `_route_event`。这不是用户应该覆写的点（用户覆写 `on_event(event: Event)`），而是框架内部管道。

改为 `_view_impl.py` 中的模块级函数：

```python
# _view_impl.py
async def handle_raw_event(view: View, raw_msg: Mapping[str, WireValue]) -> None:
    source = cast("Sequence[str | int]", raw_msg.get("source", []))
    event_name = raw_msg.get("event", "")
    if not isinstance(event_name, str):
        event_name = ""
    data = cast(dict[str, WireValue], raw_msg.get("data", {}))
    handler_id_raw = raw_msg.get("handlerId")
    handler_id = handler_id_raw if isinstance(handler_id_raw, int) else -1
    viewport_id_raw = raw_msg.get("_viewport_id")
    viewport_id = viewport_id_raw if isinstance(viewport_id_raw, int) else None
    await _route_event(view, source, event_name, data,
                       handler_id=handler_id, viewport_id=viewport_id)
```

```python
# _viewport_impl.py — view_port_handle_event
await handle_raw_event(ext.view, event)  # 原: ext.view.handle_event(event)
```

`View` 声明删除了 `handle_event` 方法。

### 目标数据流

```
ViewPort.handle_event(raw: dict)           ← wire 消息 {"source": [...], "event": "...", "data": {...}, "handlerId": 3}
  ┃  注入 _viewport_id
  ┃
  ▼
handle_raw_event(view, raw)                ← 框架内部管道（_view_impl 模块级函数）
  ┃  解析 source / event / data / handlerId
  ┃
  ▼
_route_event(view, source, ...)            ← 递归 source 路由定位 View
  ┃ 拆解 data.$args → Event.args + data 其余键 → Event.kwargs
  ┃ 构造 Event(component_id, name, args, kwargs, handler_id=handlerId)
  ┃
  ▼
view.on_event(event: Event)                ← 领域入口（用户覆写）
  ┃ ext.handlers.get(event.handler_id)     ← int 单键查找
  ┃
  ▼
handler.handle(view, event)
```

### _route_event 拆解逻辑

在 source 到达叶子节点时拆解 data：

```python
args_raw = data.get("$args", ())
args = list(args_raw) if isinstance(args_raw, list) else []
kwargs = {k: v for k, v in data.items() if k != "$args"}
event = Event(component_id, event_name, args, kwargs,
              handler_id=handler_id, viewport_id=viewport_id)
```

### _process_value 简化

移除 `event_name` 参数及相关累积逻辑。注册 handler 时直接分配递增 ID：

```python
elif isinstance(value, EventHandler):
    if component_id == "":
        raise ValueError(
            "Component has event handler but missing $id. "
            "Every component with an event handler must have a $id."
        )
    handler_id = len(state.handlers)
    state.handlers[handler_id] = value
    return value.to_wire(handler_id)
```

不再需要 `$children` scope 边界特判、路径拼接等逻辑。

### EventHandler 字段：`extract` → `kwargs`

`EventHandler` 的 keyword 参数字段从 `self.extract` 改名为 `self.kwargs`，与 `EventHandler.__init__(**kwargs)` 形参名一致：

```python
class EventHandler(mutobj.Declaration):
    args: tuple[Expr, ...]
    kwargs: dict[str, Expr]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        ...

    async def handle(self, view: View, event: Event) -> bool:
        ...

    def to_wire(self, handler_id: int) -> WireNode:
        ...
```

### 消费侧对照

| 位置 | 改动 |
|------|------|
| `event_handler_resolve_call` | `event.data.get("$args", [])` → `event.args` |
| `_eval_kwargs` | `event_data.get(k)` → `event_kwargs.get(k)`（参数名同步改为 `event.kwargs`） |
| `bind_handle` | `event.data.get("$args", [])` → `event.args[0] if event.args else None` |
| `event_handler_to_wire_impl` | `$handler` 值改为 `handler_id` 整数；args/kwargs 为顶层键（不带 `$` 前缀） |
| 用户 `on_event` 覆写 | `event.data["hash"]` → `event.kwargs["hash"]` |
| 默认 `on_event` 查找 handler | `ext.handlers.get((component_id, event_name))` → `ext.handlers.get(event.handler_id)` |
| 前端 `createHandler` | `inner.$menu` / `inner.$placement` / `!k.startsWith('$')` → `spec.menu` / `spec.placement` / `spec.kwargs` |
| 前端 `createMenuTriggerHandler` | `inner.$placement` / `!k.startsWith('$')` / `data = {$menu: true}` → `spec.placement` / `spec.kwargs` / 不再塞 `$menu` |
| `ViewPort.handle_event` | `await ext.view.handle_event(event)` → `await handle_raw_event(ext.view, event)` |

### `$args` 两层语义分离

| 层次 | 键名 | 位置 | 含义 | 方向 |
|------|------|------|------|------|
| wire 声明 | `args` | WireNode 顶层（不带 `$`） | handler 的 extract path 列表（如 `["$0.key"]`） | backend → frontend |
| 事件数据 | `$args` | wire message `data` 内部（带 `$`） | 前端 resolve 后的值列表（如 `["menu1"]`） | frontend → backend |
| Event 字段 | `args` | `Event.args: Sequence[WireValue]` | 已提取完成的运行时值 | 后端消费 |

wire 声明层用 `args`（无 `$` 前缀），事件数据层用 `$args`（有 `$` 前缀），在 `_route_event` 中拆解后转入 `Event.args`。

### 前端检测逻辑变化

| 旧代码 | 新代码 |
|--------|--------|
| `spec.$handler` 是 dict | `spec.$handler` 是 handlerId 数字 |
| `spec.$handler.$args` 取 extract path | `spec.args` 顶层数组 |
| `inner.$menu` 检测菜单 handler | `spec.menu` 顶层布尔 |
| `inner.$placement` 取 placement | `spec.placement` 顶层字符串 |
| `!k.startsWith('$')` 过滤 kwarg path | `spec.kwargs` 就是 kwarg path（不含元数据） |
| 显式 `data = {$menu: true}` | 不再需要 |

---

## 实施步骤清单

- [x] **Event 数据结构重构**
  - `Event` 新增 `args` / `kwargs` / `handler_id` 字段，移除 `data`
  - 改为 `@dataclass(slots=True)`
  - `_route_event` 拆解 wire data → `args` + `kwargs`，构造新 Event
  - 所有消费方（`event_handler_resolve_call`、`_eval_kwargs`、`bind_handle`）改用 `event.args` / `event.kwargs`

- [x] **handler_id 体系**
  - `_process_value` 注册 handler 时分配递增 id（`len(state.handlers)`）
  - `EventHandler.to_wire` 加 `handler_id` 参数，产出 `$handler: handler_id` 键
  - `_route_event` 解析 wire `handlerId` → 传入 Event
  - 默认 `on_event` 改为 `ext.handlers.get(event.handler_id)` 查找

- [x] **menu / placement 扁平化**
  - `MenuTrigger.to_wire` 将 `menu` / `placement` 写到 WireNode 顶层（不带 `$` 前缀）
  - 前端 `createHandler` / `createMenuTriggerHandler` 从 `spec.menu` / `spec.placement` 读取
  - 前端不再 `!k.startsWith('$')` 过滤，不再显式 `data = {$menu: true}`

- [x] **handle_event 移除**
  - `View` 声明删除 `handle_event`
  - `_view_impl` 新增 `handle_raw_event` 模块级函数
  - `ViewPort.handle_event` 调用 `handle_raw_event`

- [x] **_process_value 简化**
  - 移除 `event_name` 参数和相关累积逻辑
  - `$children` scope 边界处理简化

- [x] **EventHandler.extract → kwargs**
  - `EventHandler` 字段 `self.extract` 改名为 `self.kwargs`
  - `_events_impl` 中全部引用同步更新

- [x] **wire args 键去 `$` 前缀**
  - 声明层：`"args"`（不带 `$`）→ extract path 列表
  - 事件数据层：`"$args"`（带 `$`）→ 前端 resolve 后的值
  - `_route_event` 拆解时按 `$args` 键提取

- [x] **测试与文档更新**
  - 更新所有直接使用 `Event(...)` / `event.data` / `to_wire()` 的测试
  - 前端构建通过（4 个 vite bundle 干净）
  - 全量 pytest 通过
