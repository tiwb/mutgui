# VirtualList 多 ViewPort 支持设计规范

**状态**：✅ 已完成
**日期**：2026-04-18
**类型**：功能设计

## 需求

1. 多个 ViewPort（客户端）可以独立滚动同一个 VirtualList，各自看到不同范围的 items
2. 后端维护所有 ViewPort 可见 items 的并集（为未来基于可见 items 的功能打基础）
3. 每个 ViewPort 只收到自己 viewport 范围内的 items（不发送无关数据）

### 前置依赖

- `feature-virtual-list.md` — VirtualList 基础实现（已完成）
- `feature-session-sharing.md` — ViewPort + Channel 多客户端架构（已完成）

## 关键参考

### 后端

- `src/mutgui/virtual_list.py` — VirtualList + Adapter，per-VP viewport dict + union 渲染，Adapter 通过 `_virtual_lists` 关联多个 VirtualList
- `src/mutgui/_view_impl.py:161-183` — `_deferred_render`：render → 遍历 ViewObservers → `vp._push_render()`
- `src/mutgui/_viewport_impl.py:69-73` — `_viewport_handle_event`：直接委托 `view.handle_event(event)`，未注入 VP 身份
- `src/mutgui/_viewport_impl.py:96-132` — `_vp_push_render`：发送 wire_tree + 协调子 ViewPort
- `src/mutgui/events.py:16-24` — `Event` 类，`__slots__ = ("component_id", "name", "data")`，无 VP 身份
- `src/mutgui/events.py:45-59` — `Callback.handle`：从 `event.data` 提取 args/kwargs 调回调

### 前端

- `frontend/src/virtual-list.tsx` — `viewportStart` 是本地状态，基于 scrollTop 计算偏移

## 问题分析

`VirtualList._viewport` 是单一 `tuple[int, int]`，多客户端的 `onViewport` 事件写同一字段（last writer wins）。`render()` 基于此共享 viewport 生成一份 `$children`，推送给所有 ViewPort。最后一个发送 viewport 事件的客户端决定所有客户端看到的内容。

## 设计方案

四步改动链：**事件透传 VP 身份 → per-VP viewport 存储 → union 渲染 → push 时裁剪**

### VP 身份标识

用 `channel.channel_id` 作为 viewport 身份标识。Channel Declaration 声明 `channel_id: int` 公开属性，impl 中构造时分配自增 ID。同一连接的所有 ViewPort（root VP 及其 child VPs）共享同一个 Channel 对象，因此 `channel_id` 天然代表"一个客户端连接"。

```python
# channel.py — Declaration
class Channel(mutobj.Declaration):
    channel_id: int  # 唯一标识，由 impl 自动分配
    ...

# _channel_impl.py（或现有 impl 文件）— 实现
_next_channel_id = 1

@impl
def _channel_init(self: Channel, ...) -> None:
    global _next_channel_id
    self.channel_id = _next_channel_id
    _next_channel_id += 1
    ...
```

### 1. 事件路由透传 ViewPort 身份

ViewPort 在转发事件前注入 `_viewport_id`：

```python
# _viewport_impl.py — _viewport_handle_event
async def _viewport_handle_event(self: ViewPort, event: dict) -> None:
    event["_viewport_id"] = ext._channel.channel_id
    await ext._view.handle_event(event)
```

`_view_handle_event` 提取并透传到 `_route_event`，写入 Event 对象：

```python
# _view_impl.py — _view_handle_event
viewport_id = event.get("_viewport_id")
await _route_event(self, source, event["event"], event.get("data", {}),
                   viewport_id=viewport_id)
```

Event 类增加 `viewport_id` slot：

```python
# events.py
class Event:
    __slots__ = ("component_id", "name", "data", "viewport_id")

    def __init__(self, component_id, name, data, *, viewport_id=None):
        ...
        self.viewport_id = viewport_id
```

### 2. Callback `@` 前缀后端注入

