# 统一 Callback / MenuTrigger 渲染期参数绑定 — 消除 Action 渲染 lambda

**状态**：✅ 已完成
**日期**：2026-05-15
**类型**：重构

## 需求

1. 消除 `action.py` / `dock_panel.py` 渲染逻辑中 8 处 lambda 适配代码
2. 消除对应的 ~32 个 pyright 类型检查错误（`reportUnknownLambdaType` 连锁反应）
3. 不引入领域专用 EventHandler 子类（如 `ActionCallback`），保持 events 体系通用性

## 关键参考

- `src/mutgui/events.py` — `EventHandler` (L177)、`Callback` (L236)、`Bind`、`_eval_kwargs`、`_coerce_expr`
- `src/mutgui/menu.py` — `MenuTrigger` (L51)
- `src/mutgui/_menu_impl.py` — `@impl(MenuTrigger.handle)` (L48-72)，包含 `install_event_filter(_close_filter)` 关键步骤
- `src/mutgui/action.py` — `Action` (L175)、`ActionContext` (L97)、`ActionMenu` (L458)、`ActionToolbar._render_action` (L700+)
- `src/mutgui/dock_panel.py` — Action 渲染 lambda (L370-395)

## 设计方案

### 问题分析

当前渲染期 lambda 的本质：

```python
# action.py / dock_panel.py
lambda action=item.action, ctx=context: action.execute(ctx)
lambda action=item.action, ctx=context: ActionMenu(owner=..., source_action=action, context=ctx)
```

是 **closure 把渲染期值绑死**，事件触发时无参调用。pyright 对 lambda 默认参数的类型推断失败，导致 `Callback` / `MenuTrigger` 的 callable 类型变成 unknown，连锁污染下游。

`Callback` 已经原生支持这件事——非 `Expr` 的 positional / keyword 自动归为 `direct`，dispatch 时原样 forward：

```python
Callback(item.action.execute, context)   # bound method + direct positional
```

`MenuTrigger` 缺一个 positional 通道（只有 `**context` kwargs，且 kwargs 名字 "context" 还容易跟业务字段撞名）。补齐后两者完全对称。

### 核心改动：MenuTrigger 对齐 Callback

**`src/mutgui/menu.py`**

```python
class MenuTrigger(EventHandler):
    def __init__(
        self,
        menu_factory: Callable[..., MenuView],
        /,
        *args: Any,                      # 新增：positional 通道
        placement: str = "cursor",       # keyword-only，避免与 **kwargs 撞名
        **kwargs: Any,                   # 重命名 context → kwargs，对齐 Callback 语义
    ) -> None:
        super().__init__(**kwargs)
        if placement not in _VALID_PLACEMENTS:
            ...
        self.args = tuple(_coerce_expr(a) for a in args)
        self.menu_factory = menu_factory
        self.placement = placement
```

**`src/mutgui/_menu_impl.py`** — `menu_trigger_handle` 改成 `factory(*positional, **kw)`，逻辑跟 `Callback.handle` 平行。复用 `_resolve_args_kwargs` 见下节。

**`to_wire`** 同步加 `$args` wire 部分（参考 `Callback.to_wire`）。

### 重复代码下沉到 EventHandler 基类

`Callback.handle` 与 `MenuTrigger.handle` 改造后包含相同的 args/kwargs 求值逻辑。下沉到基类：

