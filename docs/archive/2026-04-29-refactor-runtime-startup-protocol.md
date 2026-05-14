# mutgui 运行时启动协议收敛 设计规范

**状态**：✅ 已完成
**日期**：2026-04-29
**类型**：重构

## 需求

1. `mutgui` 当前通过 HTML 内联 runtime manifest 告诉 `boot.js` 该加载哪些 CSS / entry / plugin，启动装配决策偏前端，不符合“后端驱动 UI”的方向。
2. 页面启动必须收敛到 **单 websocket 连接**，不能再出现“boot 一套连接、render 再开一套连接”的模型。
3. 浏览器原生 import map 约束保留：import map 继续内联到 HTML，不改成 HTTP / websocket 获取。
4. demo 中 `menu` / `dock` / `theming` 等自定义 HTML 页面，应尽量只保留页面壳子定制，运行时装配改为后端控制。
5. 官方主题示例收敛为 `theming`：只演示后端控制的 `none` / `dark` 切换，不再保留自定义紫色主题。

## 关键参考

- `frontend/src/boot.ts` — 本轮新增 `mount.attach` + `runtime.*` 启动时序，并保留 manifest 回退兼容
- `frontend/src/core.tsx` — 新增复用既有连接的 `mountWithConnection()` 与 `createConnection()`
- `frontend/src/plugins/theme-dark/index.ts` — 当前主题扩展的前端实现形态
- `frontend/mutgui.build.mjs` — 当前 runtime / plugin 模块构建声明
- `src/mutgui/modules.py` — 当前 import map / manifest 聚合来源
- `demo/framework/_routes.py` — 当前 demo HTML 模板拼装与 `data-plugins`
- `demo/framework/_server.py` — 当前 demo websocket 生命周期，进入连接后立即初始化 `ViewPort`

## 设计方案

### 总体思路

保留浏览器原生 import map，移除 HTML 对 runtime manifest 的依赖，把启动装配收敛到 **同一条 websocket 上的运行时指令流**：

1. HTML 只保留：
   - `<div data-mutgui-app ...>`
   - `<script type="importmap">`
   - `<script src=".../boot.js">`
2. `boot.js` 建立 websocket 后先发送 `mount.attach`
3. 后端按顺序返回 `runtime.*` 消息：
   - 注入 CSS
   - import 模块
   - 安装运行时扩展
   - 最后允许 mount
4. 前端完成 mount 后，连接继续承载正常 `render` / `command` / 事件流

这样“启动”只是同一条运行时流的前几条消息，不再需要 HTML manifest 做前端装配。

### HTML 协议

页面统一收敛为：

```html
<div id="app" data-mutgui-app data-ws-url="/ws"></div>
<script type="importmap">{...}</script>
<script src="/static/modules/mutgui/boot.js"></script>
```

约束：

- `data-ws-url` 仍属于 mount 级配置，保留在 div 上
- `data-plugins` 不再作为主要装配入口
- 自定义 demo HTML 仍可保留页面壳子（如全屏布局、说明文案、额外 `<style>`），但不再主动写运行时装配逻辑

### 单连接启动时序

#### 前端首条消息

```json
{"type":"mount.attach","mountId":"app","protocol":1}
```

语义：当前页面 mount 点已建立连接，请后端发送本 mount 的运行时装配步骤。

#### 后端装配消息

本轮采用动作型消息，而不是把旧 manifest 原样搬到 websocket：

```json
{"type":"runtime.css","href":"..."}
{"type":"runtime.import","module":"@mutgui/antd"}
{"type":"runtime.install","module":"@mutgui/theme-dark"}
{"type":"runtime.mount"}
```

约束：

- 消息按顺序执行
- `runtime.mount` 之后才能发送引用扩展组件的 `render`
- 若某组件依赖 `antd.*`、`mutgui.*` 以外的前端命名空间，后端必须先发送对应 `runtime.import`
- `runtime.install` 面向“前端副作用安装”，取代 HTML `data-plugins` 的主职责

### 前端执行模型

`boot.js` 只做三件事：

1. 建立 websocket 并发送 `mount.attach`
2. 顺序执行后端下发的 `runtime.*` 消息
3. 在收到 `runtime.mount` 时，调用 `@mutgui/core` 的“复用既有连接 mount”入口