Callback 支持 `@` 前缀的 extract 参数，表示后端注入（不发送到前端）。`handle` 时通过 getattr 链从后端对象解析值：

```python
# events.py — Callback
class Callback(EventHandler):
    def __init__(self, callback, /, *args, **extract):
        self.callback = callback
        self.args = args
        self.extract = extract

    async def handle(self, view, event):
        args = event.data.get("$args", [])
        kwargs = {k: v for k, v in event.data.items() if k != "$args"}
        # @-prefix: 后端注入（@event.xxx / @view）
        inject_sources = {"event": event, "view": view}
        for k, v in self.extract.items():
            if isinstance(v, str) and v.startswith("@"):
                parts = v[1:].split(".")
                obj = inject_sources.get(parts[0])
                for attr in parts[1:]:
                    obj = getattr(obj, attr, None)
                kwargs[k] = obj
        result = self.callback(*args, **kwargs)
        ...

    def to_wire(self):
        # @-prefix 参数不发送到前端
        wire = {k: v for k, v in self.extract.items()
                if not (isinstance(v, str) and v.startswith("@"))}
        ...
```

VirtualList 中的用法：

```python
"onViewport": Callback(
    self._on_viewport, start="$0.start", end="$0.end",
    viewport_id="@event.viewport_id",
),

def _on_viewport(self, *, start: int, end: int, viewport_id: int) -> None:
    self._viewports[viewport_id] = (start, end)
    self.invalidate()
```

### 3. VirtualList per-VP viewport 存储 + union 渲染

```python
# virtual_list.py
class VirtualList(View):
    def __init__(self, id, adapter):
        ...
        self._viewports: dict[int, tuple[int, int]] = {}  # channel_id → (start, end)

    def _on_viewport(self, *, start: int, end: int, viewport_id: int) -> None:
        self._viewports[viewport_id] = (start, end)
        self.invalidate()

    def _refresh_visible(self) -> None:
        # 清理已断开 VP 的条目
        active_ids = {_ext(vp)._channel.channel_id
                      for vp in ViewObservers.get(self)._viewports}
        self._viewports = {k: v for k, v in self._viewports.items()
                           if k in active_ids}

        if not self._viewports:
            self._visible_ids = []
            return

        # 计算并集
        union_start = min(s for s, e in self._viewports.values())
        union_end = max(e for s, e in self._viewports.values())

        count = self.adapter.item_count
        union_start = min(union_start, count)
        union_end = min(union_end, count)

        # 后续逻辑同现有（按并集范围创建/清理 item Views）
        new_ids = [self.adapter.item_id(i) for i in range(union_start, union_end)]
        ...
```

同时维护 per-VP 的 ID 列表，供推送裁剪使用：

```python
        # 在 _refresh_visible 末尾，预计算 per-VP 的 item ID 集合
        self._viewport_item_ids: dict[int, set[str]] = {}
        for vp_id, (s, e) in self._viewports.items():
            s, e = min(s, count), min(e, count)
            self._viewport_item_ids[vp_id] = {
                self.adapter.item_id(i) for i in range(s, e)
            }
```

### 4. Per-VP 推送裁剪（ViewChildFilter Extension）

用 mutobj Extension 模式实现 per-VP 过滤——与 ViewObservers、ViewRenderState 同一模式。过滤数据和 VirtualList 内部逻辑分离：Extension 只管"哪个 VP 该收哪些 children"，`_vp_push_render` 做标准 Extension 查找。

**ViewChildFilter Extension**（新增，放 `_view_impl.py` 或独立文件）：

```python
class ViewChildFilter(mutobj.Extension[View]):
    """Per-VP child 过滤。只有需要的 View 才创建此 Extension。"""
    _viewport_item_ids: dict[int, set[str]] = {}  # channel_id → allowed child IDs

    def get_children(self, channel_id: int) -> set[str] | None:
        """返回该 VP 应收到的 child ID 集合。None = 不过滤。"""
        if not self._viewport_item_ids:
            return None
        return self._viewport_item_ids.get(channel_id, set())
```

