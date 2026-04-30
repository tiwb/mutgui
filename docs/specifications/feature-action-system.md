# 动作系统设计规范

**状态**：✅ 已完成
**日期**：2026-04-29
**类型**：功能设计

## 需求

1. 在 mutgui 层引入一个**高于 Menu 的统一动作抽象**，用于表达 toolbar、menu、context menu、titlebar actions 等高层交互。
2. 保留现有 `MenuView` / `MenuTrigger` 作为**底层菜单机制**；Action 不替代 Menu，而是通过 `ActionMenu` 复用 Menu 能力。
3. 动作系统需要支持**可扩展**：既能被框架内置组件消费，也能被上层项目或业务代码扩展。
4. `DockPanel` 现有的 `TabSetNode.actions` 不再停留在 `ActionDef` 的极简按钮模型，而是升级为新的 `ActionRef` 体系。
5. category 设计遵循**开放字符串协议**：不做中心注册表，不引入“不可扩展 category”概念。
6. 一个 Action 同时投放到多个 category 是常态能力，不是特例。
7. 动态 action 设计遵循**稳定类型 + 运行时生成实例**模式，而不是依赖运行时注册大量临时类型。
8. 动作系统必须覆盖复杂 toolbar 的真实需求：
   - Action 本身就是一个 Widget，用于在 toolbar 中嵌入 UI
   - toolbar 上的 split button：主按钮执行 action，箭头展开下拉菜单
   - 入口是 Action，但展开菜单中承载复杂 UI，甚至是完整界面
9. 本次不设计运行时临时注入 API。
10. 本次不实现快捷键基础设施，但 Action 设计不能堵死未来快捷键系统的接入方向。

## 关键参考

- `src/mutgui/menu.py` — `MenuView` / `MenuTrigger`，底层菜单触发与浮层机制
- `src/mutgui/_menu_impl.py` — 菜单注入、关闭、overlay child 生命周期
- `src/mutgui/_view_impl.py` — `overlay_children` 注入机制
- `src/mutgui/dock_panel.py` — `TabSetNode.actions` 与现有 `ActionDef`
- `docs/specifications/feature-menu-system.md` — mutgui 菜单系统基础规范
- `docs/specifications/refactor-event-system.md` — `EventFilter` / `onKeyDown` 事件链

## 现状分析

### Menu 是机制层，不是动作抽象

`MenuView` 的职责是：

- 触发菜单
- portal 渲染
- 定位与关闭
- 管理子菜单

它并不负责这些更高层问题：

- 当前区域有哪些动作
- 同一动作在 toolbar/menu 中如何分别展示
- 动作是按钮、widget、dropdown 还是 split button
- category 如何成为扩展挂载点

因此 Menu 应继续作为**渲染机制层**存在，Action 则负责更高层的动作语义与呈现形态。

### `dock_panel.ActionDef` 只是局部按钮 schema

当前 `ActionDef` 只有：

```python
@dataclass
class ActionDef:
    id: str
    icon: str
    tooltip: str | None = None
    position: Literal["start", "end"] = "end"
```

它无法表达：

- 文本标签
- 快捷键
- 可见/可用/checked 状态
- 多 category 投放
- dropdown / split
- widget action
- 动态实例

所以它不再继续泛化，而是被 `ActionRef` 替代。

### 动作模式比"命令"更丰富

结合实际 GUI 框架的使用场景，动作系统至少需要覆盖 4 类能力：

1. **普通命令按钮** — 点击触发 `execute()`
2. **Widget Action** — 动作本身就是一个嵌入式控件（搜索框、下拉选择器、数值输入等），不依赖命令触发
3. **Dropdown / Split Button** — 主按钮执行动作，箭头展开子菜单；或纯 dropdown 入口
4. **复杂菜单内容** — 菜单中嵌入可交互配置面板、列表选择器，而非简单的 action 列表

因此，mutgui 的 Action 设计不能只围绕 `execute()` 建模，而必须覆盖**动作项的呈现形态**。

### category 一直是开放协议

在设计良好的 GUI 框架中，category 本质上是：

- 开放字符串协议
- 扩展挂载点
- 组合节点

没有中心化的 category 注册表。消费端直接声明自己属于哪个 category，多 category 是常见模式，例如：

- `("ProjectMenu", "MainToolbar")`
- `("AnimEditorToolbar", "AnimEditorContextMenu", "AnimTreeviewContextMenu")`
- `("ListViewConsoleViewToolbar", "StandardConsoleViewToolbar")`

