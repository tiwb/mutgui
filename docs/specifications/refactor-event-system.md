# 事件系统重构 — Event + EventHandler

**状态**：✅ 已完成
**日期**：2026-04-17
**类型**：重构

## 需求

1. 事件 helper（notify/handler/bind）当前用 dict + `$` 标签表示，与框架其他 `$` 前缀约定风格不统一，且需要框架解释中间格式（`$obj`/`$attr`/`$fn`）
2. handler 事件后无条件 `invalidate()`，bind 改了状态应该自动刷新，但 handler 不一定需要
3. `on_event` 当前是 fallback（只在无注册 handler 时调用），缺乏统一的事件入口和拦截能力

### 前置依赖

- `feature-framework-core.md` — 基础框架设计（事件模型、`$` 标签约定）
- `feature-view-nesting.md` — View 嵌套（事件路由、`$view` 协议）

## 关键参考

### 现有实现

- `mutgui/src/mutgui/events.py` — 当前 notify/handler/bind helper 函数，`TAG_KEY = "$"`
- `mutgui/src/mutgui/view.py` — View Declaration，`render() -> list[Any] | dict[str, Any]`，`on_event(dict) -> None`
- `mutgui/src/mutgui/_view_impl.py` — 树序列化（`_process_tagged`/`_process_node`/`_process_items`）、事件路由（`_route_event`）、`_callbacks` 存储裸 callable
- `mutgui/frontend/src/renderer.tsx` — 前端 `processProps`（`'$' in val` 检测）、`createHandler`（extract + send）
- `mutgui/frontend/src/resolve-path.ts` — `resolvePath` 路径提取

### 现有协议（将被替换）

```jsonc
// 后端 → 前端 wire 格式
{"$": "handler", "extract": {"value": "$0.target.value"}}
// bind 特殊处理
{"$": "handler", "extract": {"__bind_value__": "$0.target.value"}}

// 前端 → 后端 WebSocket 消息
{"source": ["viewId", "componentId"], "event": "onChange", "data": {"value": "hello"}}

// 后端 Python-side 中间格式
{"$": "handler", "fn": <callable>, "extract": {...}}   // handler
{"$": "bind", "obj": <obj>, "attr": "name", "path": "$0.target.value"}  // bind
```

### 主流 GUI 框架对比

设计参考了 Qt、DOM、Windows、WPF 等框架的事件系统：

| 设计决策 | 主流共识 | mutgui 选择 |
|----------|----------|-------------|
| Event 是否带目标 | 6/7 框架带（Qt 例外） | 带 component_id（View 管多个虚拟 component） |
| Event 是否含处理逻辑 | 所有框架 Event 纯数据 | Event 纯数据，处理逻辑在 EventHandler |
| 分派在哪里 | 在 View/Widget 侧 | View.on_event() 默认实现中分派 |
| 观察/拦截机制 | 所有框架都支持 | install_event_filter() |
| 消费模型 | return bool / accept-ignore | return bool |

## 设计方案

### 核心设计：Event 与 EventHandler 分离

两个正交概念：

- **Event** — 纯数据，描述"发生了什么"（等同 Qt 的 QEvent、DOM 的 Event）
- **EventHandler** — 策略对象，定义"怎么处理"（等同 Qt 的虚方法、DOM 的 listener）。基类可直接使用（只提取，不消费），子类 Callback/Bind 添加消费行为

分派逻辑在 View 侧（`on_event` 默认实现），不在 Event 侧。

### Event — 纯数据事件对象

```python
class Event:
    """运行时事件 — 纯数据，不含处理逻辑。"""
    __slots__ = ("component_id", "name", "data")

    def __init__(self, component_id: str, name: str, data: dict):
        self.component_id = component_id  # 哪个组件发的
        self.name = name                  # 什么事件 ("onClick", "onChange")
        self.data = data                  # 提取的数据
```

Event 包含 `component_id` 的原因：mutgui 的 View 管理多个虚拟 component（不像 Qt 每个 widget 是独立 QObject），观察者（event filter、parent View）需要从 Event 本身判断来源。

### EventHandler — 事件处理策略（基类，可直接使用）

EventHandler 既是基类，也是最小功能的具体类：只提取数据，不消费事件，数据留给 `on_event` 处理。

```python
class EventHandler:
    """事件处理策略 — 声明在 render 中，定义提取和处理方式。

    直接使用时：只提取数据，不消费（等同旧 Notify）。
    子类 Callback/Bind 覆盖 handle() 添加消费行为。
    """

    def __init__(self, **extract: str):
        self.extract = extract  # keyword extract paths

    async def handle(self, view: View, event: Event) -> bool:
        """处理事件。返回 True 表示已消费。基类不消费。"""
        return False

    def to_wire(self) -> dict:
        """序列化为前端 wire 格式。"""
        return {"$handler": dict(self.extract)}
```

