# 菜单系统设计规范

**状态**：✅ 已完成
**日期**：2026-04-21
**类型**：功能设计

## 需求

1. mutgui 需要通用的菜单机制（右键菜单、下拉菜单、子菜单），作为框架级基础设施
2. 菜单融入 wire_tree 协议，不引入独立的 RPC 通道
3. mutbot 现有菜单系统（`menu.py` + `RpcMenu.tsx`）将重构到此机制上，mutgui 需覆盖其全部能力
4. 菜单内容不限于 MenuItem，可包含任意组件（如搜索框），支持持续交互

### mutbot 现有能力（需覆盖）

mutbot 菜单通过独立 RPC 协议实现（`menu.query` / `menu.execute`），具备：

- 静态菜单项（Menu Declaration 子类，mutobj 自动发现）
- 动态菜单项（`dynamic_items(context)` 运行时生成）
- 条件可见/启用（`check_visible(context)`, `check_enabled(context)`）
- 分组分隔线（order 格式 `"group:index"`）
- 子菜单（`submenu_category` hover 展开，一级）
- 图标、快捷键显示、禁用状态
- 前端直接处理动作（`client_action` 跳过 RPC）
- 执行结果动作（confirm 确认框、toast 提示、redirect 跳转）
- 上下文传递（前端发 context dict，后端据此过滤）

### 前置依赖

- `feature-framework-core.md` — 基础框架（View、ViewPort、wire_tree 协议）
- `refactor-event-system.md` — 事件系统（EventHandler、Callback、Bind、resolvePath）
- `feature-view-nesting.md` — View 嵌套（子 View 引用、ViewPort 树）

## 关键参考

### mutgui 现有实现

- `src/mutgui/events.py` — EventHandler / Callback / Bind，`to_wire()` 输出 `{"$handler": {...}}`
- `src/mutgui/view.py` — View Declaration，render() → wire_tree
- `src/mutgui/_view_impl.py` — deferred render（invalidate → 同 tick 下一 microtask render → push）
- `src/mutgui/viewport.py` — ViewPort，`$view` 引用 → 子 ViewPort 自动创建
- `frontend/src/renderer.tsx` — MutguiView 组件、processProps、createHandler
- `frontend/src/resolve-path.ts` — resolvePath 路径提取（`$0.target.value` 语法）
- `frontend/src/standalone.tsx` — App 入口，createConnection，全局 MutguiView
- `frontend/src/context.tsx` — ConnectionProvider / MutguiConnection / ViewPath

### mutbot 菜单实现（重构对象）

- `mutbot/src/mutbot/menu.py` — Menu Declaration 基类、MenuItem / MenuResult 数据类
- `mutbot/src/mutbot/runtime/menu_impl.py` — MenuRegistry，query/execute 逻辑
- `mutbot/src/mutbot/builtins/menus.py` — 38 个内置菜单定义
- `mutbot/src/mutbot/web/rpc_workspace.py` — MenuOps RPC handler
- `mutbot/frontend/src/components/RpcMenu.tsx` — 前端菜单渲染（dropdown / context 双模式）

## 设计方案

### 核心思路：MenuView 就是渲染在 portal 里的普通 View

菜单不需要特殊的框架机制。MenuView 是 View 子类，render() 输出菜单内容，走标准的 wire_tree 推送。唯一的特殊之处是前端将其渲染在 portal 浮层而非原位。

框架层提供三个新概念：
1. **MenuView** — View 子类，菜单内容的容器
2. **MenuTrigger** — EventHandler 子类，声明"此事件触发菜单"
3. **前端 Menu 组件** — portal 渲染 + 关闭检测 + 定位

### MenuView — 后端

MenuView 是 View 子类，render() 返回菜单内容（任意 wire_tree）：

```python
class MenuView(View):
    """菜单 View — render() 输出菜单内容。"""
    ...
```

MenuView 的 render 输出不限于 MenuItem。可以包含 Input（搜索框）、自定义组件等，支持持续交互（Bind 双向绑定、Callback 事件回调）。

visible/enabled 在 render() 里直接控制——不输出即不可见，`disabled` 属性即禁用。不需要 mutbot 那套 `check_visible` / `check_enabled` 单独机制。

#### 生命周期：按需创建，关闭销毁

MenuView 实例在菜单触发时创建，关闭时销毁：