### 动态的主流模式是"动态实例"，不是"动态类型"

大量真实场景使用的是：

- 动态菜单项生成函数
- 稳定的动作类 + 运行时生成若干实例

而不是运行时注册大量新的动作类型。

因此 mutgui 也应优先设计：

- **静态发现 Action 类型**
- **动态生成 ActionRef 实例**

## 设计方案

### 当前实现概览

当前代码中的动作系统已经落地为以下行为：

- `ActionToolbar`、`ActionMenu`、`DockPanel` tab bar 都基于同一套 `Action` / `ActionRef` / `ActionRegistry`
- 同一 category 可同时喂给多个 presenter；toolbar 通过 `position` 拆成左右两端，中间用 spacer 对齐
- `placement` 统一决定分组与排序；`ActionMenu` / `ActionToolbar` / DockPanel actions 都按 `group_name` 自动插入 divider / separator
- toolbar 中需要 dropdown / split 的动作，在 menu 中会表现为 submenu，保持一致的信息层级
- widget 型 action 若同时提供 `toolbar_view()` 和 `menu_view()`，则 menu 里可以直接内联对应 view
- category 与 provider 的展开结果会按 `ref_id` 去重；动态多实例 provider 需要显式提供不同 `ref_id`
- toolbar 支持 `label_mode`，可切换默认"图标+文字"和 `icon-only`
- shortcut 当前只做展示：menu 的 shortcut 列与 toolbar hover tip 都会显示，不实现快捷键分发

### 分层

动作系统分三层：

1. **Menu 机制层**  
   `MenuView` / `MenuTrigger` / 前端 menu portal，负责"怎么弹菜单"。
2. **Action 语义层**  
   `Action` / `ActionRef` / `ActionContext` / `ActionRegistry` / `ActionCategoryProvider`，负责"有哪些动作、状态如何、有哪些形态能力"。
3. **Action 呈现层**  
   `ActionMenu` / `ActionToolbar`，负责"把 Action 渲染成菜单项、toolbar 项、split button、widget item"等。

一句话：**Menu 负责弹，Action 负责是什么，ActionMenu/ActionToolbar 负责怎么呈现。**

### 核心概念

#### Action

`Action` 是一个可发现、可扩展的动作声明，建议使用 `mutobj.Declaration`：

```python
class Action(mutobj.Declaration):
    action_id: str = ""
    display_name: str = ""
    display_icon: str = ""
    display_tooltip: str = ""
    display_shortcut: str = ""
    display_category: str | tuple[str, ...] = ()
    placement: str = ""
    checkable: bool = False

    @classmethod
    def check_visible(cls, context: dict) -> bool | None:
        return None

    @classmethod
    def check_enabled(cls, context: dict) -> bool | None:
        return None

    @classmethod
    def check_checked(cls, context: dict) -> bool | None:
        return None

    @classmethod
    def menu_actions(cls, context: "ActionContext") -> list["ActionRef"] | None:
        return None

    @classmethod
    def menu_view(cls, context: "ActionContext") -> View | MenuView | None:
        return None

    @classmethod
    def toolbar_view(cls, context: "ActionContext") -> View | None:
        return None

    async def execute(self, params: dict, context: "ActionContext") -> None:
        ...
```

设计要点：

- `Action` 表示稳定的动作语义，不等于"必须是一个命令按钮"。
- `display_category` 是一等主能力，支持多 category。
- `menu_actions()` 用于标准 action 子菜单。
- `menu_view()` 用于复杂 dropdown/menu UI。
- `toolbar_view()` 用于 toolbar 中直接嵌入 UI。
- `display_shortcut` 当前主要用于显示，但未来可作为快捷键系统的重要元数据。

#### ActionRef

`ActionRef` 是某个消费场景中的动作引用，用于把一个 Action 投放到具体区域：

```python
@dataclass
class ActionRef:
    ref_id: str = ""
    action: str | type[Action]
    position: str = "end"
    variant: str = "auto"
    label: str | None = None
    icon: str | None = None
    tooltip: str | None = None
    shortcut: str | None = None
    placement: str | int | None = None
    params: dict[str, Any] | None = None
```

其中 `variant` 是关键字段：

- `auto`
- `button`
- `widget`
- `dropdown`
- `split`
- `menu-item`

职责：

- 引用动作本体
- 提供实例级唯一标识（`ref_id`）
- 允许 per-surface 显示覆盖
- 显式声明呈现偏好

设计说明：