直接使用 EventHandler 的场景：需要前端提取数据但不自动处理，由 `on_event` 自定义处理。

### 两个具体策略

#### Callback — 回调策略

```python
class Callback(EventHandler):
    """提取数据 → callback(*args, **kwargs)。不自动 invalidate。"""

    def __init__(self, callback: Callable, /, *args: str, **extract: str):
        self.callback = callback
        self.args = args        # positional extract paths
        self.extract = extract  # keyword extract paths

    async def handle(self, view: View, event: Event) -> bool:
        args = event.data.get("$args", [])
        kwargs = {k: v for k, v in event.data.items() if k != "$args"}
        result = self.callback(*args, **kwargs)
        if inspect.isawaitable(result):
            await result
        return True

    def to_wire(self) -> dict:
        wire = dict(self.extract)
        if self.args:
            wire["$args"] = list(self.args)
        return {"$handler": wire}
```

#### Callback 参数与 callback 参数的对称性

Callback 的构造参数直接映射为 callback 的调用参数：

```python
# positional — callback 按位置接收
Callback(self.on_change, "$0.target.value")
# → self.on_change("typed text")

# keyword — callback 按名称接收
Callback(self.on_viewport, start="$0.start", end="$0.end")
# → self.on_viewport(start=1, end=10)

# 混合
Callback(self.on_drag, "$0.clientX", "$0.clientY", shift="$0.shiftKey")
# → self.on_drag(100, 200, shift=True)

# 无参数
Callback(self.save)
# → self.save()
```

对称关系：`Callback(fn, *args, **kwargs)` 构造 → `fn(*extracted_args, **extracted_kwargs)` 调用。

#### Bind — 绑定策略

```python
class Bind(EventHandler):
    """提取数据 → setattr(obj, attr, value)。自动 invalidate。"""

    def __init__(self, obj: Any, attr: str, path: str = "$0"):
        self.obj = obj
        self.attr = attr
        self.path = path

    async def handle(self, view: View, event: Event) -> bool:
        args = event.data.get("$args", [])
        setattr(self.obj, self.attr, args[0] if args else None)
        view.invalidate()
        return True

    def to_wire(self) -> dict:
        return {"$handler": {"$args": [self.path]}}
```

### 用法

```python
from mutgui import EventHandler, Callback, Bind

def render(self) -> Block:
    return Block([
        # Bind — 声明式绑定
        {"$component": "Input", "$id": "name", "value": self.name,
         "onChange": Bind(self, "name", "$0.target.value")},

        # Callback — 回调函数
        {"$component": "Button", "$id": "submit",
         "onClick": Callback(self.save)},

        {"$component": "Slider", "$id": "zoom",
         "onChange": Callback(self.on_zoom, "$0")},

        # EventHandler — 提取数据，on_event 处理
        {"$component": "Viewport", "$id": "viewport",
         "onViewport": EventHandler(start="$0.start", end="$0.end")},
    ])
```

### View.on_event — 统一事件入口

等同 Qt 的 `QWidget::event()`。所有事件经过此入口，默认实现查找注册的 EventHandler 并分派。

```python
class View(mutobj.Declaration):
    async def on_event(self, event: Event) -> bool:
        """统一事件入口。

        默认实现：查找 render 中注册的 EventHandler，调用 handle()。
        子类重写可拦截、预处理、后处理，再 super() 走默认分派。
        """
        ...
```

默认实现（在 _view_impl.py 中）：

```python
@impl(View.on_event)
async def _default_on_event(self: View, event: Event) -> bool:
    ext = _render_ext(self)
    handler = ext._handlers.get((event.component_id, event.name))
    if handler is not None:
        return await handler.handle(self, event)
    return False
```

#### 子类重写模式

```python
class MyView(View):
    async def on_event(self, event: Event) -> bool:
        # 拦截：在默认分派之前
        if event.component_id == "canvas" and event.name == "onMouseDown":
            self.start_drawing(event.data)
            return True

        # 默认分派：Callback→消费, Bind→消费, EventHandler→不消费
        handled = await super().on_event(event)
        if handled:
            return True

        # 处理 EventHandler 传下来的和未注册的事件
        if event.name == "onViewport":
            self.viewport = (event.data["start"], event.data["end"])
            self.invalidate()
            return True

        return False  # 未处理
```

### invalidate 策略

| 类型 | 事件后行为 |
|------|-----------|
| **Bind** | 自动 `setattr` + 自动 `view.invalidate()` |
| **Callback** | 调用 callback，**不** invalidate。需要时手动调 `self.invalidate()` |
| **EventHandler** | 不消费，落到 `on_event`，开发者按需 invalidate |

