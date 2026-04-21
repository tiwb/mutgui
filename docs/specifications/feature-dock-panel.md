# DockPanel 响应式面板布局组件 设计规范

**状态**：✅ 已完成
**日期**：2026-04-21
**类型**：功能设计

## 需求

1. 为 mutgui 提供后端驱动的多面板布局组件（`mutgui.DockPanel`）
2. 支持二分分割（水平/垂直），分割可嵌套
3. 叶子节点为 TabSet，始终显示 tab 栏（面板名称 + 图标）
4. 响应式坍缩：空间不足时分割自动合并为 TabSet，空间恢复时自动拆分
5. per-viewport 状态追踪（可见面板集合、active tab、tab 顺序），类似 VirtualList
6. 支持拖拽调整 tab 顺序和面板归属
7. Splitter 拖拽调整分割比例
8. Tab 栏可配置：位置（top/bottom/left/right）、显示模式（图标+文字/仅图标/图标+活跃tab文字）
10. SplitNode 支持 merge_bars：两个子 TabSet 的 tab 栏融合为一条，两端对齐
11. Tab 栏支持额外操作按钮（菜单、新建等）
12. Tab 停靠分割：拖 tab 到 TabSet 内容区边缘，将该 TabSet 分割为两个子面板
13. 页面边缘停靠：拖 tab 到 DockPanel 容器四边，在根节点外层创建新分割
14. 停靠预览：拖拽期间显示半透明遮罩预览停靠后的布局效果

### 不在范围内

- 浮动面板（floating）
- 共享 View 对象（多个布局引用同一 View 实例）
- 布局持久化（可配置是否实时同步）
- flexlayout-react 依赖

### 前置依赖

- `feature-framework-core.md` — 基础框架
- `feature-view-nesting.md` — View 嵌套与事件路由
- `feature-session-sharing.md` — 多客户端支持与 ViewChildFilter
- `feature-virtual-list.md` — per-viewport 状态追踪模式参考

## 关键参考

### 内部实现

- **VirtualList per-viewport 模式** — `src/mutgui/virtual_list.py`，`_viewports: dict[channel_id, tuple]` + `ViewChildFilter` + `_refresh_visible()` 计算可见集合的并集
- **ViewChildFilter** — `src/mutgui/_viewport_impl.py:108-160`，per-viewport 子 View 过滤，push 时只发送该 viewport 可见的子节点
- **mutbot flexlayout 用法** — `mutbot/frontend/src/lib/layout.ts` + `mutbot/frontend/src/App.tsx`，布局模型 JSON 化、debounced 持久化、tab 管理

### 外部参考

- **flexlayout-react** — 二分分割 + TabSet 模型，JSON 布局描述，行业参考
- **react-resizable-panels** — 轻量分割面板库，PanelGroup/Panel/ResizeHandle 组件模型
- **VSCode workbench** — 多级坍缩（正常→紧凑→侧栏→隐藏）、Activity Bar

## 设计方案

### 核心概念

| 概念 | 说明 |
|------|------|
| **DockPanel** | 顶层 View，声明面板结构和布局树 |
| **LayoutTree** | 布局树模型，描述分割和 TabSet 的嵌套关系 |
| **SplitNode** | 分割节点，将空间二分为两个子节点（水平或垂直） |
| **TabSetNode** | 叶子节点，包含一个或多个 Panel 的 tab 页签 |
| **Panel** | 面板定义（ID、标题、图标、最小尺寸、内容 View） |

### 布局树模型（后端数据结构）

布局树是一棵二叉树，内部节点为 SplitNode，叶子节点为 TabSetNode：

```
SplitNode(horizontal)
├── TabSetNode(panels=[A, B])
└── SplitNode(vertical)
    ├── TabSetNode(panels=[C])
    └── TabSetNode(panels=[D, E])
```

#### SplitNode

```python
@dataclass
class SplitNode:
    direction: Literal["horizontal", "vertical"]
    children: tuple[LayoutNode, LayoutNode]  # 严格二分
    id: str | None = None     # 用户可指定，未指定则自动生成
    ratio: float = 0.5        # 第一个子节点占比（0.0-1.0），可自由拖拽至 0-1
    merge_bars: bool = False   # 融合两个子 TabSet 的 tab 栏
    collapse_below: int | None = None  # 坍缩阈值（px）。None=继承 DockPanel 默认值，0=明确不坍缩，>0=低于此值时坍缩
```

