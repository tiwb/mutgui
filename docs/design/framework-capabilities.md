# mutgui 框架能力参考

> 用 mutgui 构建应用前，先阅读本文档了解框架已有能力。

## 框架定位

后端驱动的 React UI 框架。Python 定义 UI 树和状态，前端纯渲染。适合后端逻辑主导、前端展示为辅的应用场景。

## 渲染模型

**数据流**：`View.render()` → ViewBlock（组件字典列表） → JSON 序列化 → WebSocket → React 渲染

**组件字典格式**（`$` 前缀为框架保留键，其余透传为组件 props）：

| 键 | 说明 |
|---|---|
| `$component` | 组件名，通过解析链查找 React 组件 |
| `$id` | 组件标识，用于事件路由和 React key |
| `$children` | 子组件数组，递归渲染 |
| `$view` | View 边界标记，前端创建独立的 MutguiView 订阅 |
| `$handler` | 事件处理器标记，前端转换为回调函数 |

**去重渲染**：`invalidate()` 设置 dirty 标志并通过 `asyncio.call_soon()` 调度延迟渲染。同一事件循环 tick 内多次 `invalidate()` 只触发一次渲染。

## 事件系统

### 事件类型

- **Bind**：双向绑定。前端值变更 → `setattr(obj, attr, value)` → 自动 `invalidate()`
- **Callback**：单向回调。调用 Python 函数，支持 `$args`（位置参数）和命名参数提取，支持 `@event.xxx`、`@view` 等后端注入

### 源路径路由

事件携带源路径数组 `["parent_id", "child_id", ..., "component_$id"]`，框架沿路径逐级下发到嵌套 View，最后一段定位到组件的 EventHandler。

### Handler 协议格式

```json
{"$handler": {"$args": ["$0"], "name": "$0.target.value"}}
```

前端通过 `resolvePath()` 从事件参数中提取值，封装为 `{source, event, data}` 发回后端。

### EventFilter

观察者模式的事件拦截器，在 `on_event()` 之前执行，返回 `True` 表示已消费。

## 命令系统

### 协议形态

Command 是 Event 的下行对偶：后端业务逻辑显式触发前端副作用。

```json
{"type": "command", "viewId": ["child"], "name": "mutgui.redirect", "args": {"url": "..."}}
```

- `type`：固定为 `"command"`，与 `"render"` 平级
- `viewId`：目标 ViewPort 路径，当前实现按 ViewPort 作用域路由
- `name`：`namespace.command` 形式，走前端命令注册表解析
- `args`：后端预求值后的纯 JSON 参数

### 后端 API

- `await viewport.send_command(name, **args)`：直接向当前 ViewPort 发送 command
- `view.viewport`：当前事件上下文对应的 ViewPort
- `await view.send_command(name, **args)`：View 侧薄包装，等价于 `await view.viewport.send_command(...)`

Command 是 **fire-and-forget**：不返回值，不进入 render cache。

### 前端 API

- `registerCommands(source)`：注册命令源，后注册优先
- `resolveCommand(name)`：按与组件解析链一致的命名空间规则解析命令
- `window.MutguiApp.registerCommands(...)`：standalone 全局注册入口

当前 core 内置 `mutgui.redirect({ url, replace? })`，用于整页跳转。

### 不重放语义

- render 消息会在 ViewPort 初始化/重连时按最新树重放
- command 消息不会缓存，也不会因 `invalidate()` 或新 ViewPort 初始化而重发

这保证了 redirect 等副作用不会因为重连或重新渲染被重复执行。

## 多客户端

### ViewPort 模型

每个 WebSocket 连接对应一个 ViewPort，绑定一个 View 和一个 Channel。

- **ViewObservers**：跟踪同一 View 的所有 ViewPort，`invalidate()` 后自动推送到全部观察者
- **事件中的 viewport_id**：Callback 可通过 `@event.viewport_id` 获取来源客户端标识
- **推送顺序**：父 View 先推送，子 View 后推送；子 ViewPort 在父推送过程中创建/复用/清理

### Channel 抽象

`Channel` 是声明接口，提供 `channel_id: int` 和 `async send(message: dict)`。核心库不含网络代码，传输层由应用提供。

## 组件体系

### 可插拔解析链

`registerComponents(source)` 将组件源压入优先级栈（后注册优先）。`resolve(name)` 按以下顺序查找：

1. **命名空间查找**（含 `.` 的名字，如 `Input.TextArea`）：先匹配 `source.__name__`，再尝试属性路径
2. **直接查找**：遍历所有源的同名导出
3. **兜底**：返回字符串，React.createElement 当原生 HTML 元素渲染

### 构建分离

| 构建目标 | 命令 | 产物 | 内容 |
|----------|------|------|------|
| 核心包 | `npm run build:standalone` | `static/mutgui.js` | React + mutgui 渲染器（IIFE） |
| antd 插件 | `npm run build:antd` | `static/mutgui-antd.js` | Ant Design 组件（IIFE，React external） |
| npm 库包 | `npm run build` | `dist/index.js` | ES module，React external |

核心包暴露 `window.MutguiApp`：`mount()`、`registerComponents()`、`registerCommands()`、`React`、`ReactDOM`、`jsxRuntime`。组件库插件通过 `<script>` 标签加载后自动调用 `registerComponents()` / `registerCommands()` 注册。

## 内置组件

### 框架内置

- **VirtualList**：虚拟滚动列表，支持 Adapter 模式（`item_count`/`item_id`/`create_item_view`）、per-ViewPort 视口跟踪、可选滚动同步、32px 默认行高、5 项 overscan、50ms 节流

### Ant Design 插件

通过 `import * as antd` 导出全量 antd v5 组件。常用组件包括：

- **表单**：Input、InputNumber、Checkbox、Select、Switch、Slider、DatePicker、Radio、Rate、Cascader、Upload、Mentions、ColorPicker
- **布局**：Row、Col、Space、Divider、Layout
- **容器**：Card、Form、FormItem、Tabs、Collapse、Drawer、Modal
- **数据展示**：Table、List、Tree、Avatar、Badge、Tag、Statistic、Progress、Timeline
- **反馈**：Alert、Spin、Empty、Result、Message、Notification、Popconfirm
- **导航**：Menu、Breadcrumb、Pagination、Steps、Dropdown

## View 嵌套

- View 可在 `render()` 返回中直接包含子 View 实例，框架自动转换为 `{"$view": view_id}` 协议节点
- 每个 View 有局部 `id`（在兄弟 View 中唯一），路径数组 `[parent_id, ..., child_id]` 从根到叶
- 子 View 的 `invalidate()` 只触发自身重渲染，不影响父 View
- 前端通过 `ScopeProvider` 逐级传递路径上下文，事件自动携带完整源路径

## IME 输入处理

文本输入的 onChange 检测 IME 组合状态（compositionStart → compositionEnd）。组合期间值变更在前端本地缓冲，组合结束后发送最终值，避免中文等 IME 输入被中途打断。

## 前端扩展接入

自定义组件库的标准接入方式：

```typescript
// libs/my-components.ts
(window as any).MutguiApp.registerComponents({
  __name__: 'mylib',
  MyButton,
  MyCard,
});
```

```html
<script src="/static/mutgui.js"></script>
<script src="/static/libs/my-components.js"></script>
<script>MutguiApp.mount(...)</script>
```

后端通过 `$component: "mylib.MyButton"` 或 `$component: "MyButton"` 引用。