**VirtualList 侧**（在 `_refresh_visible` 末尾填充 Extension）：

```python
filt = ViewChildFilter.get_or_create(self)
filt._viewport_item_ids = {
    vp_id: {self.adapter.item_id(i) for i in range(s, e)}
    for vp_id, (s, e) in self._viewports.items()
}
```

**`_vp_push_render` 侧**（`_viewport_impl.py`）：

```python
async def _vp_push_render(vp: ViewPort) -> None:
    view = ext._view
    render_state = _render_ext(view)

    # Extension 查找 — 无 Extension 则不过滤
    filt = ViewChildFilter.get(view)
    allowed = filt.get_children(ext._channel.channel_id) if filt is not None else None

    # 发送 wire_tree（可能过滤 $children）
    wire_tree = render_state._wire_tree
    if allowed is not None:
        wire_tree = _filter_children_in_tree(wire_tree, allowed)
    await ext._channel.send({...})

    # 协调子 ViewPort（同样过滤）
    children = render_state._children
    if allowed is not None:
        children = {k: v for k, v in children.items() if k in allowed}

    # ... 后续 child VP 协调逻辑不变
```

**`_filter_children_in_tree`**：纯函数，浅拷贝 wire_tree 节点，过滤 `$children` 数组中的 `$view` 引用：

```python
def _filter_children_in_tree(tree: list[dict], allowed: set[str]) -> list[dict]:
    """浅拷贝 tree，只保留 $children 中 ID 在 allowed 集合内的 $view 节点。"""
    result = []
    for node in tree:
        if "$children" in node:
            filtered = [c for c in node["$children"]
                        if not isinstance(c, dict) or c.get("$view") in allowed]
            node = {**node, "$children": filtered}
        result.append(node)
    return result
```

### 5. Sync Scroll（同步滚动）

独立滚动是默认行为。Sync scroll 作为可选模式，让所有客户端的滚动位置保持一致。

**核心思路**：sync scroll 是普通的状态同步，跟 input value 同步一个道理。后端存 scroll position，推给所有 VP，前端被动跟随。Union 机制全程在线——sync 模式下所有 VP 恰好报告同样的 viewport，union 自然退化为单一范围。

#### 后端

VirtualList 增加 `sync_scroll` 参数（默认 `False`）。该参数可动态修改，但当前框架无 per-client 状态机制，修改后所有客户端同步变化。未来有 per-client 状态支持后，可实现每个客户端独立切换。

```python
class VirtualList(View):
    def __init__(self, id, adapter, *, sync_scroll=False):
        ...
        self.sync_scroll = sync_scroll
        self._scroll_top: float = 0  # 同步滚动位置（仅 sync_scroll=True 时有意义）
```

当 sync scroll 开启时，客户端 A 滚动 → 发 `onScroll` 事件 → 后端存 `_scroll_top` → invalidate → 推给所有 VP。其他前端收到新的 `scrollTop` prop → programmatically 滚动到该位置。

```python
def render(self) -> ViewBlock:
    ...
    props = {
        "$component": "VirtualList",
        "$id": "list",
        "itemCount": self.adapter.item_count,
        "onViewport": Callback(self._on_viewport, ...),
        "$children": visible_items,
    }
    if self.sync_scroll:
        props["scrollTop"] = self._scroll_top
        props["onScroll"] = Callback(self._on_scroll, scrollTop="$0.scrollTop")
    return ViewBlock([props])

def _on_scroll(self, *, scrollTop: float) -> None:
    self._scroll_top = scrollTop
    self.invalidate()
```

#### 前端

VirtualList 组件增加两个可选 props（仅 sync scroll 模式下由后端传入）：

| prop | 类型 | 说明 |
|------|------|------|
| `scrollTop` | `number` | 后端同步的滚动位置 |
| `onScroll` | `handler` | 回报滚动位置给后端 |

行为：