`merge_bars=True` 时，要求两个子节点都是 TabSetNode。前端将两个 tab 栏提升到 Split 层级渲染为一条连续的 bar，两端对齐（第一个子节点的 tabs 靠起始端，第二个靠末尾端）。内容区仍按 ratio 分割。

融合 bar 中，一侧的 tabs 在空间充足时不受分割比例约束，可以越过内容区的分割线位置。只在两侧 tabs 挤到一起时才受限。

```
merge_bars=True 效果（水平分割，tab 栏在顶部）：
┌──────────────────────────────────┐
│[P1|P2]                   [P3|P4]│  ← 一条 bar，两端对齐
├──────────────┬───────────────────┤
│  Content A   │  Content B        │  ← 内容区按 ratio 分割
└──────────────┴───────────────────┘

右侧 tab 很多时，可越过内容分割线：
┌──────────────────────────────────┐
│[P1] [P3|P4|P5|P6|P7|P8]        │
├──────────────┬───────────────────┤
│  Content A   │  Content B        │
└──────────────┴───────────────────┘
```

#### TabSetNode

```python
@dataclass
class TabSetNode:
    panel_ids: list[str]        # 该 TabSet 中的面板 ID 列表
    id: str | None = None       # 用户可指定，未指定则自动生成
    active_id: str | None = None
    bar_position: Literal["top", "bottom", "left", "right"] = "top"
    display_mode: Literal["icon-text", "icon", "icon-active-text"] = "icon-text"
    actions: list[ActionDef] | None = None  # tab 栏额外操作按钮
```

**Tab 栏位置**（`bar_position`）：

| 值 | tab 栏位置 | 典型用途 |
|----|-----------|---------|
| `top` | 顶部（默认） | 普通面板区 |
| `bottom` | 底部 | 底部状态栏风格 |
| `left` | 左侧 | 侧边工具栏（VSCode Activity Bar） |
| `right` | 右侧 | 右侧属性面板栏 |

**显示模式**（`display_mode`）：

| 值 | 效果 | 典型用途 |
|----|------|---------|
| `icon-text` | 所有 tab 显示图标 + 文字 | 顶部 tab 栏（默认） |
| `icon` | 所有 tab 只显示图标 | 侧边工具栏 |
| `icon-active-text` | 活跃 tab 显示图标 + 文字，其余只显示图标 | 紧凑侧边栏 |

**额外操作按钮**（`actions`）：

```python
@dataclass
class ActionDef:
    id: str
    icon: str
    tooltip: str | None = None
    position: Literal["start", "end"] = "end"  # 放在 tab 栏的哪一端
```

操作按钮不代表面板，点击触发后端事件（与 tab 切换走同一套 EventHandler 机制）。常见用途：菜单（`...`）、折叠/展开、新建面板等。

#### Panel 定义

```python
@dataclass
class PanelDef:
    id: str
    title: str
    icon: str | None = None
    min_width: int = 0     # UI 提示用途，不驱动坍缩
    min_height: int = 0    # UI 提示用途，不驱动坍缩
    view: View | None = None  # 面板内容（子 View）
```

LayoutNode 为 `SplitNode | TabSetNode` 的联合类型。

**节点 ID 生成**：用户可在声明时指定 `id`，未指定则由 DockPanel 自增计数器自动分配（如 `split-1`、`tabset-2`）。不使用基于树位置的编码（如 `split-0-1`），因为 tab_move 引发树重构时位置编码会漂移，导致 per-viewport 状态映射失效。

### IDE 风格布局示例

通过组合 bar_position、display_mode 和 merge_bars，可实现 VSCode/PyCharm 风格的布局：

```
VSCode 风格：
┌─────────────────────────────────────────┐
│ 📁  │  [main.py | utils.py]  [Terminal] │  ← merge_bars: 左侧 icon 模式 + 右侧 icon-text
│ 🔍  ├────────────────────┬──────────────┤
│ 🔀  │                    │              │
│     │  Editor            │  Outline     │
│     │                    │              │
│ ⚙️  ├────────────────────┴──────────────┤
│ 👤  │  [Problems | Output | Terminal]   │
└─────┴───────────────────────────────────┘

对应布局树：
SplitNode(horizontal, merge_bars=True)
├── TabSetNode(bar_position="left", display_mode="icon",
│              panels=[Explorer, Search, Git, Settings, Account])
└── SplitNode(vertical)
    ├── SplitNode(horizontal)
    │   ├── TabSetNode(panels=[main.py, utils.py])
    │   └── TabSetNode(panels=[Outline])
    └── TabSetNode(panels=[Problems, Output, Terminal])
```