现有实现所有事件后无条件 invalidate。新设计只有 Bind 自动 invalidate（Bind 是声明式状态绑定，改了属性就该刷新；Callback/EventHandler 是命令式，callback 可能只是记日志、发请求，不一定改状态）。

### EventFilter — 事件观察/拦截

类似 Qt 的 `installEventFilter`、DOM 的 capture phase、WPF 的 Preview 隧道事件。

```python
class EventFilter:
    """事件观察/拦截器。"""
    async def on_event_filter(self, watched: View, event: Event) -> bool:
        """返回 True 吞掉事件，target 的 on_event 不会被调用。"""
        return False
```

```python
class View:
    def install_event_filter(self, filter: EventFilter) -> None:
        """注册 filter。filter 在 on_event 之前看到事件。"""
        ...
```

用法示例：

```python
class LoggingFilter(EventFilter):
    """记录所有事件。"""
    async def on_event_filter(self, watched, event):
        log(f"{watched.id}.{event.component_id}:{event.name}")
        return False  # 只观察，不吞

class ShortcutFilter(EventFilter):
    """全局快捷键拦截。"""
    async def on_event_filter(self, watched, event):
        if event.name == "onKeyDown" and event.data.get("key") == "Escape":
            self.app.close_modal()
            return True  # 吞掉
        return False
```

### 完整事件链

```
前端事件到达
    ↓
框架路由到目标 View（按 source 路径递归）
    ↓
Filter 链（观察/拦截）
    ↓ (未吞掉)
view.on_event(event)（统一入口）
    ↓ (默认实现)
查找 _handlers → handler.handle(view, event)
    ↓ (未消费)
冒泡到 parent View（未来，不在本次范围）
```

### 框架处理 — 树序列化

`_process_node` 检测 EventHandler 对象，存储到 `_handlers`，生成 wire 格式：

```python
def _process_node(view: View, node: dict[str, Any]) -> dict[str, Any]:
    ext = _render_ext(view)
    result: dict[str, Any] = {}
    node_id = node.get("$id", "")
    for key, val in node.items():
        if key == "$children" and isinstance(val, list):
            result[key] = _process_items(view, val)
        elif isinstance(val, EventHandler):
            ext._handlers[(node_id, key)] = val
            result[key] = val.to_wire()
        else:
            result[key] = val
    return result
```

### 框架处理 — 事件路由

```python
async def _route_event(
    view: View, source: list[str], event_name: str,
    data: dict[str, Any], original_event: dict[str, Any],
) -> None:
    ext = _render_ext(view)
    if len(source) > 1:
        child_id = source[0]
        child_view = ext._children.get(child_id)
        if child_view is not None:
            await _route_event(child_view, source[1:], event_name, data, original_event)
    elif len(source) == 1:
        component_id = source[0]
        event = Event(component_id, event_name, data)

        # Filter 链
        for f in ext._event_filters:
            if await f.on_event_filter(view, event):
                return

        # 统一入口
        await view.on_event(event)
    else:
        event = Event("", event_name, data)
        await view.on_event(event)
```

### Wire 格式

后端 → 前端统一使用 `$handler` 标记。前端不区分 EventHandler 类型：

```jsonc
// Callback(self.save) — 无 extract
{"$handler": {}}

// Callback(self.on_change, "$0.target.value") — positional
{"$handler": {"$args": ["$0.target.value"]}}

// Callback(self.on_viewport, start="$0.start", end="$0.end") — keyword
{"$handler": {"start": "$0.start", "end": "$0.end"}}

// Callback(self.on_drag, "$0.x", "$0.y", shift="$0.shiftKey") — 混合
{"$handler": {"$args": ["$0.x", "$0.y"], "shift": "$0.shiftKey"}}

// Bind(self, "name", "$0.target.value")
{"$handler": {"$args": ["$0.target.value"]}}

// EventHandler(start="$0.start", end="$0.end")
{"$handler": {"start": "$0.start", "end": "$0.end"}}
```

命名 `$handler` 而非 `$event` 的原因：wire 告诉前端"创建一个 handler 函数"，前端的 `createHandler` 创建实际的提取+转发函数。"handler" 在整个链路中含义一致（怎么处理事件），"event" 只在后端表示运行时数据，不污染到 wire 层。

### 前端变更

检测逻辑从 `'$' in val` 改为 `'$handler' in val`：