- `ref_id` 默认可回退为 `action_id`
- 同一个 Action 以不同参数出现多次时，provider 应显式提供不同 `ref_id`
- `variant="split"` 应视为显式语义，不靠 presenter 猜测

#### Placement

动作的视觉分组与排序统一由单字段 `placement` 表达：

```text
[group-part "/"] item-part
```

- 不写 `/`：表示默认分组 `""`
- `group-part` 形式：`group_name[:group_order...]`
- `item-part` 形式：`token[:token...]`

示例：

- `10`
- `command:10/20`
- `recent:20/1`
- `beta:20/1:-2`

解析与比较规则：

1. 先按 `/` 拆出 `group-part` 与 `item-part`
2. `group_name` 取 `group-part` 的第一个字段；未提供时为 `""`
3. `group_order` 与 `item_order` 都按 `:` 拆成 token 序列
4. token 尝试转换为整数；转换失败时保留为字符串
5. 比较前归一化为 Python 可比较元组：
   - 数字 token → `(0, value)`
   - 字符串 token → `(1, value)`
6. 最终排序 key 为：`(group_order, group_name, item_order)`

separator 规则：

- `ActionMenu` 与 `ActionToolbar` 都在排序后扫描相邻项
- 相邻项 `group_name` 变化时自动插入 divider / separator
- 未显式分组的动作属于默认组 `""`，因此与具名分组相邻时同样会产生分隔

兼容性：

- `Action.order` / `ActionRef.order` 仍可作为旧写法输入，解析时等价为 `placement=str(order)`
- 新代码应统一使用 `placement`

#### ActionContext

```python
@dataclass
class ActionContext:
    view: View | None = None
    viewport_id: int | None = None
    surface: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
```

说明：

- `surface` 让同一个 Action 感知自己被投放在 `menu`、`toolbar`、`dock-tabbar` 等哪个场景
- `payload` 是运行时上下文
- 后续可按需扩充 channel、focus、selection 等信息

### Action 的 4 种一等形态

本设计把 Action 视为"可呈现动作项"，至少覆盖 4 种形态。

#### 1. Command Action

普通动作按钮：

- 通过 `execute()` 执行
- 可有 `checkable/checked`
- 可显示 shortcut

适用：

- 普通 menu item
- 普通 toolbar button
- context menu item

#### 2. Widget Action

Action 本体就是一个 toolbar item：

- 通过 `toolbar_view(context)` 提供 View
- 不依赖 `execute()` 触发
- 适合持续存在的 UI

典型场景：

- 搜索框
- 下拉选择器
- 数值输入
- 状态条/配置控件

设计判断：

- 这是本次必须覆盖的核心需求
- 不能被当成"未来另做"的边缘能力

#### 3. Dropdown / Split Action

动作入口在 toolbar，但展开一个 menu：

- `dropdown`：只有展开入口，不承担主执行
- `split`：主按钮执行 `execute()`，箭头部分展开 menu

展开内容来源有两种：

1. `menu_actions(context)` — 标准 action 列表
2. `menu_view(context)` — 复杂 UI

设计判断：

- split button 是一等能力，不应靠 presenter 自动猜测
- 同一个 Action 是否以 split 形式出现，应允许由 `ActionRef.variant` 控制

#### 4. Complex Menu View Action

入口是 Action，但展开菜单里不是简单 action list，而是复杂 UI：

- 一个可交互的配置面板
- 一个列表选择器
- 一个带按钮、说明文字、状态块的完整界面

实现方式：

- `menu_view(context)` 返回 `MenuView` 或普通 `View`
- `ActionMenu` 负责通过现有 Menu 机制承载它

### 为什么不引入 `ActionResult`

本次不定义 `ActionResult`。

原因：

1. 本次设计的重点不是"execute 返回一个打开界面的结果"，而是：
   - widget 型动作（toolbar 中嵌入 UI）
   - split button
   - dropdown 中承载复杂 UI
2. "打开窗口"等行为更多是业务副作用（如 `dialog.show()`、`show_settings(...)`），不要求框架层先抽象成统一返回值协议

因此本次的结论是：

- 命令型 Action 的业务副作用仍由 `execute()` 自己完成
- 呈现层复杂度主要通过 `toolbar_view()` / `menu_actions()` / `menu_view()` 建模

### Category 设计：可扩展性的根基

#### category 的语义

category 表示一个动作组合槽位，而不是组件类型。它回答的是：

- 哪些动作应该出现在这个区域
- 外部模块如何往这个区域追加动作
- 这个区域是否是中间组合节点，供 submenu/聚合动作继续向下分发