### per-viewport 状态

参照 VirtualList 的 `_viewports` 模式，DockPanel 维护每个 viewport 的布局状态：

```python
@dataclass
class ViewportLayoutState:
    visible_panel_ids: set[str]      # 当前可见的面板集合
    collapsed_splits: set[str]       # 已坍缩的 SplitNode ID 集合
    tab_orders: dict[str, list[str]] # TabSetNode ID → tab 顺序（用户可调整）
    active_tabs: dict[str, str]      # TabSetNode ID → 活跃 panel ID
    split_ratios: dict[str, float]   # SplitNode ID → 当前分割比例
```

DockPanel 持有：
```python
_viewport_states: dict[int, ViewportLayoutState]  # channel_id → 状态
```

### 可见性驱动推送

复用 `ViewChildFilter` 机制：

1. 每个面板的内容是一个子 View
2. `_refresh_visible()` 计算所有 viewport 可见面板的**并集**作为 render 输出
3. `ViewChildFilter` 记录每个 viewport 的可见面板子集
4. push 时按 viewport 过滤，不可见面板的子 View 不推送
5. 面板从不可见变为可见时，触发该子 View 的 full render 推送

### 响应式坍缩算法

**核心原则**：

1. 布局树结构不变，坍缩只改变渲染形态
2. Splitter 拖拽自由（ratio 0-1），被拖动的 split 本身永远不坍缩
3. 坍缩只发生在后代 split 上：祖先的 ratio 变化或 viewport 缩小导致后代 split 可用空间不足

#### 触发条件

SplitNode 的 `collapse_below` 字段定义坍缩阈值。当该 split 在分割方向上的**总可用空间**低于阈值时，合并为 TabSet。

- `collapse_below = None`：继承 DockPanel 的 `default_collapse_below`（默认）
- `collapse_below = 0`：该 split 明确不自动坍缩
- `collapse_below = 300`：当水平 split 宽度 < 300px 或垂直 split 高度 < 300px 时坍缩

DockPanel 通过 `default_collapse_below` 参数设置全局默认坍缩阈值（默认 0）。所有未指定 `collapse_below` 的 SplitNode（包括停靠操作动态创建的）统一使用此默认值。

#### 算法（自底向上递归）

```
compute_layout(node, available_width, available_height):
  if node is TabSetNode:
    return node

  # node is SplitNode
  axis_space = available_width if node.direction == "horizontal" else available_height

  # 坍缩判定：解析 None → DockPanel 默认值，然后判断
  threshold = node.collapse_below if node.collapse_below is not None else default_collapse_below
  if threshold > 0 and axis_space < threshold:
    return collapse_to_tabset(node)

  # 空间充足，按 ratio 分配，递归处理子节点
  c0_space = axis_space * node.ratio
  c1_space = axis_space - c0_space
  if node.direction == "horizontal":
    child0 = compute_layout(node.children[0], c0_space, available_height)
    child1 = compute_layout(node.children[1], c1_space, available_height)
  else:
    child0 = compute_layout(node.children[0], available_width, c0_space)
    child1 = compute_layout(node.children[1], available_width, c1_space)
  return SplitNode(..., children=(child0, child1))

collapse_to_tabset(node) -> TabSetNode:
  panel_ids = collect_all_panels(node)  # 保持原声明顺序
  return TabSetNode(panel_ids=panel_ids)
```

#### Splitter 拖拽与坍缩的关系

- `split_resize` 事件只更新目标 SplitNode 的 ratio（0.0-1.0 自由范围）
- ratio 变化后重新计算布局，**后代** SplitNode 可能因可用空间减少而坍缩
- 被拖动的 split 本身不受坍缩判定（它始终保持 split 结构）
- 示例：拖动 explorer 右侧 splitter 往右 → 右侧空间缩小 → 右侧嵌套的 editors|outline split 空间不足 → 坍缩为 TabSet

#### 坍缩与恢复

