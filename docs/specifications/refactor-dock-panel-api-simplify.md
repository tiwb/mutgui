# DockPanel API 简化重构

**状态**：✅ 已完成
**日期**：2026-05-22
**类型**：重构

## 需求

1. 消除 `DockPanel.set_panel_view()` 两步初始化——当前使用者必须先构造 `DockPanel(panels=[...], ...)` 再逐面板调用 `set_panel_view()`，视图入口分散在两处，易遗漏且不直观
2. PanelDef 的 `id` 和 `set_panel_view` 的 `panel_id` 重复指定同一标识，违反 DRY
3. `action_context_data` 藏在 runtime extension（`_dp_ext(self).action_context_data`）中，不够直观，且与 mutgui 其他 View（如 ActionProvider）的 ActionContext 使用方式不一致
4. 首次 render（尚未收到 onResize）返回所有 panel View 作为 $children，使用假的 viewport 尺寸渲染，可能导致前端布局抖动

## 关键参考

- `src/mutgui/dock_panel.py` — `PanelDef` / `DockPanel` 声明
- `src/mutgui/_dock_panel_impl.py` — `DockPanelRuntime` 扩展，`render()` / `_dock_panel_children()` 实现
- `src/mutgui/action.py` — `ActionContext` 类型
- `demo/examples/action.py` / `demo/examples/dock.py` — 消费者示例
- `tests/test_dock_panel.py` / `tests/test_dock_panel_core.py` / `tests/test_action.py` — 测试

## 设计方案

### PanelDef：id 外提 + 内聚 view

将 panel id 从 `PanelDef` 内部字段外提到 dict key，同时将 view 内聚到 `PanelDef` 中：

```python
# 旧
@dataclass
class PanelDef:
    id: str
    title: str
    icon: str | None = None
    min_width: int = 0
    min_height: int = 0

# 新
@dataclass
class PanelDef:
    title: str
    icon: str | None = None
    min_width: int = 0
    min_height: int = 0
    view: View | None = None
```

`view` 为 `None` 表示该面板暂无视图（如延迟加载场景），后续可调用 `DockPanel.panels["id"].view = some_view` 更新。

### DockPanel：panels 改为 dict + 移除 set_panel_view

```python
# 旧
class DockPanel(View):
    panels: dict[str, PanelDef]
    panel_views: dict[str, View]
    ...
    def __init__(self, id: str, panels: list[PanelDef], layout: LayoutNode, ...) -> None: ...
    def set_panel_view(self, panel_id: str, view: View) -> None: ...

# 新
class DockPanel(View):
    panels: dict[str, PanelDef]
    ...
    def __init__(self, id: str, panels: dict[str, PanelDef], layout: LayoutNode, ...) -> None: ...
```

`__init__` 中遍历 `panels`，当 `p.view is not None` 时自动设置 `p.view.id = pid`（与旧 `set_panel_view` 行为一致）。

移除 `panel_views` 属性和 `set_panel_view()` 方法。render 阶段直接从 `self.panels[active_id].view` 获取视图。

### action_context 公开化

将 `action_context_data` 从 `DockPanelRuntime` 扩展字段提升为 `DockPanel` 的公开属性：

```python
class DockPanel(View):
    ...
    action_context: ActionContext | None = None
```

使用方式从 `_dp_ext(dock).action_context_data["page"] = self` 变为 `dock.action_context = ActionContext(data={"page": self})`，与 mutgui Action 系统的 `ActionContext` 模式一致。

同时从 `DockPanelRuntime` 中移除 `action_context_data` 字段。

### 首次 render 不展示子 View

`_dock_panel_children()` 在尚未收到 onResize（即 `viewport_sizes` 中无该 viewport 的尺寸）时返回空列表 `[]`，而非所有 panel View：

```python
def _dock_panel_children(vid: int, self: DockPanel) -> RenderTree:
    size = _dp_ext(self).viewport_sizes.get(vid)
    if not size:
        return []  # 等待 onResize，避免假尺寸算错布局
    ...
```

旧行为是返回所有 panel View 作为 children，前端使用无意义的 viewport 尺寸渲染，导致布局抖动。新行为下首次渲染仅推送 DockPanel 壳，待 onResize 返回真实尺寸后再推送带子 View 的正确布局。

## 实施步骤清单

- [x] `PanelDef` 移除 `id` 字段，新增 `view: View | None = None`
- [x] `DockPanel` 声明：`panels` 参数类型从 `list[PanelDef]` 改为 `dict[str, PanelDef]`
- [x] `DockPanel` 声明：移除 `panel_views` 属性和 `set_panel_view()` 方法
- [x] `DockPanel` 声明：新增 `action_context: ActionContext | None = None`，`default_collapse_below` 加默认值 0
- [x] `DockPanelRuntime` 移除 `action_context_data` 字段
- [x] `dock_panel_init`：遍历 panels dict 设置 `p.view.id = pid`，初始化 `self.action_context = None`
- [x] `dock_panel_render`：通过 `self.panels` + `p.view` 替代 `self.panel_views`
- [x] `_dock_panel_children`：无 onResize 时返回 `[]`（移除 `all_views` 参数）
- [x] `_dock_panel_build_tabset_component`：从 `self.panels[active_id].view` 获取活跃视图
- [x] `_dock_panel_tabset_action_context`：用 `self.action_context.data` 替代 `_dp_ext(self).action_context_data`
- [x] Demo `action.py` 和 `dock.py`：迁移到 dict panels + 内聚 view
- [x] 测试 `test_dock_panel.py`：适配 dict panels、断言空 children
- [x] 测试 `test_dock_panel_core.py`：适配 dict panels
- [x] 测试 `test_action.py`：适配 dict panels + 内聚 view、`action_context` 替代 `action_context_data`
