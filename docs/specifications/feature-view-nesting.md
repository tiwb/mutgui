# View 嵌套设计规范

**状态**：✅ 已完成
**日期**：2026-04-17
**类型**：功能设计

## 需求

1. 复杂 UI（编辑器）由多个面板组成，不可能每次同步完整的编辑器视图下所有控件
2. 需要独立更新单元——面板 A 的值变化只影响面板 A，不触及菜单栏和其他面板
3. VirtualList 的每个 item 需要独立更新和独立的事件作用域
4. 嵌套结构中组件 ID 会重复（多个 item 都有 `id="value"` 的 InputNumber），需要 ID 隔离机制
5. 为 VirtualList、TreeView、Panel 等上层组件提供统一的框架基础

### 前置依赖

- `feature-framework-core.md` — 基础框架（协议、事件模型、`$component`、`$` 标签、View/ViewSession）

### 后续文档

- `feature-virtual-list.md` — VirtualList 组件（依赖本文档的 View 嵌套机制）

## 关键参考

### 内部实现

- `mutgui/docs/specifications/feature-framework-core.md` — 基础框架设计（`$component`、`$` 标签、事件模型、View/ViewSession）
- `mutgui/docs/explorations/2026-04-17-server-driven-ui-frameworks-reference.md` — server-driven UI 框架对比（LiveView、Blazor、Vaadin、NiceGUI）

### 外部参考

- **Phoenix LiveView Stateful Component** — 架构最接近的参考。每个 `live_component` 有独立 state/render/event handler，通过 `id` 建立作用域，`phx-target={@myself}` 限定事件路由
- **Blazor Server Component** — `StateHasChanged()` 只触发当前组件重渲染；`@key` 驱动组件复用
- **Vaadin** — 所有 UI 组件是后端 Java 对象，属性级 dirty tracking + 批量推送

## 设计方案

### View 的定义

**View 是 mutgui 的独立更新单元**，三个职责合一：

1. **独立状态** — 后端 Python 对象，持有自己的数据和逻辑
2. **独立渲染** — 有自己的 `render()`，产出组件树，独立推送给前端
3. **独立作用域** — 内部组件的 ID 不与外部冲突，事件自动路由到正确的 View

View 可以嵌套 View，形成树形结构。每个 View 是一个作用域边界。

与基础控件的区别：基础控件（InputNumber、Button 等）是纯 JSON 描述，无后端状态。View 是有状态的后端对象，有自己的渲染周期和事件处理。

### 编辑器场景示例

```
EditorView（View）
├── MenuBar（View）—— 菜单独立更新
├── PropertyPanel（View）—— 属性面板独立更新
│   └── VirtualList（View）
│       ├── Item 0（View）—— 每个 item 独立更新
│       ├── Item 1（View）
│       └── ...
└── Viewport3D（View）—— 3D 视口独立更新
```

改了属性面板里一个值 → 只推送那个 item View 的更新。菜单栏、3D 视口、其他 item 完全不动。

### 协议扩展

在 framework-core 的 `$` 命名空间中新增 `$view` 和 `$id`，修订 `$children` 的语义。

#### `$` 命名空间约定（完整）

| 字段 | 用途 | 透传给 React 组件？ |
|------|------|------|
| `$component` | 组件类型标识 | 否（用于 registry 查找） |
| `$view` | View 边界标识 | 否（前端创建 MutguiView） |
| `$id` | 框架身份标识（事件路由、React key） | 否 |
| `$children` | 嵌套组件树（框架递归渲染） | 渲染为 React children |
| `$` (handler) | 事件处理器标记 | 转换为函数 |
| 其余键 | 组件 props | 是，全部透传 |

**统一规则**：`$` 前缀的键 = 框架消费，不透传。无前缀的键 = 组件 props，全部透传。

#### `$id` —— 框架身份标识

替代 framework-core 中 `id` 的双重用途。`$id` 是纯框架概念：