- **坍缩方向**：自底向上（内层分割先坍缩）
- **恢复方向**：自顶向下（外层分割先恢复）
- **自动恢复**：当可用空间重新超过 `collapse_below` 时，自动从原始布局树恢复 split 结构
- **结构不变性**：坍缩只影响渲染输出，不修改原始布局树。原始树始终保留，用于恢复
- **面板归属不变性**：tab 重排不改变面板在布局树中的归属。坍缩态下用户重排了 tab 顺序，恢复时仍按原始归属拆分

### 前端→后端事件

| 事件 | 触发时机 | payload |
|------|----------|---------|
| `resize` | viewport 或容器尺寸变化 | `{width, height}` |
| `tab_switch` | 用户点击 tab | `{tabset_id, panel_id}` |
| `tab_reorder` | 用户拖拽 tab 调整顺序 | `{tabset_id, panel_ids: [...]}` |
| `tab_move` | 用户拖拽 tab 到另一个 TabSet | `{from_tabset, to_tabset, panel_id, index}` |
| `split_resize` | 用户拖拽 splitter | `{split_id, ratio}` |
| `action_click` | 用户点击 tab 栏操作按钮 | `{tabset_id, action_id}` |
| `tab_dock` | 拖拽 tab 到 TabSet 内容区边缘停靠 | `{from_tabset, panel_id, target_tabset, position}` |
| `edge_dock` | 拖拽 tab 到 DockPanel 边缘停靠 | `{from_tabset, panel_id, edge}` |

### 后端→前端推送

后端计算出布局形态后，通过 render 推送 wire tree。前端是哑渲染器，不做布局决策：

```json
{
  "$component": "mutgui.DockPanel",
  "$id": "dock",
  "$children": [
    {
      "$component": "mutgui.DockPanel.Split",
      "$id": "split-1",
      "direction": "horizontal",
      "ratio": 0.5,
      "mergeBars": false,
      "$children": [
        {
          "$component": "mutgui.DockPanel.TabSet",
          "$id": "tabset-1",
          "barPosition": "top",
          "displayMode": "icon-text",
          "tabs": [{"id": "a", "title": "Panel A", "icon": "file"}],
          "actions": [{"id": "menu", "icon": "more-horizontal", "position": "end"}],
          "activeId": "a",
          "$children": [{"$view": "panel-a"}]
        },
        {
          "$component": "mutgui.DockPanel.TabSet",
          "$id": "tabset-2",
          "barPosition": "top",
          "displayMode": "icon-text",
          "tabs": [{"id": "c", "title": "Panel C"}, {"id": "d", "title": "Panel D"}],
          "activeId": "c",
          "$children": [{"$view": "panel-c"}]
        }
      ]
    }
  ]
}
```

`mergeBars=true` 时的 wire tree 结构不变（仍是 Split 包含两个 TabSet），前端组件根据 `mergeBars` 标志决定渲染方式：将两个子 TabSet 的 tab 栏提升到 Split 层级，渲染为一条两端对齐的 bar。

注意：TabSet 的 `$children` 只包含 active panel 的 `$view`（不可见面板不推送）。

### 布局持久化

- 后端持有布局树的序列化 JSON（结构 + per-viewport 状态）
- 默认行为：last-write-wins，不实时同步（与 mutbot 一致）
- 可配置实时同步：`sync_layout=True` 时，一个 viewport 的布局变更推送到所有 viewport
- 前端交互产生的布局变更（splitter 拖拽、tab 重排）debounce 后上报后端

### 拖拽行为

#### Tab 重排（同一 TabSet 内）

- 前端处理拖拽动画
- 完成后上报 `tab_reorder` 事件
- 后端更新 per-viewport 的 tab 顺序
- 不改变面板在布局树中的归属

#### Tab 移动（跨 TabSet）

- 拖拽 tab 到另一个 TabSet 的 tab 栏区域
- 上报 `tab_move` 事件
- 后端修改布局树结构（面板从一个 TabSetNode 移到另一个）
- 这是结构性变更，影响所有 viewport
- **空 TabSet 清理**：源 TabSet 面板全部移走后自动删除，父 SplitNode 独子提升替代父节点（tab_move 处理逻辑中一并完成）
- **merge_bars 降级**：独子提升后，如果某个 `merge_bars=True` 的 SplitNode 的子节点不再全是 TabSetNode，自动将 `merge_bars` 降级为 `false`（防御性降级，保证渲染不出错）