前端维护的状态只有：

- 已加载 CSS 集合
- 已 import 模块集合
- 已安装扩展集合
- 当前 mount 是否已完成

前端不主动决定要加载哪些模块，也不再从 HTML manifest 推导装配。

### `@mutgui/core` 入口调整

现有 `mount(el, wsUrl, plugins)` 会在内部自行 `new WebSocket(wsUrl)`，不适合单连接启动。

本轮调整为：

- 保留现有 `mount()` 作为兼容入口
- 新增“复用既有连接”的入口，供 `boot.js` 使用
- 连接对象需要能接收外部转发的 `render` / `command` 消息，而不是自己直接绑 websocket 生命周期

这样启动和正常渲染可真正共用同一条连接。

### 扩展安装模型

协议层不再强调“plugin”这个词，但前端仍需保留一类“扩展安装”能力，对应原本的：

- `addCss`
- `addBodyClass`
- `wrapRoot`

因此 `runtime.install` 约定模块导出一个标准安装函数（可继续复用现有 default export 形式），由前端执行：

```ts
export default function install(ctx) { ... }
```

这层本质上是“前端 effect / extension 安装协议”，不再依赖 HTML `data-plugins`。

### demo 页面装配

demo framework 需要把运行时装配显式声明到后端：

- 默认页面：
  - eager CSS：`@mutgui/core` 对应样式
  - import：按页面需要加载 `@mutgui/antd`
  - install：默认安装 `@mutgui/theme-dark`
- demo route 提供 `layout="plain" | "centered" | "fullscreen"` 页面壳子选择：
  - `plain`：不额外包 960px 容器，mount div 直接落在 body
  - `centered`：文档式居中容器
  - `fullscreen`：`html/body/#app` 占满窗口
- `theming`：
  - 页面可在后端控制的 `none` / `dark` 两种模式间切换
  - 切换通过 `mutgui.reload()` 触发重连，新的 runtime 消息决定是否安装 `@mutgui/theme-dark`
- `basic` / `antd` / `command` / `menu`：
  - 使用 `plain`，不由 framework 默认强加 960px 外层容器
- `dock`：
  - 使用 `fullscreen`，满足 IDE / app 类页面占满窗口的常见需求

### 消费者场景

| 消费者 | 场景 | 依赖的输出 | 本轮验收 |
|---|---|---|---|
| mutgui demo/basic | 单连接启动，无 HTML manifest，页面可正常 render 与交互 | `mount.attach` + `runtime.mount` + render 流 | ✅ 必须 |
| mutgui demo/menu | 使用默认模板 `plain` layout，不再额外包 960px 容器 | 页面级 runtime 配置 + 单连接启动 + route layout | ✅ 必须 |
| mutgui demo/dock | 使用 `fullscreen` layout 占满窗口 | 页面级 runtime 配置 + 单连接启动 + route layout | ✅ 必须 |
| mutgui demo/theming | 页面可在后端控制下切换 none/dark，并通过 reload 重连重新装配主题 | 后端主题状态 + `runtime.install` + `mutgui.reload()` | ✅ 必须 |
## 实施步骤清单

- [x] 新增本轮启动协议设计文档，并明确单连接运行时消息时序
- [x] 重构 `boot.js` 与 `@mutgui/core`，让启动和正常渲染共用同一 websocket
- [x] 把 demo framework 改为后端声明运行时装配，移除 HTML manifest / `data-plugins` 的主职责
- [x] 完成 mutgui 构建、demo 启动与浏览器验收

## 测试验证

- `npm --prefix frontend run build`
- `python -m pytest tests/test_command_channel.py tests/test_menu.py tests/test_dock_panel.py`
- `python -m demo`
- chrome-cdp 验证：
  - `basic` 页面正常加载，按钮点击后从 `Clicked 0 times` 变为 `Clicked 1 times`
  - `menu` 页面正常加载，`#app` 直接位于 body 下，不再被默认 960px 容器包裹
  - `dock` 页面正常加载，`body margin === 0`、`overflow === hidden`、`#app` 占满窗口
  - `theming` 页面正常加载；默认 `none` 时 `document.body.className === ""`，切到 `dark` 后重连安装 `theme-dark`