```
收到 scrollTop prop 时（sync 模式）：
  本客户端滚动 → 正常发 onViewport + 发 onScroll(scrollTop)
  收到新 scrollTop prop → programmatically el.scrollTop = scrollTop
                        → skip 一次 onScroll 回发（避免循环）
                        → 触发的 onViewport 正常发送

未收到 scrollTop prop 时（独立模式）：
  完全不关心 scrollTop/onScroll，行为同独立滚动
```

防循环：用 ref 标记 "这次 scroll 是 programmatic 的"，跳过 onScroll 回发。onViewport 不跳过——前端 scroll 后需要告诉后端自己的 viewport。

#### Demo

当前框架无 per-client 状态，无法让单个客户端独立切换 sync scroll。Demo 用同一个 adapter 创建两个 VirtualList 实例，以不同默认值并排展示两种模式：

```python
class RootView(View):
    def __init__(self):
        self.adapter = RecordAdapter(...)
        self.list_independent = VirtualList("list-ind", self.adapter)
        self.list_synced = VirtualList("list-sync", self.adapter, sync_scroll=True)

    def render(self):
        return ViewBlock([
            {"$component": "Card", "$id": "ind", "title": "独立滚动",
             "$children": [self.list_independent]},
            {"$component": "Card", "$id": "sync", "title": "同步滚动",
             "$children": [self.list_synced]},
        ])
```

两个客户端打开同一页面：
- 左侧列表（独立滚动）：各自自由滚动，互不影响
- 右侧列表（同步滚动）：一个客户端滚动，另一个跟随

#### 与 per-VP 机制的关系

Sync scroll **不影响后端的 per-VP 逻辑**。每个 VP 依然独立发 `onViewport`，后端依然 per-VP 存储 viewport、计算 union、per-VP 裁剪推送。只不过 sync 模式下所有 VP 报告同一个 scroll 位置，viewport 收敛，union 等于单一范围——自然退化，零特殊路径。

### 前端改动汇总

| 改动点 | 原因 |
|--------|------|
| 无（per-VP 独立滚动） | 每个 VP 收到自己 viewport 范围的 items，前端 `viewportStart` 本地定位，行为不变 |
| `scrollTop` + `onScroll` 支持 | sync scroll 模式下被动跟随 + 回报（通过有无 `scrollTop` prop 判断模式） |
| programmatic scroll 防循环 | 避免收到 scrollTop → scroll → onScroll → 循环 |

### 正确性论证

| 场景 | 行为 |
|------|------|
| VP-A [0, 20], VP-B [100, 120] | union [0, 120]，40 个 item View 存活。VP-A 收到 0-19，VP-B 收到 100-119 |
| VP-A 和 VP-B 重叠 [90, 110] 和 [100, 120] | union [90, 120]，30 个 item View。共享的 100-109 对应相同 View 实例 |
| 新 VP 连接，未发 viewport | `_viewports` 无该 VP 条目 → `_children_for_viewport` 返回空集 → VP 收到 itemCount 但无 children → 前端计算 viewport → 发 onViewport → 正常流程 |
| VP 断开 | `detach()` 级联清理子 VP。下次 `_refresh_visible` 检测到 `active_ids` 变化，移除条目，可能缩小 union |
| item View 独立更新（值变化） | item View 的 observers 是各 VP 的子 VP。只有持有该 item 子 VP 的 VP 收到更新 |
| sync scroll：VP-A 滚动 | VP-A 发 onScroll → 后端存 scrollTop + invalidate → 所有 VP 收到新 scrollTop → 其他前端跟随滚动 → 各自发 onViewport → viewport 收敛 → union = 单一范围 |
| sync scroll 切换 | 开→关：前端停止响应 scrollTop prop，各 VP 保持各自位置独立滚动。关→开：前端以后端当前 scrollTop 为准同步 |

## 已决策问题

### Q1: per-VP 过滤的 hook 机制

**决策**：用 mutobj Extension（`ViewChildFilter(Extension[View])`）。与 ViewObservers、ViewRenderState 同一模式，`_vp_push_render` 做标准 Extension 查找。过滤数据和 VirtualList 逻辑分离，类型明确，未来其他组件需要 per-VP 过滤时填同一个 Extension 即可。