#### 坍缩态下的拖拽

- 坍缩后多个面板合并在一个 TabSet 中
- tab 重排（reorder）仍然有效（调整显示顺序）
- **允许从坍缩态拖出**：tab 可从坍缩态 TabSet 拖出进行 move 和 dock 操作。源 TabSet 面板减少后，cleanup_tree 正常处理空节点清理
- 恢复时按原始归属拆分，不受 tab 重排影响

### 停靠分割（Dock Splitting）

拖拽 tab 可触发两种停靠行为，将目标区域分割为两个面板。

#### 面板内停靠（Panel Dock）

拖拽 tab 进入某个 TabSet 的内容区域时，根据鼠标相对位置判断停靠方向：

```
┌─────────────────────────┐
│         top 25%         │
├────┬───────────┬────────┤
│    │           │        │
│ L  │  center   │  R     │
│25% │   50%     │  25%   │
│    │           │        │
├────┴───────────┴────────┤
│        bottom 25%       │
└─────────────────────────┘
```

- **边缘 25%**：触发停靠分割，显示半透明遮罩覆盖对应半区
- **中心 50%**：回落为 tab_move（等价于拖到 tab bar），遮罩覆盖整个内容区
- **角落区域**（两个边缘 25% 重叠）：优先 top/bottom 方向

**树操作**（以 position=left 为例）：

```
Before:  TabSet[A, B, C]

After:
  SplitNode(horizontal, ratio=0.5)
  ├── TabSet[拖入的 tab]    ← 新建
  └── TabSet[A, B, C]       ← 原 TabSet
```

- position → direction：left/right → horizontal，top/bottom → vertical
- position → 子节点顺序：left/top → 新 TabSet 在前，right/bottom → 新 TabSet 在后
- 新 SplitNode 替换原 TabSet 在父节点中的位置
- 新建的 SplitNode 和 TabSet 由自增计数器分配 ID
- 新分割 ratio 固定 0.5
- 新分割 `collapse_below` 不指定（`None`），自动继承 DockPanel 默认值

#### 页面边缘停靠（Edge Dock）

拖拽开始时，DockPanel 容器四边各显示一个停靠触发区（约 40×40px 矩形，居中于边缘中点）。鼠标拖到触发区时，显示半透明遮罩覆盖整个 DockPanel 对应边缘的一半区域。

```
                    ┌──┐
                    │▼ │ ← top 触发区
        ┌───────────┴──┴───────────┐
        │                          │
  ┌──┐  │                          │  ┌──┐
  │► │  │       DockPanel          │  │◄ │
  └──┘  │                          │  └──┘
        │                          │
        └───────────┬──┬───────────┘
                    │▲ │ ← bottom 触发区
                    └──┘
```

**树操作**（以 edge=right 为例）：

```
Before:
  Root (原有布局树)

After:
  SplitNode(horizontal, ratio=0.5)
  ├── Root (原有布局树)     ← 原根节点降级为子节点
  └── TabSet[拖入的 tab]    ← 新建
```

- edge → direction：同面板内停靠
- edge → 子节点顺序：left/top → 新 TabSet 在前，right/bottom → 新 TabSet 在后
- 新 SplitNode 成为新的布局根节点
- 新分割 ratio 固定 0.5
- 新分割 `collapse_below` 不指定（`None`），自动继承 DockPanel 默认值

#### 停靠预览

前端在拖拽期间渲染半透明遮罩（DockOverlay），预览停靠后的布局效果：

- **面板内停靠预览**：遮罩覆盖目标 TabSet 内容区的对应半区
- **中心区预览**：遮罩覆盖目标 TabSet 整个内容区（表示合并到该 TabSet）
- **边缘停靠预览**：遮罩覆盖 DockPanel 容器对应边缘的一半
- **无动画过渡**：遮罩直接出现/消失

#### 前端拖拽状态

拖拽状态从 TabSet 内部提升到 DockPanel 根级 Context：

```typescript
interface DockDragState {
  isDragging: boolean;           // 控制边缘停靠区显示
  preview: DockPreview | null;   // 当前停靠预览
}

type DockPreview =
  | { type: 'panel-dock'; targetId: string; position: 'top' | 'bottom' | 'left' | 'right' }
  | { type: 'tab-move'; targetId: string }    // 中心区，回落为 tab_move
  | { type: 'edge-dock'; edge: 'top' | 'bottom' | 'left' | 'right' }
```