```typescript
// processProps — 检测
} else if (
  val != null && typeof val === 'object' &&
  !Array.isArray(val) && '$handler' in (val as Record<string, unknown>)
) {
  props[key] = createHandler(val as Record<string, unknown>, scope, nodeId, key, conn);
}

// createHandler — 提取 $args + 其余 kwargs
function createHandler(spec, scope, componentId, eventName, conn) {
  const inner = spec.$handler as Record<string, unknown>;
  const argPaths = (inner.$args || []) as string[];
  const kwargPaths: Record<string, string> = {};
  for (const [k, v] of Object.entries(inner)) {
    if (k !== '$args') kwargPaths[k] = v as string;
  }
  const source = [...scope, componentId];
  return (...args: unknown[]) => {
    const extractedArgs = argPaths.map(p => resolvePath(args, p));
    const extractedKwargs: Record<string, unknown> = {};
    for (const [k, path] of Object.entries(kwargPaths)) {
      extractedKwargs[k] = resolvePath(args, path);
    }
    const data: Record<string, unknown> = { ...extractedKwargs };
    if (extractedArgs.length > 0) {
      data.$args = extractedArgs;
    }
    conn.send(JSON.stringify({ source, event: eventName, data }));
  };
}
```

前端 → 后端的 WebSocket 消息格式不变：`{source, event, data}`。

### 消除的概念

本次重构后以下概念不再存在：

| 消除 | 替代 |
|------|------|
| `TAG_KEY = "$"` 常量 | `isinstance(val, EventHandler)` 类型检测 |
| `{"$": "handler", "extract": {...}}` dict 中间格式 | `EventHandler` 类 + `to_wire()` |
| `_process_tagged()` 函数 | `isinstance` 检测 + `val.to_wire()` |
| `handler()`/`bind()`/`notify()` 小写 helper 函数 | `Callback`/`Bind`/`EventHandler` 构造函数 |
| `$fn`/`$obj`/`$attr` Python-side 元数据键 | EventHandler 对象属性 |
| `__bind_value__` 魔法键 | `$args` 统一机制 |
| `callback(data_dict)` 传 dict | `callback(*args, **kwargs)` 原生参数 |
| 事件后无条件 `invalidate()` | 仅 Bind 自动 invalidate |
| `_callbacks: dict` (裸 callable) | `_handlers: dict` (EventHandler 对象) |
| `on_event` 作为 fallback | `on_event` 作为统一入口（默认分派到 handler） |
| `Notify` 独立类 | 合并到 `EventHandler` 基类（直接使用） |

### View 处理不变

View 实例在渲染树中的处理保持 `isinstance(item, View)` 硬判断，与 EventHandler 模式一致：

```python
# _process_items — 不变
if isinstance(item, View):
    ext._children[item.id] = item
    result.append({"$view": item.id})
```

## 实施步骤清单

- [x] 重写 `events.py` — 删除 `TAG_KEY`/`notify`/`handler`/`bind`，实现 `Event`、`EventHandler`、`Callback`、`Bind`、`EventFilter` 五个类
- [x] 更新 `view.py` — `on_event` 签名改为 `async def on_event(self, event: Event) -> bool`，新增 `install_event_filter` 声明
- [x] 更新 `_view_impl.py` — `ViewRenderState._callbacks` → `_handlers`，新增 `_event_filters`；删除 `_process_tagged`/`_make_bind_callback`；`_process_node` 改用 `isinstance(val, EventHandler)`；`_route_event` 构造 `Event` + filter 链 + 调用 `on_event`；默认 `on_event` 实现查找 handler 并分派；移除事件后无条件 `invalidate()`
- [x] 更新 `virtual_list.py` — `handler()` → `Callback()`，`_on_viewport` 签名从 `(data: dict)` 改为 `(*, start, end)`，显式调用 `self.invalidate()`
- [x] 更新 `__init__.py` — 导出 `Event`/`EventHandler`/`Callback`/`Bind`/`EventFilter`，移除旧 `notify`/`handler`/`bind`
- [x] 更新前端 `renderer.tsx` — `processProps` 检测从 `'$' in val` 改为 `'$handler' in val`；`createHandler` 支持 `$args` + kwargs；IME `onCompositionEnd` 适配新 wire 格式
- [x] 重写 `test_events.py` — 测试新的 Event/EventHandler/Callback/Bind/EventFilter 类
- [x] 更新 `test_session.py` — 使用新 API（`Callback`/`Bind`/`EventHandler`），断言新 wire 格式（`$handler`），事件 data 使用 `$args` 格式
- [x] 更新 `test_nesting.py` — `handler()` → `Callback()`，`on_change` 签名从 `(data: dict)` 改为关键字参数
- [x] 更新 `test_virtual_list.py` — `_on_viewport(dict)` 改为关键字参数调用
- [x] 运行测试，确认全部通过（48 passed）