```
触发 → 创建 MenuView 实例 → 挂到 View 树（获得 ViewPort）→ push 内容 → 显示
交互 → Bind/Callback 正常工作（如搜索框输入 → 过滤 → push 更新）
关闭 → 前端通知后端 → 销毁 MenuView 实例 → ViewPort 清理
```

这自然解决了 per-viewport 问题：每次触发创建独立实例，不同客户端的菜单互不干扰。

#### 用法示例

简单菜单：

```python
class TabContextMenu(MenuView):
    def __init__(self, session):
        self.session = session

    def render(self):
        return [
            {"$component": "mutgui.Menu.Item", "label": "Rename", "icon": "pencil",
             "shortcut": "F2", "onClick": Callback(self.on_rename)},
            {"$component": "mutgui.Menu.Divider"},
            {"$component": "mutgui.Menu.Item", "label": "Close", "icon": "x",
             "onClick": Callback(self.on_close)},
        ]
```

带搜索的菜单：

```python
class CommandMenu(MenuView):
    query = ""
    all_commands: list = []

    def render(self):
        filtered = [c for c in self.all_commands
                    if self.query.lower() in c.name.lower()]
        return [
            {"$component": "Input", "placeholder": "Search...",
             "value": self.query, "onChange": Bind(self, "query")},
            {"$component": "mutgui.Menu.Divider"},
            *[{"$component": "mutgui.Menu.Item", "label": c.name, "icon": c.icon,
               "onClick": Callback(self.on_select, c.id)}
              for c in filtered],
        ]
```

### MenuTrigger — 触发机制

MenuTrigger 是 EventHandler 子类（与 Callback、Bind 同级），声明"此事件触发弹出菜单"。复用现有的 `$handler` + resolvePath 机制。

```python
class MenuTrigger(EventHandler):
    """菜单触发器 — 告诉前端"此事件弹出菜单"。

    参数:
        menu_factory: 返回 MenuView 实例的工厂函数
        placement: 定位策略：
            'cursor'
            'top-start' | 'top-center' | 'top-end'
            'bottom-start' | 'bottom-center' | 'bottom-end'
            'left-start' | 'left-end'
            'right-start' | 'right-end'
        **context_extract: context 提取路径（resolvePath 语法）
    """

    def __init__(self, menu_factory, *, placement='cursor', **context_extract):
        self.menu_factory = menu_factory
        self.placement = placement
        self.extract = context_extract
```

#### wire 格式

MenuTrigger 复用 `$handler` 格式，通过 `$menu` 特殊 key 标识身份：

```python
def to_wire(self):
    wire = {k: v for k, v in self.extract.items()
            if not (isinstance(v, str) and v.startswith("@"))}
    wire["$menu"] = True
    if self.placement != 'cursor':
        wire["$placement"] = self.placement
    return {"$handler": wire}
```

输出示例：

```jsonc
// 右键菜单，从 DOM 提取 context
{"$handler": {"$menu": true, "item_id": "$0.target.dataset.itemId"}}

// 下拉菜单，无 context
{"$handler": {"$menu": true, "$placement": "bottom-start"}}

// 子菜单，定位在右侧
{"$handler": {"$menu": true, "$placement": "right-start"}}
```

前端看到 `$handler` 里有 `$menu` → 走菜单逻辑而非普通事件：
1. 用 resolvePath 提取非 `$` 开头字段作为 context（**完全复用现有逻辑**）
2. 阻止默认事件（如浏览器右键菜单）
3. 记住触发位置（鼠标坐标 / 触发元素 rect）
4. 发事件到后端（context 数据 + viewport_id）
5. 等待 MenuView push → 在记录位置渲染

#### 统一所有触发方式

三种菜单触发方式用同一个 MenuTrigger，只是挂在不同事件上：

```python
# 右键菜单
"onContextMenu": MenuTrigger(self.make_tab_menu, item_id="$0.target.dataset.id")

# 下拉按钮菜单
"onClick": MenuTrigger(self.make_add_menu, placement="bottom-start")

# 子菜单（hover 展开）
"onMouseEnter": MenuTrigger(self.make_submenu, placement="right-start")
```

#### 后端处理流程

MenuTrigger.handle() 在后端的处理：

1. 调用 menu_factory(context) 创建 MenuView 实例
2. 将 MenuView 挂到 View 树（作为子 View）
3. MenuView 获得 ViewPort → invalidate → deferred render → push
4. 前端收到 MenuView 的 wire_tree → 渲染菜单

### 前端实现

#### Menu 组件