- 事件路由：作为事件 source 数组的一段
- React key：驱动组件 reconciliation
- 定向更新：后端按 `$id` 路由更新到特定组件

**不渲染为 HTML `id` 属性**。在 View 嵌套场景下，多个 item 内部组件有相同的 `$id`（如 `"value"`），如果渲染为 HTML id 会违反唯一性约束。

如果组件需要 HTML id 属性（无障碍场景等），使用无前缀的 `id`（普通 prop，透传）。

**有 handler 必须有 `$id`**：组件如果声明了事件 handler（`$` 标记），就必须有 `$id`。事件 source 数组的末段是组件的 `$id`，没有 `$id` 则无法路由事件。框架层面校验此约束。

#### `$children` —— 嵌套组件树

替代 framework-core 中 `children` 对数组的特殊处理。语义明确：

- `$children`：数组，框架递归渲染为 React 组件树
- `children`：普通 prop，透传（文本、数字等原始值）

```json
{"$component": "Form", "$children": [
    {"$component": "Input", "$id": "name", "value": "hello"}
]}

{"$component": "Button", "children": "Save"}
{"$component": "Text", "children": 42}
```

渲染器不再需要检查 `children` 是否为数组来决定是否递归。`$children` = 一定递归，`children` = 一定透传。

#### `$view` —— View 边界

标记一个节点是 View 的前端入口。前端看到 `$view` 就创建 `MutguiView` 实例。

**`$view` 与 `viewId` 的区别**：

- **树节点中的 `$view`**：单个段（string 或 int），是 View 的 local id，只在同级 View 中唯一
- **消息中的 `viewId`**：数组，是从根 View 到目标 View 的完整路径，每段对应一层 MutguiView

View 本身只知道自己的 local id，不知道自己在树中的位置。完整路径由框架（ViewSession）在发送消息时组装。

```json
{"$view": "properties", "$component": "VirtualList", "itemCount": 5000}
```

- `$view` 的值是 View 的 local id
- 可以与 `$component` 共存 — 表示"这个 View 用特定组件渲染容器"（如 VirtualList）
- 没有 `$component` 时 — 用默认容器（div 或 fragment）渲染

```json
{"$view": "menu", "$children": [
    {"$component": "Button", "$id": "file", "children": "File"},
    {"$component": "Button", "$id": "edit", "children": "Edit"}
]}
```

**数字 id**：VirtualList 等列表场景中，item View 的 `$view` 可以是数字（索引）：

```json
{"$view": 0, "$component": "ListItem"}
{"$view": 1, "$component": "ListItem"}
```

#### 事件格式扩展

事件的 `source` 使用数组格式，每段是一个 View 的 local id 或组件的 `$id`，由 View 层级自动拼接：

```json
{"source": ["properties", "prop_opacity", "value"], "event": "onChange", "data": {"value": 0.65}}
```

数组结构：`[View_id, 子View_id, ..., 组件$id]`

- 每段的类型可以是 string 或 int（VirtualList item 用数字索引）
- 后端框架逐段解析，逐层路由到对应的 View，最终到达组件
- 前端通过 ScopeProvider（React Context）逐层叠加段，组件发事件时收集完整数组

数字索引示例：

```json
{"source": ["properties", 2, "value"], "event": "onChange", "data": {"value": 0.65}}
```

### 后端设计

#### View 基类（扩展 framework-core 的 View）

```python
class View:
    id: str | int  # local id，只在同级 View 中唯一。View 不知道自己在树中的位置。

    def render(self) -> list[dict] | dict:
        """声明当前 UI。返回组件描述，可包含子 View 实例。"""
        return []

    def on_event(self, event: dict) -> None:
        """处理未被 handler/bind 捕获的事件。"""
        pass

    def invalidate(self):
        """标记需要重新 render，合并到下一次推送。"""
        ...
```

#### View 嵌套用法

View 实例直接出现在 `render()` 的返回值中。ViewSession 处理 render 树时识别 View 实例，转换为协议中的 `$view` 节点。

