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

Python 后端不再拼接一串 IIFE `<script>`，而是在渲染 HTML 时内联两段 JSON，再加载一个 bootstrap：

```html
<div data-mutgui-app
     data-ws-url="/ws"
     data-plugins="@mutgui/theme-dark"></div>

<script type="importmap">{"imports": ...}</script>
<script id="mutgui-manifest" type="application/json">{"importMap": ..., "css": ..., "entries": ...}</script>
<script src="/static/modules/mutgui/boot.js"></script>
```

加载时序：

1. import map 先注册
2. `boot.js` 读取内联 manifest
3. boot 先插入 runtime manifest `css` 列表里的 eager 样式
4. boot `import()` 各个 entry（如 `@mutgui/antd`、`@mutgui/theme-dark`）
5. boot `import('@mutgui/core')` 并对每个 `data-mutgui-app` 执行 `mount()`

`data-ws-url` 可以是：

- 绝对 `ws://` / `wss://` 地址
- 站内路径（如 `/ws`、`/ws/demo-1`）
- 省略；省略时默认使用当前 `location.pathname`

`data-plugins` 是逗号分隔的 plugin 模块名。模块全局只加载一次，但是否作用于某个 mount 由该属性决定。

## CSS 规则

mutgui 现在把 CSS 明确分成两类：

1. **eager 全局样式**：例如 `@mutgui/core` 的基础样式。构建后进入 runtime manifest 的 `css` 列表，由 boot 统一插 `<link>`.
2. **plugin 条件样式**：例如 theme-dark 的少量覆盖样式。保留 `?inline`，由 plugin 在运行时通过 `ctx.addCss()` 注入。

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

plugin 也是标准 ESM 默认导出：

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
- `scripts/build.mjs` 负责 vendor/runtime 产物与 `manifest.json`
- `vite build` 仍负责 `frontend/dist/index.js`
- `tsc --emitDeclarationOnly` 负责 `dist/*.d.ts`

vendor 文件名带版本号，没变就直接复用；业务代码改动时主要重打 runtime libs 与 dist。

Python 侧在运行时还会给每个静态资源 URL 追加 `?v=<mtime_ns>`，避免浏览器继续命中旧 bundle；因此日常开发不需要依赖手工强刷来刷新 import map 指向的 runtime 资源。

## 消费者注意事项

### Python runtime 场景

- 只需要 `static/manifest.json` + `boot.js` 协议，不要再引用旧的 `mutgui.js` / `mutgui-antd.js`
- 静态资源应挂到 `/static/modules/<python-package>/`

### 本地 TS / vite 场景

```ts
import { mount, registerComponents, MutguiView } from '@mutgui/core';
import '@mutgui/core/styles.css';
```

`frontend/dist/` 仍可作为本地 file: 依赖的入口，但它不是 Python runtime 的加载协议。