前端注册一个 `Menu` 容器组件，负责：

- **Portal 渲染**：通过 `ReactDOM.createPortal` 渲染到 body 顶层（React 动态创建容器，无需 HTML 预写）
- **定位**：根据 `{side}-{align}` placement 决定锚点与菜单对齐角；`cursor` 仍表示鼠标点右下弹出
- **自动适配**：mount 时执行主轴 flip、交叉轴 shift 和 size 约束；后续尺寸变化只按锁定锚点重算位置，不重新 flip

#### 关闭检测

纯前端行为，document 级别事件监听（与 mutbot RpcMenu 现有方案一致）：

- `document.addEventListener("pointerdown", handler)` — 点击目标不在菜单内 → 关闭
- `document.addEventListener("keydown", handler)` — ESC → 关闭
- 子菜单：点击不在任何菜单内才关闭整棵树；ESC 关闭最深层子菜单

关闭时通知后端（发关闭事件），后端销毁 MenuView 实例、清理 ViewPort。

#### 菜单组件注册

与 DockPanel 一致，菜单组件注册在 `mutgui` 命名空间下：

```ts
registerComponents({
  __name__: 'mutgui',
  Menu,
  'Menu.Item': MenuItem,
  'Menu.Divider': MenuDivider,
});
```

| 组件 | wire_tree 名称 | 说明 |
|------|---------------|------|
| Menu | `mutgui.Menu` | 菜单容器（portal 渲染、关闭检测、定位） |
| Menu.Item | `mutgui.Menu.Item` | 菜单项（label, icon, shortcut, disabled, checked） |
| Menu.Divider | `mutgui.Menu.Divider` | 分隔线 |

`mutgui.Menu.Item` 点击后默认自动关闭整棵菜单树。如果菜单内包含非 Menu.Item 组件（Input、Toggle 等），点击不关闭——由 Menu.Item 组件自身控制关闭行为，而非框架全局判断。

#### 子菜单层叠

子菜单在同一个 portal 容器内平铺定位（不嵌套 portal）：

```html
<div id="menu-layer">          <!-- React 动态创建，portal 到 body -->
  <div class="menu" style="left:120px; top:200px">    <!-- 主菜单 -->
    <Menu.Item>Copy</Menu.Item>
    <Menu.Item class="active">New...</Menu.Item>        <!-- hover 状态 -->
  </div>
  <div class="menu" style="left:280px; top:220px">    <!-- 子菜单，平级 DOM -->
    <Menu.Item>Terminal</Menu.Item>
    <Menu.Item>Chat</Menu.Item>
  </div>
</div>
```

### 定位策略

| placement | 触发方式 | 定位基准 |
|-----------|---------|---------|
| `cursor` (默认) | contextmenu | 鼠标坐标 |
| `top-start` / `top-center` / `top-end` | click / submenu | 触发元素上边，分别左/中/右对齐 |
| `bottom-start` / `bottom-center` / `bottom-end` | click / dropdown | 触发元素下边，分别左/中/右对齐 |
| `left-start` / `left-end` | submenu / edge demo | 触发元素左边，上/下对齐 |
| `right-start` / `right-end` | submenu / edge demo | 触发元素右边，上/下对齐 |

所有定位均采用统一布局管线：

1. 主轴优先 flip 到空间更大的方向
2. 交叉轴用 shift 贴边（保留 4px margin）
3. 仍放不下时给出 `maxHeight` / `maxWidth`，由菜单内部滚动兜底
4. 菜单 mount 后内容尺寸变化时，只按锁定锚点重算位置，保证弹出角稳定
5. 菜单刚打开的一帧会临时抑制 `:hover` 高亮，直到用户第一次移动指针，避免点击/右键打开时首项被即时命中成 hover

### 时序

```
前端                              后端
──────────────────────────────────────────────
contextmenu/click 事件
  ├ 阻止默认行为
  ├ resolvePath 提取 context
  ├ 记住触发坐标/元素
  └ send({source, event, data: {$menu:true, ...context}})
                                  ──→ MenuTrigger.handle()
                                       ├ menu_factory(context) → MenuView
                                       ├ 挂到 View 树
                                       └ invalidate
                                      (同 tick deferred render)
                                       └ push wire_tree ──→
收到 MenuView render 消息
  └ 在记录坐标处 portal 渲染菜单
  
(交互中: Input onChange → Bind → invalidate → push 更新)

点击外部 / ESC
  ├ 前端关闭菜单
  └ send close 事件 ──→ 后端销毁 MenuView + ViewPort
```

