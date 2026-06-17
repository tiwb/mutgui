# ActionToolbar 前端组件化重构

**状态**：✅ 已完成
**日期**：2026-06-17
**类型**：重构

## 需求

1. ActionToolbar 当前在 Python 端用 `html.div` / `html.button` / `html.span` + 内联 CSS 拼装 UI，导致 Python 核心实现依赖 `html` namespace
2. Menu 已使用 `mutgui.Menu.Item` / `mutgui.Menu.Divider` 前端组件，ActionToolbar 应与之一致
3. 当前 Python 端内联 CSS 缺失 hover、active、focus-visible、transition 等交互态，暗色模式适配不完整
4. 样式分散在 Python 和前端两侧，调整样式需要改 Python 代码，迭代效率低

## 关键参考

- `src/mutgui/action.py` — Action / ActionRef / ActionToolbar / ActionMenu 声明
- `src/mutgui/_action_impl.py` — ActionToolbar render 实现，含所有 HTML + 内联 CSS 逻辑
- `src/mutgui/_action_registry.py` — ResolvedAction 解析引擎
- `src/mutgui/_menu_impl.py` — Menu 实现（参照目标架构）
- `src/mutgui/menu.py` — MenuView / MenuTrigger 声明
- `frontend/src/components/menu.tsx` — Menu 前端组件实现（参照目标模式）
- `frontend/src/core.tsx` — `registerComponents` 注册入口
- `frontend/src/core/registry.ts` — 组件解析器，含 `registerComponents` / `registerNamespace`
- `frontend/src/integrations/html.ts` — `html` namespace 注册（`registerNamespace('html', (key) => key)`）
- `frontend/src/core/renderer.tsx` — renderTree，负责将 wire tree 转换为 React 组件树

## 设计方案

### 总体思路

参照 Menu 的 `mutgui.Menu.Item` / `mutgui.Menu.Divider` 模式，将 ActionToolbar 的 UI 渲染职责从前端移到前端组件。Python 端 `render()` 只输出结构描述（props），前端组件负责样式、交互态、无障碍。

### 前端组件注册

新增 5 个内置组件到 `mutgui.*` namespace：

| 组件 | 用途 | 替换的 html.* |
|------|------|--------------|
| `mutgui.Toolbar` | 整体容器（start/spacer/end 三栏布局） | `html.div` |
| `mutgui.Toolbar.Button` | 按钮（图标+文字+tooltip+checked+disabled） | `html.button` + `html.span` |
| `mutgui.Toolbar.SplitButton` | 分离按钮（主动作 + 下拉箭头） | 两个 `html.button` 紧挨 |
| `mutgui.Toolbar.Dropdown` | 纯下拉按钮 | `html.button`（showArrow=true） |
| `mutgui.Toolbar.Divider` | 分组分隔线 | `html.div`（1px 竖线） |

### 组件 Props 设计

#### mutgui.Toolbar

```
gap: int           — 按钮间距（px），默认 6
wrap: bool         — start/end 组是否换行，默认 true
$children          — 按 position 分组的子项（Python 负责分组为 start/end 两段）
```

布局：水平 flex，`width: 100%`，`align-items: center`，start 和 end 组之间由 flex spacer（`flex: 1`）撑开。按钮间无分隔线；分隔线只出现在不同 `group_name` 之间。

#### mutgui.Toolbar.Button

核心组件，同时作为 SplitButton/Dropdown 的内部单元：

```
label: str              — 按钮文字
icon: str | null        — 图标（emoji/Unicode）
tooltip: str | null     — 悬停提示
shortcut: str | null    — 快捷键
disabled: bool          — 禁用态，默认 false
checked: bool           — 选中高亮态，默认 false
labelMode: "always" | "icon-only"  — 文字显示策略，默认 "always"
showArrow: bool         — 是否显示下拉箭头，默认 false
arrow: str              — 箭头符号，默认 "▾"
leftRounded: bool       — 右半圆角控制（SplitButton），默认 true
rightRounded: bool      — 右半圆角控制（SplitButton），默认 true
onClick: EventHandler   — 点击回调
```

**样式**（前端组件内部）：
- 尺寸：`height: 32px`，`padding: 0 10px`，`gap: 6px`
- 边框：`1px solid var(--mutgui-border)`
- 默认背景：`var(--mutgui-bg)`
- checked 背景：`color-mix(in oklch, var(--mutgui-accent) 22%, var(--mutgui-bg))`
- 圆角：默认 `6px`，由 leftRounded/rightRounded 控制 SplitButton 场景的半边圆角

**交互态**（前端组件内部，当前 Python 实现缺失）：
- hover：背景 `color-mix(in oklch, var(--mutgui-accent) 8%, var(--mutgui-bg))`
- active：背景 `color-mix(in oklch, var(--mutgui-accent) 12%, var(--mutgui-bg))`
- disabled：`opacity: 0.4`，`cursor: not-allowed`
- focus-visible：outline ring（键盘无障碍）
- transition：背景色 `150ms` 过渡

**labelMode 三种模式**：

```
"always":     [icon] [label]  /  [label]（无图标时）
"icon-only":  [icon]          /  [label]（无图标时回退到文字）
"auto":       保留，语义同 "always"，后续扩展用
```

**tooltip**（`title` 属性）：
- 有 tooltip + shortcut：`{tooltip} ({shortcut})`
- 仅 tooltip：`{tooltip}`
- 仅 shortcut：`{shortcut}`
- 都没有：不设 title