## 实施步骤清单

### 基础设施 — Channel ID + 事件透传

- [x] `channel.py`：Channel Declaration 增加 `channel_id: int` 属性声明 + `__init__` 桩方法
- [x] 新建 `_channel_impl.py`：`@impl(Channel.__init__)` 自增 ID 分配（从 1 开始），`__init__.py` 注册 side-effect import
- [x] `events.py`：Event 增加 `viewport_id` slot，构造函数增加 `viewport_id=None` 参数
- [x] `events.py`：Callback 构造时检测 `_wants_event`，handle 中按需传 `_event` 给回调
- [x] `_viewport_impl.py`：`_viewport_handle_event` 注入 `event["_viewport_id"] = ext._channel.channel_id`
- [x] `_view_impl.py`：`_view_handle_event` 提取 `_viewport_id`，`_route_event` 透传到 Event 对象

### 核心 — Per-VP viewport + union 渲染 + 推送裁剪

- [x] `_view_impl.py`：新增 `ViewChildFilter(Extension[View])` 类，提供 `get_children(channel_id)` 方法
- [x] `_viewport_impl.py`：`_vp_push_render` 增加 ViewChildFilter 查找 + wire_tree 过滤 + children 协调过滤
- [x] `_viewport_impl.py`：新增 `_filter_children_in_tree` 纯函数
- [x] `virtual_list.py`：`_viewport` 改为 `_viewports: dict[int, tuple[int, int]]`，`_on_viewport` 接收 `_event` 按 channel_id 存储
- [x] `virtual_list.py`：`_refresh_visible` 改为 union 逻辑（清理断开 VP、计算并集、预计算 per-VP ID 集合、填充 ViewChildFilter Extension）

### Sync Scroll

- [x] `virtual_list.py`：增加 `sync_scroll` 参数 + `_scroll_top` 状态 + `_on_scroll` 回调，render 中条件输出 `scrollTop`/`onScroll` props
- [x] `frontend/src/virtual-list.tsx`：支持 `scrollTop` + `onScroll` props，programmatic scroll + 防循环逻辑

### 前端构建

- [x] `npm run build`（重新构建 standalone bundle）

### 测试

- [x] 更新 `tests/test_virtual_list.py`：per-VP viewport 存储、union 范围计算、VP 断开清理
- [x] 新增测试：ViewChildFilter Extension 过滤逻辑
- [x] 新增测试：sync scroll 的 scrollTop 状态同步

### Demo

- [x] 更新 `demo/app.py`：同一 adapter 挂两个 VirtualList（独立滚动 + 同步滚动），并排展示

### Bug 修复

- [x] `virtual_list.py`：`VirtualListItemAdapter._virtual_list` 改为 `_virtual_lists: list[VirtualList]`，`invalidate()` 遍历通知所有关联 VirtualList（同一 adapter 挂多个 list 时后创建的覆盖前一个，导致只有最后一个收到 invalidate）
- [x] `demo/app.py`：`RecordItemView` 存 positional index → 改为存 stable uid，避免删除后 index 错位导致删错 item
- [x] `demo/app.py`：`on_delete` 重复调用 `delete_record` + 引用未定义变量 `index`，清理为单次调用
- [x] `events.py`：Callback 后端注入机制从 `inspect.signature` 检测 `_wants_event` 改为 `@` 前缀语法（如 `viewport_id="@event.viewport_id"`），更通用且无 inspect 开销
- [x] `channel.py` + `_channel_impl.py`：Channel ID 分配从 `__init_subclass__` hack 改为正确的 `@impl(Channel.__init__)` + `super().__init__()` 模式
- [x] Declaration 文件底部 import：impl 导入从 `__init__.py` 移到各 Declaration 文件底部（`channel.py`、`view.py`、`viewport.py`），确保 Declaration 加载时 impl 必然注册