```python
class EditorView(View):
    def __init__(self, doc):
        self.menu = MenuBar()
        self.props = PropertyPanel(doc)
        self.viewport = Viewport3D(doc)

    def render(self):
        return [
            self.menu,     # View 实例 → 框架转为 {"$view": "menu", ...}
            self.props,    # View 实例 → 框架转为 {"$view": "props", ...}
            self.viewport, # View 实例 → 框架转为 {"$view": "viewport", ...}
        ]

class MenuBar(View):
    id = "menu"  # 开发者指定 local id（业务含义，便于调试）

    def render(self):
        return [
            {"$component": "Button", "$id": "file", "children": "File",
             "onClick": handler(self.on_file)},
            {"$component": "Button", "$id": "edit", "children": "Edit",
             "onClick": handler(self.on_edit)},
        ]
```

#### View 在组件 `$children` 中

View 可以出现在 Ant Design 等容器组件的 `$children` 里。Component 和 View 是正交的——Component 是视觉容器，View 是独立更新单元。

```python
class EditorView(View):
    def __init__(self, doc):
        self.prop_panel = PropertyPanel(doc)
        self.material_panel = MaterialPanel(doc)

    def render(self):
        return {"$component": "Tabs", "$children": [
            {"$component": "Tabs.TabPane", "key": "props", "tab": "属性",
             "$children": [self.prop_panel]},
            {"$component": "Tabs.TabPane", "key": "mat", "tab": "材质",
             "$children": [self.material_panel]},
        ]}
```

协议上 Tabs 组件不知道 View 的存在，它的 `$children` 里出现了 `$view` 节点，前端渲染器处理。

#### ViewSession 扩展

ViewSession 管理 View 树。每个 View 有独立的 render → serialize → send 循环。

核心变化：
- `_process_tree()` 识别 render 树中的 View 实例，转换为 `$view` 协议节点
- 为每个子 View 建立独立的 ViewSession（递归）
- **路径组装**：ViewSession 维护 View 树结构，发送 render 消息时组装完整 `viewId` 数组路径（View 本身只有 local id）
- 事件按 source 数组逐段路由到对应的 View
- 子 View 的 `invalidate()` 只触发自身的 re-render 和推送，不影响父 View

#### 脏标记合并刷新

多次 `invalidate()` 合并为一次推送：

```python
view.invalidate()  # 标记 dirty
view.invalidate()  # 再次标记，不会多推
# → 下一次 flush 时，只 render + push 一次
```

### 前端设计

#### MutguiView —— View 在前端的对应物

每个后端 View 在前端对应一个 `MutguiView` React 组件实例。职责：

1. **持有 tree state** — 从后端接收这个 View 的 render 结果
2. **提供事件作用域** — 通过 React Context 给内部事件 source 加上路径前缀
3. **渲染** — 用 `renderTree` 渲染自己的组件树

```tsx
function MutguiView({ viewId, ws }) {
  const [tree, setTree] = useState([]);
  const parentScope = useScope();  // 从 Context 获取父级 scope 数组
  const fullPath = [...parentScope, viewId];  // 拼接完整路径

  // 监听后端针对这个 View 的更新（按完整路径数组匹配）
  useEffect(() => {
    const handler = (msg) => {
      if (msg.type === 'render' && arrayEquals(msg.viewId, fullPath)) {
        setTree(msg.tree);
      }
    };
    ws.addEventListener('message', handler);
    return () => ws.removeEventListener('message', handler);
  }, [viewId, ws]);

  return (
    <ScopeProvider scope={fullPath}>
      {renderTree(tree, ws)}
    </ScopeProvider>
  );
}
```

**ScopeProvider** 通过 React Context 提供当前 View 的完整路径数组。内部组件发送事件时，从 Context 取出路径数组，追加自己的 `$id` 作为末段，构成完整的 source 数组。

**动态增删**：父 View re-render 时 `$view` 节点可能出现或消失（条件渲染）。处理方式与 React 组件一致——`$view` 出现在新 tree 中 → 挂载 MutguiView；`$view` 消失 → 卸载。以 `$view` 值作为 React key，reconciliation 自然处理。