#### mutgui.Toolbar.SplitButton

```
label / icon / tooltip / shortcut / disabled / checked / labelMode / leftRounded / rightRounded
    — 同 Button，传给主按钮
mainOnClick: EventHandler     — 主按钮点击（Callback(execute)）
menuOnClick: EventHandler     — 箭头按钮点击（MenuTrigger）
menuPlacement: string         — 菜单弹出方向，用于决定箭头符号
```

布局：两个 Button 紧挨（`align-items: stretch`，容器 `display: inline-flex`），无间隙：
- 主按钮：leftRounded=true, rightRounded=false，disabled 跟随 action
- 箭头按钮：leftRounded=false, rightRounded=true，始终 enabled，仅显示箭头符号

#### mutgui.Toolbar.Dropdown

```
    — 同 Button 的展示属性
onClick: EventHandler  — MenuTrigger（始终）
showArrow: true        — 始终显示箭头
```

本质是 Button 的 `showArrow=true + onClick=MenuTrigger` 特化。

#### mutgui.Toolbar.Divider

无 props，纯视觉元素：`width: 1px; height: 20px; background: var(--mutgui-border); align-self: center`。

### Python 端 render() 输出变化

以按钮为例，当前 vs 重构后：

```python
# 当前：手写 html.* + 内联 CSS
{"$component": "html.button", "$id": "button-0",
 "type": "button", "disabled": True,
 "title": "运行 (F5)",
 "style": {"display": "inline-flex", "alignItems": "center",
           "gap": "6px", "height": "32px", "padding": "0 10px",
           "border": "1px solid var(--mutgui-border)", ...},
 "$children": [{"$component": "html.span", "$id": "icon",
                "children": "▶"},
               {"$component": "html.span", "$id": "label",
                "children": "运行"}]}

# 重构后：用 mutgui.Toolbar.Button
{"$component": "mutgui.Toolbar.Button", "$id": "button-0",
 "label": "运行", "icon": "▶",
 "tooltip": "运行当前命令", "shortcut": "F5",
 "disabled": False, "checked": False,
 "labelMode": "always",
 "onClick": Callback(item.action.execute, context)}
```

不再有 `style` dict、`$children` 包含 `html.span` 等模式。

### widget variant 处理

`variant == "widget"` 且 `toolbar_view` 返回 View 时，Python 输出：

```python
{"$component": "mutgui.Toolbar.Widget", "$id": f"widget-{index}",
 "title": item.tooltip,
 "$children": [widget_view]}
```

等待定问题 Q1 确认是否保留为独立组件。

### 注册方式

参照 Menu/MenuItem/MenuDivider 模式，在 `frontend/src/core.tsx` 中：

```ts
import { Toolbar, ToolbarButton, ToolbarSplitButton,
         ToolbarDropdown, ToolbarDivider } from './components/toolbar';

registerComponents({
  __name__: 'mutgui',
  // ... 现有组件 ...
  Toolbar,
  'Toolbar.Button': ToolbarButton,
  'Toolbar.SplitButton': ToolbarSplitButton,
  'Toolbar.Dropdown': ToolbarDropdown,
  'Toolbar.Divider': ToolbarDivider,
  // 如有 ToolbarWidget，在此注册
});
```

### 文件规划

| 文件 | 操作 |
|------|------|
| `frontend/src/components/toolbar.tsx` | 新建 — Toolbar 全部前端组件 |
| `frontend/src/components/toolbar.css` | 新建 — 样式文件（或合并到 core.css） |
| `frontend/src/core.tsx` | 修改 — 注册 Toolbar 组件 |
| `src/mutgui/_action_impl.py` | 修改 — render 输出改为 mutgui.Toolbar.* |
| `src/mutgui/action.py` | 不改 — ActionToolbar 声明不变 |

## 已确认决策

### widget variant 处理
不抽独立前端组件。widget 容器的样式极简（仅 `inline-flex` + `minHeight`），和 View 自身的样式强相关。直接让 View 作为 Toolbar 的子项（`$view` 协议），Python 侧用简单的 `html.div` 包装加 title，后续如有统一包装需求再抽独立组件。

### SplitButton 箭头禁用策略
保持当前行为：主按钮 disabled 时箭头按钮始终 enabled。与 VS Code、JetBrains 等编辑器惯例一致，确保菜单始终可访问。

### CSS 文件组织
独立 `toolbar.css`，在 manifest.json 的 css 列表中追加。

## 实施步骤清单

- [x] 创建 `frontend/src/components/toolbar.tsx` — Toolbar/ToolbarButton/ToolbarSplitButton/ToolbarDropdown/ToolbarDivider React 组件
- [x] 创建 `frontend/src/components/toolbar.css` — Toolbar 组件样式（含 hover/active/disabled/checked/focus-visible 交互态）
- [x] 修改 `frontend/src/core.tsx` — 注册 Toolbar 组件到 mutgui namespace，导出组件类型
- [x] 修改 `frontend/src/index.css` — 导入 toolbar.css
- [x] 修改 `src/mutgui/_action_impl.py` — render 输出改为 mutgui.Toolbar.* 组件，移除内联 CSS 和 html.* 依赖
- [x] 更新 `tests/test_action.py` — 适配新组件 props 结构
- [x] 前端构建并验证