```python
class EventHandler:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = tuple(_coerce_expr(a) for a in args)
        self.extract = {k: _coerce_expr(v) for k, v in kwargs.items()}

    def _resolve_call(
        self, view: View, event: Event,
    ) -> tuple[list[Any], dict[str, Any]]:
        """按 env 求值 args/kwargs，返回 (positional, keyword)。"""
        context = _build_dispatch_context(view, event)
        wire_args = event.data.get("$args", [])
        positional: list[Any] = []
        wire_idx = 0
        for expr in self.args:
            if expr.env == "direct":
                positional.append(expr.source)
            elif expr.env == "wire":
                positional.append(wire_args[wire_idx] if wire_idx < len(wire_args) else None)
                wire_idx += 1
            else:
                positional.append(eval_host_expr(expr.source, context))
        keyword = _eval_kwargs(self.extract, event.data, context)
        return positional, keyword

    def to_wire(self) -> dict[str, Any]:
        wire = {k: e.source for k, e in self.extract.items() if e.env == "wire"}
        wire_args = [e.source for e in self.args if e.env == "wire"]
        if wire_args:
            wire["$args"] = wire_args
        return {"$handler": wire}
```

`Callback.handle` 缩成：

```python
async def handle(self, view, event) -> bool:
    positional, keyword = self._resolve_call(view, event)
    result = self.callback(*positional, **keyword)
    if inspect.isawaitable(result):
        await result
    return True
```

`menu_trigger_handle` 缩成：

```python
@impl(MenuTrigger.handle)
async def menu_trigger_handle(self, view, event) -> bool:
    positional, kwargs = self._resolve_call(view, event)
    # 关闭已有菜单
    ext = render_ext(view)
    for child in list(ext.overlay_children.values()):
        if isinstance(child, MenuView):
            await child.close()
    # 创建新菜单
    menu_view = self.menu_factory(*positional, **kwargs)
    if not isinstance(menu_view, MenuView):
        return False
    menu_view.owner = view
    menu_view.install_event_filter(_close_filter)   # 保留 — 关键
    ext.overlay_children[menu_view.id] = menu_view
    view.invalidate()
    return True
```

`Bind` 不受影响（它有独立的简化路径）。

### 调用侧迁移

**`action.py` — `ActionMenu._render_resolved_items` (~L538)**

```python
# 之前
node["onClick"] = Callback(
    lambda action=item.action, ctx=context: action.execute(ctx),
)
node["onMouseEnter"] = MenuTrigger(
    lambda action=item.action, ctx=context:
        ActionMenu(owner=self.owner, source_action=action, context=ctx),
    placement="right-start",
)

# 之后
node["onClick"] = Callback(item.action.execute, context)
node["onMouseEnter"] = MenuTrigger(
    ActionMenu,
    source_action=item.action,
    context=context,
    placement="right-start",
)
```

> 调用侧**不再传 `owner=`**。`MenuView.owner` 作为 lifecycle 字段由 `_menu_impl` 自动赋值为 trigger view；传了也会被覆盖。业务 owner 走 `ActionContext.owner`（同名双角色语义的遗留问题记录在 `refactor-menuview-owner-roles.md`）。

**`action.py` — `ActionToolbar._render_action` (~L700)** 和 **`dock_panel.py` — `_render_action` (~L370)** 同样模式。

`_button_schema` 的参数类型 `on_click: Callback | MenuTrigger | None` 不变。

### 设计取舍记录

- **`placement` 用 keyword-only**：会被 MenuTrigger 截走、不进 kwargs。理论上跟"factory 也想接 placement"撞名，但实际 menu factory（`MenuView` / `ActionMenu`）没这字段，撞了的话 `functools.partial` 兜底。这与现状一致。
- **`**context` 改名 `**kwargs`**：原名暗示 menu context，新名对齐 Callback 的"透传 kwargs"语义，更通用。`**name` 形参不构成 API 契约（调用方写不到 `context=...` 字面量），docstring / 测试同步更新即可。
- **保留 positional 通道**：当前 `ActionMenu` 不需要，但保留对 `Callback` 的对称性，未来 factory 想用 positional ctor 也支持。
- **不新增 EventHandler 子类**：`ActionCallback` / `ActionMenuTrigger` 是非常窄的领域封装，会重复 menu 挂载逻辑（且 spec 旧版漏掉 `install_event_filter` 是真实 regression）。本方案让 events 体系自身够用。
- **调用侧不再传 `owner=`**：`MenuView.owner` 是 lifecycle 字段，`_menu_impl.menu_trigger_handle` 会强制覆盖为 trigger view。业务 owner 走 `ActionContext.owner`。该字段双角色语义混乱是遗留问题，独立记录在 `refactor-menuview-owner-roles.md`，本次不动。
## 消费者场景