建议使用 `/` 分层路径，例如：

- `DockPanel/TabBar`
- `DockPanel/TabContext`
- `Inspector/Toolbar`
- `FileTree/Context`
- `DockPanel/TabBar/Layout`

#### 两类语义：surface 与 composition

只作为设计理解，不拆成两套类型：

1. **surface category**
   - 直接被 presenter 消费
   - 例如 `Inspector/Toolbar`
2. **composition category**
   - 主要作为组合节点，被 action dropdown / submenu 再次引用
   - 例如 `MainMenu/File/OpenRecent`

#### category 是开放协议

不做中心注册表，不做白名单。只要消费者使用某个 category，扩展方就可以往里面贡献动作。

#### 多 category 是一等能力

优先做法是：

1. 一个稳定的 Action
2. 声明多个 `display_category`
3. 必要时由 `ActionRef` 做局部显示覆盖

而不是为每个区域复制一份 Action。

### 动态 action 的发现与展开

动态 action 分成两层。

#### 一类：category 级动态实例

用于"某个区域当前有哪些动作实例"：

- 最近文件
- 当前可选模板
- 当前选择集相关操作

通过 `ActionCategoryProvider` 负责：

```python
class ActionCategoryProvider(mutobj.Declaration):
    display_category: str | tuple[str, ...] = ()

    @classmethod
    def refs(cls, context: ActionContext) -> list[ActionRef]:
        return []
```

职责：

- 面向 category 贡献一批动态 `ActionRef`
- 返回的是实例，不是新的 Action 类型

#### 二类：action 自身展开内容

用于"这个动作点开之后下面是什么"：

- `menu_actions(context)` → 标准 action 列表
- `menu_view(context)` → 复杂 UI

因此职责分工是：

- `ActionCategoryProvider`：决定一个 category 里有哪些实例
- `Action.menu_actions/menu_view`：决定一个动作展开后长什么样

### 注册与发现

采用 `mutobj.discover_subclasses(Action)` 与 `mutobj.discover_subclasses(ActionCategoryProvider)` 自动发现。

```python
class ActionRegistry:
    def get(self, action_ref: ActionRef | str | type[Action]) -> type[Action]: ...
    def query_category(self, category: str, context: ActionContext) -> list[ActionRef]: ...
    def resolve(self, refs: list[ActionRef], context: ActionContext) -> list[ResolvedAction]: ...
```

`query_category(category, context)`：

1. 刷新子类缓存
2. 收集所有 `display_category` 命中的静态 Action，转成隐式 `ActionRef`
3. 调用所有命中该 category 的 `ActionCategoryProvider.refs(context)`
4. 合并并按 `placement` 排序

`resolve(refs, context)`：

1. 解析 `ActionRef.action`
2. 合并类默认属性与 ref 覆盖
3. 计算 `visible / enabled / checked`
4. 按 surface 推导实际呈现形态
5. 生成 `ResolvedAction`

### 呈现层组件

#### ActionMenu

`ActionMenu` 是基于 `MenuView` 的高层封装。它支持：

- `actions: list[ActionRef]`
- `category: str`
- `categories: list[str]`

渲染规则：

1. 若动作本身是 widget 型（提供 `toolbar_view(context)`）且同时提供 `menu_view(context)`，则在 menu 中直接内嵌该 View
2. 否则若动作提供 `menu_view(context)` 或 `menu_actions(context)`，则渲染为 submenu
3. 否则渲染为普通 menu item

这意味着：

- toolbar 中需要 dropdown / split 的动作，在 menu 中会保持同样的信息层级，先表现为 submenu
- 若确实希望 menu 中直接内嵌展示，则应使用 widget 型 action（例如 toolbar 是 widget，menu 也直接展示对应 view）
- category/provider 展开结果会按 `ref_id` 去重，避免静态 category 与 provider 叠加时出现重复菜单项

#### ActionToolbar

`ActionToolbar` 是普通 View 组件，也支持：

- `actions`
- `category`
- `categories`
- `label_mode`

渲染规则：

1. `variant="widget"` 或动作提供 `toolbar_view(context)`  
   → 渲染为 widget item
2. `variant="split"`  
   → 渲染为 split button（主按钮执行 + 箭头展开）
3. `variant="dropdown"`  
   → 渲染为 dropdown button
4. 其他  
    → 普通按钮

`label_mode` 用于控制 toolbar 中按钮类 action 是否展示文字：

