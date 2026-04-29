# mutgui 前端构建与扩展

> 给“用 mutgui 跑前端 runtime”的人，以及“在 mutgui 之上继续做组件库”的人看的。

## 当前产物

`npm --prefix frontend run build` 会同时生成两类产物：

| 类别 | 位置 | 用途 |
|---|---|---|
| runtime 产物 | `src/mutgui/static/` | Python 侧页面直接加载 |
| dist 产物 | `frontend/dist/` | 本地 TS / vite 消费、类型分发 |

runtime 目录结构：

```text
src/mutgui/static/
  boot.js
  manifest.json
  libs/
    mutgui-core.js
    mutgui-core.css
    mutgui-antd.js
    mutgui-theme-dark.js
  vendor/
    react-<version>.js
    react-dom-client-<version>.js
    react-jsx-runtime-<version>.js
    antd-<version>.js
```

## 页面加载协议

Python 后端不再拼接一串 IIFE `<script>`，而是在渲染 HTML 时内联 import map，再加载一个 bootstrap：

```html
<div data-mutgui-app data-ws-url="/ws"></div>

<script type="importmap">{"imports": ...}</script>
<script src="/static/modules/mutgui/boot.js"></script>
```

加载时序：

1. import map 先注册
2. `boot.js` 建立 websocket，并发送 `{"type":"mount.attach",...}`
3. 后端按顺序下发 `runtime.css` / `runtime.import` / `runtime.install`
4. boot 执行这些运行时指令
5. 后端发送 `runtime.mount` 后，boot `import('@mutgui/core')` 并复用同一连接执行 mount
6. 后续 `render` / `command` / 事件继续走同一条 websocket

`data-ws-url` 可以是：

- 绝对 `ws://` / `wss://` 地址
- 站内路径（如 `/ws`、`/ws/demo-1`）
- 省略；省略时默认使用当前 `location.pathname`

页面不再依赖 `data-plugins` 做运行时装配。是否安装 dark theme、custom theme 等扩展，由后端在 websocket 建立后显式发送 `runtime.install` 决定。

## CSS 规则

mutgui 现在把 CSS 明确分成两类：

1. **eager 全局样式**：例如 `@mutgui/core` 的基础样式。后端在连接建立后通过 `runtime.css` 指示 boot 注入 `<link>`.
2. **扩展条件样式**：例如 theme-dark / theme-purple 的覆盖样式。保留 `?inline`，由扩展安装函数在运行时通过 `ctx.addCss()` 注入。

所以：

- runtime 页面**不要**自己手动再引入 `mutgui-core.css`
- plugin 如果需要按 mount 条件启用样式，继续用 `?inline`

## 对外扩展方式

现在扩展一个组件库时，不再依赖 `window.MutguiApp.*` 全局对象，而是直接写标准 ESM：

```ts
import * as antd from 'antd';
import { registerComponents } from '@mutgui/core';

registerComponents({
  __name__: 'antd',
  ...antd,
});
```

运行时扩展也是标准 ESM 默认导出：

```ts
import React from 'react';
import { ConfigProvider, theme } from 'antd';
import type { MutguiPlugin } from '@mutgui/core';
import darkCss from './dark.css?inline';

const plugin: MutguiPlugin = (ctx) => {
  ctx.addCss(darkCss);
  ctx.wrapRoot((children) =>
    React.createElement(ConfigProvider, { theme: { algorithm: theme.darkAlgorithm } }, children)
  );
};

export default plugin;
```

## 构建约定

- 唯一入口命令：`npm --prefix frontend run build`
- `frontend/build.mjs` 是唯一执行入口
- `frontend/mutgui.build.mjs` 只声明 mutgui 自己的 vendor / runtime / boot target
- `frontend/build-preset.mjs` 封装共享规则，并通过 `@mutgui/core/build-preset` 暴露给下游项目复用
- `vite build` 仍负责 `frontend/dist/index.js`
- `tsc --emitDeclarationOnly` 负责 `dist/*.d.ts`

vendor 文件名带版本号，没变就直接复用；业务代码改动时主要重打 runtime libs 与 dist。

Python 侧在运行时还会给每个静态资源 URL 追加 `?v=<mtime_ns>`，避免浏览器继续命中旧 bundle；因此日常开发不需要依赖手工强刷来刷新 import map 指向的 runtime 资源。

## 消费者注意事项

### Python runtime 场景

- 运行时页面只需要 import map + `boot.js` 协议，不要再引用旧的 `mutgui.js` / `mutgui-antd.js`
- 静态资源应挂到 `/static/modules/<python-package>/`
- `static/manifest.json` 仍作为后端生成 import map / eager CSS 的元数据来源，但不是页面必须内联的启动载荷

### 本地 TS / vite 场景

```ts
import { mount, registerComponents, MutguiView } from '@mutgui/core';
import '@mutgui/core/styles.css';
```

`frontend/dist/` 仍可作为本地 file: 依赖的入口，但它不是 Python runtime 的加载协议。