#### renderTree —— 纯渲染函数

遍历 JSON 组件树，生成 React 元素。遇到 `$view` 节点时创建 `MutguiView`（递归）。

```tsx
function renderTree(tree: any[], ws: WebSocket): React.ReactNode[] {
  return tree.map(schema => {
    // $view 节点 → 创建独立的 MutguiView（递归）
    if (schema.$view) {
      const Component = schema.$component
        ? registry.get(schema.$component)
        : undefined;
      return (
        <MutguiView key={schema.$view} viewId={schema.$view} ws={ws}>
          {Component && <Component {...extractProps(schema)} />}
        </MutguiView>
      );
    }

    // 普通组件节点 → 查 registry 渲染
    const Component = registry.get(schema.$component);
    if (!Component) return <UnknownComponent key={schema.$id} />;
    const props = processProps(schema, ws);
    return <Component key={schema.$id} {...props} />;
  });
}
```

`processProps` 处理逻辑（扩展 framework-core）：
- `$component`、`$view`、`$id`：不透传
- `$children`：递归调用 `renderTree`，结果作为 React `children` prop
- `$` handler：转换为事件函数（同 framework-core，但 source 从 scope Context 取数组路径 + 追加组件 `$id`）
- 其余：全部透传

#### MutguiView 与 MutguiRenderer（framework-core）的关系

framework-core 中的 `MutguiRenderer` 是 v1 的无状态渲染函数。引入 View 嵌套后，自然演进为：

- `MutguiView`：有状态的 View 渲染组件（持有 tree state + scope）
- `renderTree`：无状态的纯渲染函数（遍历树、创建组件）

根级的 `MutguiView`（root View）取代了 v1 中外层 App 组件管理 tree state + 调用 MutguiRenderer 的模式。

#### 前端整体架构（递归）

```
MutguiView (root, viewId=[])             ← EditorView
├── renderTree 渲染 Text, Button...      ← 普通组件
├── MutguiView ("menu")                  ← MenuBar
│   └── renderTree 渲染 Button...
├── MutguiView ("props")                 ← PropertyPanel
│   └── renderTree 渲染 VirtualList 组件
│       ├── MutguiView (0)               ← item View（数字索引）
│       │   └── renderTree 渲染 Text, InputNumber
│       └── MutguiView (1)               ← item View
│           └── renderTree 渲染 Text, InputNumber
└── MutguiView ("viewport")              ← Viewport3D
    └── renderTree 渲染 Canvas...
```

后端一个 View = 前端一个 MutguiView。一一对应。

### 消息协议

#### 下行消息（Backend → Frontend）

**全量渲染（针对特定 View）**：

```json
{"type": "render", "viewId": ["properties", "prop_opacity"], "tree": [
    {"$component": "Text", "$id": "label", "children": "Opacity"},
    {"$component": "InputNumber", "$id": "value", "value": 0.8,
     "onChange": {"$": "handler", "extract": {"value": "$0"}}}
]}
```

- `viewId` 使用数组格式，是从根 View 到目标 View 的完整路径
- 每段对应一层 MutguiView 嵌套，类型可以是 string 或 int
- 前端按 `viewId` 找到对应的 MutguiView，更新其 tree state
- 根 View 的 `viewId` 为空数组 `[]`
- **推送顺序**：初始化时先推父 View（建立 `$view` 挂载点），再推子 View。批量推送时保证父在前子在后的顺序（前端收到子 View 的 render 时，对应的 MutguiView 已挂载）

**VirtualList 场景（数字索引）**：

```json
{"type": "render", "viewId": ["properties", 2], "tree": [
    {"$component": "Text", "$id": "label", "children": "Opacity"},
    {"$component": "InputNumber", "$id": "value", "value": 0.8,
     "onChange": {"$": "handler", "extract": {"value": "$0"}}}
]}
```