- `always`：有文字就显示（当前默认行为）
- `icon-only`：有图标时只显示图标；无图标 action 仍显示文字，避免按钮变空
- `auto`：当前等价于 `always`，为后续更紧凑或响应式策略预留

作用范围：

- 只影响 `ActionToolbar` 中的按钮类 action
- 不影响 `ActionMenu`
- 不影响 `toolbar_view()` 提供的 widget action
- split 的箭头按钮始终只显示箭头，不受 `label_mode` 影响

按钮类 action 在 toolbar 中的 `title` 采用：

- 优先使用 `tooltip`
- 若存在 `display_shortcut` / `shortcut`，则拼成 `"{title} ({shortcut})"`

这样在不实现快捷键分发的阶段，toolbar hover tip 与 menu shortcut 区域都能展示快捷键信息。

非目标：

- 本次不试图覆盖所有 toolbar 布局定制
- 但必须覆盖 `display_widget` / split / dropdown 这三类核心需求

### DockPanel 集成

`TabSetNode.actions` 升级为：

```python
actions: list[ActionRef] | None = None
```

DockPanel 的职责变为：

- 提供 `surface="dock-tabbar"`
- 提供 `payload`（active panel、tabset、selection 等）
- 在 tab bar 两端渲染 `ActionToolbar`

这使得 DockPanel 的动作不再局限于"小图标按钮"，而能自然接入：

- 普通按钮
- dropdown
- split
- widget item

### 快捷键方向：本次只保留兼容接口

这次不实现 ShortcutRegistry，但 Action 模型必须为未来保留接口。

保留点：

1. 稳定 `action_id`
2. `display_shortcut` 元数据
3. `execute()` 作为统一执行入口
4. `check_enabled/check_visible` 可被快捷键触发复用

为什么不在本次一并做：

- 真实业务已经出现 shortcut scope/冲突问题
- 需要单独设计：
  - 全局/局部 scope
  - 焦点优先级与输入框豁免
  - 冲突解决策略
  - chord 与平台差异
  - 前端 keyboard 捕获与后端分发

所以本次只保证 Action 设计**不堵死快捷键方向**。

## 消费者场景

| 消费者 | 场景 | 依赖输出 | 验收标准 |
|--------|------|---------|---------|
| DockPanel tab bar | tab 栏右上角动作、新建、布局入口 | `ActionToolbar` + `ActionRef` | 不再依赖 `ActionDef`，支持 button/dropdown/split |
| Console / Inspector toolbar | 搜索框、下拉框、状态控件 | `toolbar_view()` | toolbar 中可直接嵌入 View |
| Scene/Game toolbar | 主按钮执行 + 箭头展开配置菜单 | `variant="split"` + `menu_actions/menu_view` | split button 行为明确、无需 presenter 猜测 |
| 复杂 dropdown 菜单 | action 入口展开配置 UI、状态面板 | `menu_view()` | 菜单中可承载复杂 UI，不限于 action 列表 |
| context menu / header menu | category 扩展与动态实例 | `ActionCategoryProvider` + `ActionMenu` | 外部模块可无侵入追加动作 |
| 未来快捷键系统 | 键位触发 action | `action_id` + `display_shortcut` + `execute()` | 后续可单独设计 shortcut，而无需推翻 Action 模型 |

## 待定问题

无。当前已确认：

- 不引入 `ActionResult`
- 本次必须覆盖 widget action
- split button 是一等能力
- dropdown 中承载复杂 UI 是一等能力
- 本次不做运行时临时注入
- 本次不实现快捷键基础设施，只保留兼容方向

## 实施步骤清单

- [x] 实现 Action / ActionRef 的 `placement` 解析、排序与旧 `order` 兼容
- [x] 在 `ActionMenu` / `ActionToolbar` 中按 `group_name` 自动插入 divider / separator
- [x] 让 DockPanel tab bar action wire 透传分组信息，并按同一排序规则输出
- [x] 补充 placement 相关单元测试并同步更新 demo 与设计规范
- [x] 为 toolbar 增加 `label_mode`，支持 icon-only 与无图标兜底文字
- [x] 为 demo action 增加 shortcut 展示，并让 toolbar tip 与 menu shortcut 区域同步展示
- [x] 调整 `ActionMenu` 的 presenter 规则：dropdown/split 在 menu 中显示为 submenu，widget 型 action 才直接内联
- [x] 修复 category + provider 叠加时的重复 action，按 `ref_id` 去重

## 测试验证

- `python -m pytest tests\test_action.py tests\test_dock_panel.py tests\test_dock_panel_core.py tests\test_menu.py`