| 消费者 | 场景 | 依赖的输出 | 验收标准 |
|--------|------|-----------|---------|
| `action.py` 内部渲染 | toolbar / split / dropdown / menu 渲染 | `Callback(method, *args, **kwargs)` `MenuTrigger(factory, *args, **kwargs, placement=...)` | 8 处 lambda 全部移除；现有 demo 行为不变 |
| `dock_panel.py` `_render_action` | DockPanel 工具栏渲染 Action | 同上 | demo `python demo/app.py` 行为不变 |
| 其他 EventHandler 用法（`Bind`、自定义 callback） | 不受影响 | — | 现有测试通过 |
| 类型检查 | 渲染相关 ~32 个 pyright unknown 错误 | bound method / class ctor 类型完整 | `pyright src/mutgui` 错误数下降到目标值 |

## 实施步骤清单

- [x] `events.py` — `EventHandler` 基类改造
  - [x] `__init__` 增加 `*args` 通道，存 `self.args: tuple[Expr, ...]`
  - [x] 新增 `_resolve_call(view, event) -> (positional, keyword)` 方法
  - [x] `to_wire` 同时输出 wire kwargs 和 `$args`（参考现 `Callback.to_wire`）
- [x] `events.py` — `Callback` 简化
  - [x] `__init__` 调用 `super().__init__(*args, **extract)`，移除自身 args 维护
  - [x] `handle` 改为调用 `self._resolve_call(...)` + `self.callback(*p, **k)`
  - [x] 移除自身 `to_wire`（继承基类即可）
- [x] `events.py` — `Bind` 兼容确认
  - [x] `super().__init__()` 不传 args/extract，行为不变
  - [x] 自身 `to_wire` 完全独立（不调用 super），保持现状
- [x] `menu.py` — `MenuTrigger` 对齐 `Callback`
  - [x] 签名改为 `(menu_factory, /, *args, placement="cursor", **kwargs)`
  - [x] `super().__init__(*args, **kwargs)` 替代当前 `**context`
  - [x] 移除自身 args 维护逻辑
  - [x] `to_wire` 调 `super().to_wire()` 后补 `$menu` / `$placement`
  - [x] docstring 同步：`**context` → `**kwargs`，新增 positional 说明
- [x] `_menu_impl.py` — `menu_trigger_handle` 改造
  - [x] 改用 `self._resolve_call(view, event)` 取 positional + kwargs
  - [x] `self.menu_factory(*positional, **kwargs)`
  - [x] 保留 `install_event_filter(_close_filter)` / `overlay_children` 挂载逻辑
- [x] 调用侧迁移 — `action.py`（6 处 lambda）
  - [x] L543 `onMouseEnter` MenuTrigger → `(ActionMenu, source_action=item.action, context=context, placement="right-start")`
  - [x] L556 `onClick` Callback → `(item.action.execute, context)`
  - [x] L712/L722 split 渲染（main onClick + menu MenuTrigger）
  - [x] L744 dropdown MenuTrigger
  - [x] L760 button onClick Callback
  - [x] 全部不传 `owner=`（由 `_menu_impl` 自动赋值）
- [x] 调用侧迁移 — `dock_panel.py`（2 处 lambda）
  - [x] L379 onClick Callback
  - [x] L384 onMenuClick MenuTrigger（`ctx.with_updates(surface="menu")` 改为渲染期先算好新 ctx 再传入）
- [x] 测试验证
  - [x] `pytest tests/` 全部通过（重点 `test_menu.py`、`test_action.py`、`test_events.py`、`test_dock_panel.py`）