### 本次范围

本次只实现 mutgui 框架层的菜单系统（MenuView、MenuTrigger、前端 Menu 组件、demo 验证）。mutbot 菜单重构为后续工作。

### 后续工作（不在本次范围）

- mutbot `CategoryMenuView` 封装（category + auto-discovery + dynamic_items）
- mutbot `RpcMenu.tsx` 迁移到 mutgui Menu 组件
- mutbot `client_action`、执行结果动作（confirm / toast / redirect）等业务层适配

## 实施步骤清单

- [x] 后端 MenuView + MenuTrigger 定义 — `src/mutgui/menu.py` 新建，MenuView(View) 声明类 + MenuTrigger(EventHandler) 声明类 + to_wire() 序列化
- [x] 后端 MenuTrigger.handle() 实现 — `src/mutgui/_menu_impl.py`，菜单创建、_overlay_children 注入机制、关闭事件处理和 MenuView 销毁
- [x] 前端 Menu / Menu.Item / Menu.Divider 组件 — `frontend/src/menu.tsx` 新建，Menu 使用 createPortal 渲染到 body，支持 placement 锚点模型、flip/shift/size 与 ResizeObserver 重算
- [x] 前端 $menu handler 识别 — 修改 `frontend/src/renderer.tsx`，createHandler 中识别 `$menu` 标记，走菜单触发逻辑（记住坐标、发事件、等 push、渲染）
- [x] 前端关闭检测 — document pointerdown + ESC 监听，关闭时发 `$close` 事件通知后端
- [x] 前端组件注册 — `frontend/src/standalone.tsx` 注册 mutgui.Menu / mutgui.Menu.Item / mutgui.Menu.Divider
- [x] Demo 验证 — `demo/examples/menu.py` 新建，覆盖：右键菜单、下拉按钮菜单、带搜索的命令面板、子菜单、disabled 状态
- [x] 菜单样式 — CSS 内联在 demo HTML 中（菜单容器、菜单项 hover/disabled、分隔线、快捷键、子菜单箭头）
- [x] 单元测试 — `tests/test_menu.py`，11 个测试覆盖 to_wire 序列化、id 唯一性、完整 trigger→render→click→close 流程、连续触发、@注入

## 实施记录

### 关键实现决策

**`_overlay_children` 注入机制**：`ViewRenderState` 加 `_overlay_children: dict[str|int, View]` 字段，`_render_and_cache` 在处理完 `render()` 输出后追加 overlay children 到 `_children` + `_wire_tree`。MenuView 作为子 View 自动获得 ViewPort，走标准 reconciliation。开发者的 `render()` 不需要感知菜单存在。

**菜单 ID 约定**：`MenuView.__init__` 自动生成 `$menu:<8位hex>` 格式 ID。前端 `MutguiView` 检测 `viewId` 以 `$menu:` 开头就用 `Menu` 容器包装并 portal 到 body。菜单走标准 wire_tree 协议，无需在 wire 上加额外标记。

**关闭事件路由**：前端发 `{source: [...menuPath, ''], event: '$close'}`，源路径末尾加空字符串使 `_route_event` 命中 MenuView 自身（component_id=""），EventFilter 拦截 `$close` 调用 `MenuView.close()`。

**`_close_filter` 共享单例**：所有 MenuView 共享一个 `_MenuCloseFilter` 实例（filter 无状态，用 `watched` 区分）。

### 文件清单

新增：
- `src/mutgui/menu.py` — MenuView + MenuTrigger 声明
- `src/mutgui/_menu_impl.py` — handle / close / EventFilter 实现
- `frontend/src/menu.tsx` — Menu / Menu.Item / Menu.Divider + 触发处理
- `demo/examples/menu.py` — Demo
- `tests/test_menu.py` — 11 个单元测试

修改：
- `src/mutgui/_view_impl.py` — `_overlay_children` 字段 + 注入
- `src/mutgui/__init__.py` — 导出 MenuView / MenuTrigger
- `frontend/src/renderer.tsx` — `$menu` handler 识别 + Menu 包装
- `frontend/src/standalone.tsx` — 组件注册

### 测试结果

- `pytest tests/`：140 passed（11 新增 + 129 既有）
- `tsc --noEmit`：通过
- `vite build`：通过，bundle 213.81 kB（gzip 67.42 kB）