#### 后端清理逻辑

停靠操作复用现有的 `cleanup_tree()` 逻辑：

- 源 TabSet 面板全部移走后自动删除
- 父 SplitNode 独子提升替代父节点
- `merge_bars` 降级规则不变

### 前端组件结构

```
mutgui.DockPanel (根容器)
├── DockPanelCtx.Provider（拖拽状态 + 回调上下文）
├── EdgeDropZone × 4（DockPanel 四边停靠触发区，仅拖拽时可见）
├── DockOverlay（半透明停靠预览遮罩，根据 preview 状态定位）
├── mutgui.DockPanel.Split (分割容器)
│   ├── 普通模式（mergeBars=false）：
│   │   ├── 子节点 1（TabSet 或嵌套 Split，自带 tab 栏）
│   │   ├── Splitter handle
│   │   └── 子节点 2
│   └── 融合模式（mergeBars=true）：
│       ├── MergedTabBar（两个子 TabSet 的 tab 栏融合，两端对齐）
│       ├── 子节点 1 内容区（无 tab 栏）
│       ├── Splitter handle
│       └── 子节点 2 内容区（无 tab 栏）
└── mutgui.DockPanel.TabSet (tab 页签容器)
    ├── Tab 栏（位置由 barPosition 决定，含 tabs + actions）
    ├── 内容区（MutguiView 渲染 active panel 的子 View）
    └── ContentDropZone（内容区边缘停靠检测，拖拽时激活）
```

前端职责：
- 渲染 splitter 和 tab 栏
- 检测容器尺寸变化（ResizeObserver）→ debounce（100-200ms）后上报后端（避免连续 resize 产生过多往返）
- 处理拖拽交互（tab 重排、tab 移动、tab 停靠、splitter 拖拽）→ 上报后端。拖拽自行实现（splitter 用 pointer event，tab 用 HTML5 Drag and Drop API），不引入额外依赖
  - 停靠检测：内容区边缘 25% 触发面板内停靠，DockPanel 四边触发区触发页面边缘停靠
- **不做布局决策**（坍缩/恢复由后端决定）

### 消费者场景

| 消费者 | 场景 | 依赖的输出 | 验收标准 |
|--------|------|-----------|---------|
| mutbot | IDE 风格多面板布局 | DockPanel + 多种面板 View | 替代 flexlayout-react 实现等效功能 |
| mutgui demo | 基础多面板演示 | DockPanel + 简单面板 | 可拖拽调整、响应式坍缩正常 |
| 移动端场景 | 极窄 viewport | 响应式坍缩结果 | 自动坍缩为单 TabSet |

## 实施步骤清单

- [x] 后端数据结构和布局树操作（`dock_panel.py`）
- [x] 坍缩算法和 per-viewport 状态追踪
- [x] 后端事件处理（tab_switch/reorder/move、split_resize、action_click）
- [x] 前端 DockPanel/Split/TabSet 组件（`dock-panel.tsx`）
- [x] 组件注册（standalone.tsx）和模块导出（`__init__.py`、`index.ts`）
- [x] IDE 风格 demo（`dock_demo.py`）
- [x] 前端构建验证（library + standalone + antd 均通过）
- [x] 现有测试回归通过（62/62）
- [x] 坍缩算法重构：splitter ratio 自由 0-1 + collapse_below 阈值驱动 + 自动恢复
- [x] 浏览器实际验证（tab 切换、拖拽重排、splitter 拖拽、坍缩恢复）
- [x] 后端 tab_dock 事件处理（目标 TabSet 替换为 SplitNode + 新 TabSet）
- [x] 后端 edge_dock 事件处理（根节点包裹新 SplitNode）
- [x] 解除坍缩态拖出限制（允许从坍缩态 TabSet 拖出 dock 和 move）
- [x] 前端拖拽状态提升到 DockPanel Context
- [x] 前端 ContentDropZone（TabSet 内容区边缘检测 + 停靠方向判断）
- [x] 前端 EdgeDropZone（DockPanel 四边停靠触发区）
- [x] 前端 DockOverlay（半透明遮罩预览）
- [x] 前端 drop 事件触发 tab_dock / edge_dock / tab_move 回调
- [x] 浏览器验证停靠功能（面板内停靠、边缘停靠、预览效果）