**父 View 的渲染（包含 $view 引用）**：

```json
{"type": "render", "viewId": [], "tree": [
    {"$component": "Text", "children": "Editor"},
    {"$view": "menu"},
    {"$view": "props", "$component": "VirtualList", "itemCount": 5000},
    {"$view": "viewport"}
]}
```

子 View 的具体内容不在父 View 的 tree 中，各自独立推送。

#### 上行消息（Frontend → Backend）

事件格式不变，source 数组自动由 scope 层级拼接：

```json
{"source": ["props", "prop_opacity", "value"], "event": "onChange", "data": {"value": 0.65}}
```

数字索引示例：

```json
{"source": ["props", 2, "value"], "event": "onChange", "data": {"value": 0.65}}
```

后端逐段路由：`"props"` → `2` → `"value"`。

### 与 framework-core 的兼容性

View 嵌套是 framework-core 的扩展，不是替代。向后兼容：

- 单 View 应用（v1 模式）继续工作 — 只有一个根 View，无嵌套
- `$component`、`$` handler 等协议不变
- `id` 已替换为 `$id`，`children` 数组已替换为 `$children`（v1 用法不再支持）

## 实施步骤清单

### 后端 — $id / $children 协议迁移

- [x] ViewSession._process_node 支持 `$id`（用于 callback 注册键）和 `$children`（递归处理），直接替换 v1 的 `id` / `children`

### 后端 — View 嵌套核心

- [x] View 基类添加 `id: str | int` 属性
- [x] ViewSession._process_items 识别 render 树中的 View 实例，转换为 `$view` 协议节点
- [x] ViewSession 为嵌套 View 创建和管理子 ViewSession（递归）
- [x] ViewSession 组装完整 viewId 数组路径，render 消息包含 viewId 字段
- [x] 初始化推送顺序：父 View 先推，子 View 后推（_flush_tree）

### 后端 — 事件路由

- [x] handle_event 支持 source 数组格式，逐段路由到对应 View 的 ViewSession

### 后端 — invalidate 机制

- [x] View.invalidate() 标记脏，ViewSession 合并多次 invalidate 为一次 render + push
- [x] 子 View invalidate 只触发自身 re-render，不触发父 View

### 前端 — ScopeProvider + MutguiView

- [x] 实现 ScopeContext / useScope（React Context，管理 viewId 路径数组）
- [x] 实现 MutguiView 组件（持有 tree state，按 viewId 数组匹配消息更新）

### 前端 — renderTree + processProps

- [x] 从 MutguiRenderer 重构为 renderTree 纯函数，遇到 `$view` 节点创建 MutguiView
- [x] processProps 支持 `$id`（不透传，用作 React key 和 source）、`$children`（递归渲染）
- [x] createHandler 使用 scope context 构建 source 数组（追加组件 `$id`）

### 前端 — 入口

- [x] standalone.tsx 使用 MutguiView + ConnectionProvider 替代旧的 tree state 管理

### 测试

- [x] 后端：嵌套 View render 产出正确协议（`$view` 节点、viewId 数组）
- [x] 后端：事件 source 数组路由到正确的 View handler（含三层深嵌套）
- [x] 后端：invalidate 合并（连续多次 → 一次 push）
- [x] 后端：子 View invalidate 不触发父 View render
- [x] 后端：`$id` / `$children` 在 session 和 nesting 测试中全覆盖
- [x] 验证：demo 在浏览器中可正常运行

### Demo

- [x] demo/app.py 迁移到 `$id` / `$children` 协议
- [x] demo/app.py 改为嵌套 View 演示（RootView + ProfileView + SubscriptionView 并排，带 render 计数器）

### 遗留问题

- [ ] 校验：有 handler 的组件必须有 `$id`（从事件路由章节移入）
- View._session 是 1:1 引用，不支持多 Session 共享同一 View。当前 demo 用 `push()` 暴力全量重渲染绕过，需要独立设计多 Session 通信机制 → 见 `feature-session-sharing.md`
