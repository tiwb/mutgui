# mutgui 组件库扩展机制（ESM + Import Map)

**状态**：✅ 已完成
**日期**：2026-04-28
**类型**：功能设计（架构层）

> 本文是该规范的第二版，整体方案推翻重写。第一版基于 IIFE + 全局命名空间（`window.MutguiApp.*`）的"洋葱式 external"思路，无法做到第三方库（如 react-markdown）的真正库级共享。新版以浏览器原生 ES Module + Import Map 为基础，统一所有库的加载与共享机制。
>
> 第一版的相关实现（vite IIFE 配置、`MutguiApp.<libname>` 命名空间、HTML 硬拼 `<script>` 链）在本规范实施完成后整体下线。

## 需求

1. **库级共享**：第三方库（react、antd、react-markdown 等）在多层组件库间共享时是真正的单实例，而不是各层 bundle 各自打一份。
2. **统一形态**：mutgui 自身、可选组件库（antd、theme-dark）、下游项目（mutagent / mutbot）、第三方扩展，全部走同一种发布与加载形态，没有“框架内置特例”。
3. **后端可控加载**：HTML 模板不再硬拼 `<script>` 标签链，由后端 Python 在运行时聚合“哪些模块、什么 URL、什么依赖”并下发给前端。
4. **路径无侵入**：每个 Python 包只声明包内相对路径，绝对 URL 由后端在运行时拼装;包不知道也不关心自己被挂到哪个前缀。
5. **零 npm 发布**：mutgui 及其生态下的应用/插件不向 npm registry 发包。所有运行时 JS、构建期 vite preset、TypeScript 类型，都随 Python wheel 通过 PyPI 分发。开发工具链（vite、typescript）仍走 node 生态。
6. **开发期源码同生产期**：开发期写的 `import 'react'` 和 `import '@mutgui/core'`，跟生产期跑的代码完全一样，差别只在加载机制。
7. **MVP 在 mutgui 单项目内端到端验证**：方案先在 mutgui 仓库自身打通--`python -m demo` 跑起来，前端通过 import map 加载 react / antd / mutgui-core / mutgui-theme-dark，浏览器 Network 中可见各文件独立加载且单实例。下游项目本轮不动。

## 关键参考

### 现状代码

- `mutgui/frontend/vite.config.ts` / `vite.standalone.ts` / `vite.antd.ts` / `vite.theme-dark.ts` - 4 份 vite 配置，硬编码 4 套 external / globals
- `mutgui/frontend/src/standalone.tsx` - 当前 IIFE 入口，`window.MutguiApp` 命名空间挂载
- `mutgui/frontend/src/integrations/antd.ts` - 一层组件库样板，`app.antd = antd`
- `mutgui/frontend/src/plugins/theme-dark/index.ts` - plugin 样板，`window.MutguiThemeDark = plugin`
- `mutgui/frontend/src/index.ts` - 当前 npm 包入口（本规范实施后保留为开发期类型源，不再发 npm)
- `mutgui/frontend/package.json` - react/antd 当前在 `dependencies`（应改为 `peerDependencies`，但因不发 npm，纯属规范性调整）
- `mutgui/demo/framework/_routes.py:29-32` - 当前 HTML 模板硬拼 3 个 `<script>` 标签
- `mutgui/demo/standalone/starlette.py:97-105` - 同上，独立 starlette 示例

### 上下文

- `mutgui/docs/design/frontend-build.md` - 现有机制使用说明（本规范实施完后整体重写）
- `mutgui/docs/specifications/feature-pluggable-component-libs.md` - 组件解析机制（命名空间注册），本规范保持兼容
- `mutagent/docs/specifications/feature-frontend-component-package.md` - 下游 mutagent 的组件库立项（本轮不联动，待 mutgui MVP 完成后启动）

### 浏览器能力

- [Import Maps spec (HTML Living Standard)](https://html.spec.whatwg.org/multipage/webappapis.html#import-maps)
- 主流浏览器原生支持：Chrome 89+ / Edge 89+ / Firefox 108+ / Safari 16.4+
- mutgui 的目标用户全部走现代浏览器，无需 polyfill

## 设计方案

### 总体思路

把整个前端世界统一为一种结构：

```
ES Module 文件 + Import Map 解析名字
```

所有 JS--包括 react 本身--都是浏览器可直接 import 的 ESM 文件，物理上躺在某个 Python 包的 `static/` 目录里。后端启动时聚合各包的 manifest，在**渲染 HTML 时直接内联 import map 和 runtime manifest JSON**。浏览器先注册 import map，再执行一个不依赖 bare specifier 的 bootstrap script（`boot.js`），由它用 `await import(name)` 触发依赖图加载。

URL 单例性由浏览器保证（同一个 URL 只 fetch 一次、只实例化一次），自然解决 React 单例、antd ConfigProvider 共享等问题。

### 物理布局

```
mutgui/
  frontend/
    vendor-build/                    新增:把第三方 npm 包打成单文件 ESM
      react.config.ts
      react-dom-client.config.ts
      react-jsx-runtime.config.ts
      antd.config.ts
    build-preset/                    新增:defineLib() 工厂,供下游 vite.config.ts 使用
      index.ts
      package.json                   壳,不发 npm,仅用于 file: / tsconfig paths
    scripts/
      build.mjs                      新增:单一构建编排器(vendor skip + libs + boot + manifest)
    src/
      boot.ts                        新增:bootstrap 源文件，构建为 boot.js
      core.tsx                       新增:mutgui-core lib 的 ESM 入口(取代 standalone.tsx)
      plugins/theme-dark/index.ts    改造为 ESM 入口
      integrations/antd.ts           改造为 ESM 入口(仅做命名空间注册,antd 本体走 vendor)
    package.json                     脚本调整
  src/mutgui/
    static/                          全部构建产物落地,已在 .gitignore,由 npm run build 生成
      boot.js                        唯一被 HTML <script> 加载的文件
      manifest.json                  mutgui 自身的包内 manifest
      vendor/                        文件名带版本号，作为天然指纹（由 build 脚本自动管理，详见「第三方库的 vendor 化」）
        react-19.1.0.js
        react-dom-client-19.1.0.js
        react-jsx-runtime-19.1.0.js
        antd-5.24.0.js
      libs/
        mutgui-core.js               含 mount / registerComponents / 内置组件
        mutgui-antd.js               薄壳:把 antd 命名空间注册到 mutgui registry
        mutgui-theme-dark.js         plugin
      types/                         本规范阶段先不做,留位
    modules.py                       新增:ModuleRegistry / 静态挂载辅助
```

### 包内 manifest 格式

每个 Python 包带一个 `static/manifest.json`,**只用包内相对路径**：

```json
{
  "name": "mutgui",
  "exports": {
    "react":              "vendor/react-19.1.0.js",
    "react-dom/client":   "vendor/react-dom-client-19.1.0.js",
    "react/jsx-runtime":  "vendor/react-jsx-runtime-19.1.0.js",
    "antd":               "vendor/antd-5.24.0.js",
    "@mutgui/core":       "libs/mutgui-core.js",
    "@mutgui/antd":       "libs/mutgui-antd.js",
    "@mutgui/theme-dark": "libs/mutgui-theme-dark.js"
  },
  "css": [],
  "entries": [
    {"name": "@mutgui/antd",       "kind": "lib"},
    {"name": "@mutgui/theme-dark", "kind": "plugin"}
  ]
}
```

字段说明：
- `name`：包名（仅诊断/日志用）
- `exports`：本包提供哪些 import map 名字 → 包内相对路径
- `css`：本包要在页面上注入的 CSS 文件列表（包内相对路径），boot 阶段统一拼成 `<link>` 注入
- `entries`：本包希望被 boot 自动 `import()` 触发执行的模块及其角色
  - `kind: "lib"` - 普通组件库，import 时执行注册副作用即可
  - `kind: "plugin"` - mutgui plugin（如 theme-dark),import 后取其 `default` 导出加入 plugin 列表传给 `mount()`

`@mutgui/core` 不在 entries 里--它由 boot/bootstrap 显式 import 并调用 `mount()`，是框架硬约定。

manifest **只描述本包对外暴露什么，不描述内部依赖图**（无 `deps` 字段）。模块间依赖完全交给浏览器 ESM resolver--`@mutgui/antd` 内部 `import 'antd'` 时，浏览器会自动并行 fetch antd;某个 import 名字在 import map 里找不到时浏览器会报清晰错误，无需冗余声明。

### 后端 ModuleRegistry

新增 `mutgui/src/mutgui/modules.py`:

```python
class ModuleRegistry:
    """聚合各 Python 包的前端 manifest,输出统一的运行时 manifest。"""

    def __init__(self) -> None:
        self._packages: list[tuple[str, Path, dict]] = []

    def add_from_package(self, package_name: str) -> None:
        """从 Python 包里读 static/manifest.json 注册。"""
        static_dir = importlib.resources.files(package_name) / "static"
        manifest = json.loads((static_dir / "manifest.json").read_text("utf-8"))
        self._packages.append((package_name, Path(str(static_dir)), manifest))

    # 静态文件统一挂在 /static/modules/<pkg>/ 下:
    # - 走 /static/ 这个 CDN 友好的根,未来加图片、字体等都能复用同一条 CDN 规则
    # - modules/ 子目录把 ESM 模块加载体系跟普通静态资源(图片等)分开,互不污染
    # - <pkg> 段按 Python 包名隔离,多个扩展包之间不会撞文件名
    URL_PREFIX = "/static/modules"

    def url_prefix(self, package_name: str) -> str:
        return f"{self.URL_PREFIX}/{package_name}/"

    def static_mounts(self) -> list[tuple[str, Path]]:
        """返回 (url_prefix, dir) 列表,供框架做 StaticFiles 挂载。"""
        return [(self.url_prefix(p), d) for p, d, _ in self._packages]

    def runtime_manifest(self) -> dict:
        """聚合输出最终下发给前端的 manifest(绝对 URL)。"""
        import_map: dict[str, str] = {}
        css: list[str] = []
        entries: list[dict] = []
        for pkg, _, m in self._packages:
            prefix = self.url_prefix(pkg)
            for name, rel in m.get("exports", {}).items():
                if name in import_map:
                    raise RuntimeError(
                        f"Import name conflict: '{name}' from {pkg} "
                        f"already provided by another package"
                    )
                import_map[name] = prefix + rel
            for rel in m.get("css", []):
                css.append(prefix + rel)
            for entry in m.get("entries", []):
                entries.append(entry)
        return {"importMap": import_map, "css": css, "entries": entries}
```

冲突策略：默认抛错（让用户在配置层显式选择），后续可加优先级机制。

### 后端集成（demo 层）

`demo/framework/_routes.py` 与 `demo/standalone/starlette.py` 改造：

1. 在应用启动时构建一个 `ModuleRegistry`，注册 `mutgui` 包（demo 内只有这一个包，足够验证机制）
2. 通过 `app.mount(prefix, StaticFiles(directory=dir))` 把每个包的 static 目录挂到对应前缀
3. HTML 模板退化为一个挂载点 + 3 个固定 script（import map / manifest JSON / boot）：

```html
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{title}</title></head>
<body>
  <div data-mutgui-app
       data-ws-url="ws://{host}{path}"
       data-plugins="@mutgui/theme-dark"></div>
  <script type="importmap">{...runtime import map json...}</script>
  <script id="mutgui-manifest" type="application/json">{...runtime manifest json...}</script>
  <script src="/static/modules/mutgui/boot.js"></script>
</body>
</html>
```

挂载点的配置全部走 `data-*` attribute，由后端模板渲染时直接拼入;不再向 `window` 注入任何全局对象。`boot.js` 启动时通过 `document.querySelectorAll('[data-mutgui-app]')` 找到所有挂载点，循环 mount。

**多实例支持**：一个页面可以放多个 `<div data-mutgui-app>`，每个独立 mount + 独立 wsUrl。manifest 与 import map 全局只注入一份共享。plugin 模块全局只 import 一次，但**是否对某个 mount 生效**由该 div 的 `data-plugins` 决定（逗号分隔模块名）；这样 `no_theme` 页面可以不启用 dark theme，而多实例页面仍共享同一份模块实例。

**attribute 命名规范**：使用 HTML 标准 `data-*` 前缀 + kebab-case，DOM API 分别通过 `el.dataset.wsUrl`、`el.dataset.plugins` 自动驼峰读取。

**未来 Web Component 升级路径**：MVP 选 `<div data-mutgui-app>` 而非自定义元素 `<mutgui-app>`，因为 Shadow DOM 与 antd portal(`message`/`Modal`/`notification` 默认挂 `document.body`）和 theme-dark plugin（操作 `documentElement`）冲突;即便升级也只能走 light DOM 模式，相对当前方案只多“自定义元素名 + connectedCallback 生命周期”两个语义优势，本规范不做。触发条件是"用户在自己的非 mutgui 页面散插多个独立 mutgui app"。届时自定义元素可与现有 `[data-mutgui-app]` 选择器并存（同一元素可同时持有两种标识），无破坏性改动。

### import map 生效时机（阻塞点已定）

浏览器要求 import map 在依赖它的 module 解析前就完成注册，因此 **`boot.js` 不能是 `type="module"`**。MVP 的时序固定为：

1. 后端渲染 HTML 时内联 `<script type="importmap">`
2. 同一份 HTML 紧接着内联 `<script type="application/json" id="mutgui-manifest">`
3. 最后加载普通 `<script src=".../boot.js">`
4. `boot.js` 读取已内联的 manifest，之后才调用 `import('@mutgui/core')` / `import(entry.name)`

这样 import map 在任何 bare specifier 解析前已生效，不依赖“动态插入 import map 后浏览器是否补注册”的边缘行为。`/api/manifest` 可作为调试接口补充，但 **boot 不依赖它**，避免首屏多一次 fetch，也避免“boot 先作为 module 执行”这一架构错误。

### CSS 协议（阻塞点已定）

CSS 分三类处理，避免“一刀切全走 manifest.css”导致 plugin 条件样式无法表达：

1. **eager 全局样式**：页面上只要跑 mutgui 就必须存在的样式（如 `@mutgui/core` 基础样式、vendor 产出的 antd CSS）。这些产物由构建脚本写入 runtime manifest 的 `css` 列表，boot 在 mount 前统一插入 `<link>`.
2. **plugin 条件样式**：只有启用某个 plugin 才需要的少量样式（如 theme-dark 的覆盖 CSS）。这类样式继续由 plugin 模块内部 `import './x.css?inline'` 后通过 `ctx.addCss()` 注入，不进入 runtime manifest 的 `css` 列表。
3. **开发期 dist 样式**：`frontend/dist/styles.css` 仅服务本地 TS / vite 消费者，不参与 Python runtime 的 manifest 协议。

对应约束：

- `@mutgui/core` runtime lib 必须产出单独 CSS 文件，并记录到 runtime manifest 的 `css` 列表
- vendor build 若生成 CSS（如 antd）同样进入 runtime manifest 的 `css` 列表
- plugin 不得依赖 `import './x.css'` 这种浏览器原生不认识的 ESM CSS import；若 CSS 需要按 plugin 条件启用，必须走 `?inline + ctx.addCss`

### boot.ts / boot.js 流程

```ts
async function start() {
  // 1. 找所有挂载点;任一 div 缺 ws-url 就视为配置错误
  const targets = Array.from(
    document.querySelectorAll<HTMLElement>('[data-mutgui-app]')
  );
  if (targets.length === 0) {
    throw new Error('No <div data-mutgui-app> found on page');
  }

  // 2. 从 HTML 内联 JSON 读取 manifest（import map 已在 boot 运行前注册）
  const manifest = readManifest();

  // 3. 注入 CSS(独立 <link>,去重靠 URL)
  for (const href of manifest.css) {
    if (!document.querySelector(`link[href="${href}"]`)) {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = href;
      document.head.appendChild(link);
    }
  }

  // 4. 加载 entries: lib 只要 import 触发注册副作用即可;
  //    plugin 记录到表里,各 mount 再按 data-plugins 选择
  const pluginTable = new Map<string, any>();
  for (const entry of manifest.entries) {
    const mod = await import(/* @vite-ignore */ entry.name);
    if (entry.kind === 'plugin') {
      pluginTable.set(entry.name, mod.default);
    }
  }

  // 5. 对每个挂载点调用 mount
  const { mount } = await import('@mutgui/core');
  for (const el of targets) {
    const wsUrl = required(el, 'wsUrl');
    const plugins = readPlugins(el, pluginTable);
    mount(el, wsUrl, plugins);
  }
}

function readManifest(): RuntimeManifest {
  const el = document.getElementById('mutgui-manifest');
  if (!el?.textContent) throw new Error('Missing #mutgui-manifest JSON script');
  return JSON.parse(el.textContent);
}

function readPlugins(el: HTMLElement, table: Map<string, any>): any[] {
  const names = (el.dataset.plugins ?? '')
    .split(',')
    .map(s => s.trim())
    .filter(Boolean);
  return names.map(name => {
    const plugin = table.get(name);
    if (!plugin) throw new Error(`Unknown plugin requested by mount point: ${name}`);
    return plugin;
  });
}

function required(el: HTMLElement, key: string): string {
  const v = el.dataset[key];
  if (!v) throw new Error(`<div data-mutgui-app> missing data-${kebab(key)}`);
  return v;
}
function kebab(s: string): string {
  return s.replace(/[A-Z]/g, c => '-' + c.toLowerCase());
}

start().catch(err => {
  document.body.innerHTML = `<pre style="color:red">${err.stack}</pre>`;
});
```

`boot.js` 自身**不能 import 任何 bare specifier 业务模块**。它作为普通 script 执行，唯一职责是读取内联 manifest、注入 eager CSS、再用动态 `import()` 拉起 ESM 图。构建时不走 lib 模式，独立打包为单文件 bootstrap。

**挂载点的契约**：boot 把 `<div data-mutgui-app>` 自身作为 mount target 直接传给 `mount()`，不再有 `mountTarget` 这一层间接配置。div 是配置和宿主合一的单一真相源。

**失败 UX**：MVP 阶段顶层 `start().catch` 直接在 `<body>` 写入红色 `<pre>` 显示完整 stack（覆盖 fetch manifest 失败、import 失败、import map 注入时机问题等所有场景）。产品化阶段再设计加载占位、重试、降级，本规范不做。

### vite build-preset

`frontend/build-preset/index.ts` 导出 `defineLib`:

```ts
import { defineConfig, type UserConfig } from 'vite';
import { resolve } from 'node:path';

export interface LibOptions {
  name: string;             // import map 中的名字,如 '@mutgui/core'
  entry: string;            // 源文件路径(相对项目根)
  outFile: string;          // 输出文件名(相对 outDir)
  outDir: string;           // 输出目录绝对路径
  peers?: string[];         // external 依赖名字数组
  react?: boolean;          // 默认 true,自动 inject @vitejs/plugin-react
  extraPlugins?: Plugin[];  // 追加自定义 vite 插件
}

// preset 默认自动 inject @vitejs/plugin-react(mutgui 自家三个 lib 都需要);
// 下游若不需要可显式传 `react: false` 关闭,需要追加自定义插件用 `extraPlugins`。

export function defineLib(opts: LibOptions): UserConfig {
  return defineConfig({
    plugins: [/* @vitejs/plugin-react(除非 react: false) + opts.extraPlugins */],
    build: {
      lib: {
        entry: resolve(opts.entry),
        formats: ['es'],
        fileName: () => opts.outFile,
      },
      outDir: opts.outDir,
      emptyOutDir: false,
      rollupOptions: {
        external: opts.peers ?? [],
        // ESM 模式不需要 globals 映射,浏览器 import map 自己解析
      },
      cssCodeSplit: false,
    },
  });
}
```

manifest.json 的生成由一个独立的 vite 插件或构建后脚本完成（读取所有 `defineLib` 的产物 + 配置中声明的 vendor 与 entries，写入 `static/manifest.json`）。

### 第三方库的 vendor 化

`vendor-build/` 子目录用 vite 把 react / react-dom / antd 各自打成单文件 ESM,**产物文件名带版本号**（版本号由 `scripts/build.mjs` 从 `package-lock.json` 读出后注入）：

```ts
// vendor-build/react.config.ts -- 由 scripts/build.mjs 拼接版本号后调用
import { defineConfig } from 'vite';
export default ({ version }: { version: string }) => defineConfig({
  build: {
    lib: {
      entry: 'react/index.js',  // 直接从 node_modules 拿
      formats: ['es'],
      fileName: () => `react-${version}.js`,
    },
    outDir: '../src/mutgui/static/vendor',
    emptyOutDir: false,
  },
});
```

要点：
- React 的 CJS `module.exports` 由 vite/rollup 自动转成 ESM `export`
- antd 的 CSS 通过 `cssCodeSplit: false` + 独立 CSS 输出（manifest 中通过 `css` 字段引用）
- jsx-runtime 单独打一份（`react-jsx-runtime-<version>.js`)
- 文件名版本号即天然指纹（也天然适合 immutable 长缓存）：build 脚本检查文件存在则 skip，缺失则编译

所有产物都不进 git（`src/mutgui/static/` 已在 `.gitignore` 中），由 `npm run build` 生成；CI 打 wheel 前跑一次 build 即可。

#### 单一构建命令的自动闭环

采用「产物文件名带版本号」方案，避免 stamp 文件、独立子命令、产物入 git、postinstall hook 等机制——`npm run build` 是唯一入口，零心智负担。核心实现 `frontend/scripts/build.mjs`：

```js
// 1. 读 package-lock.json 得到 vendor 期望版本
const lock = JSON.parse(readFileSync('package-lock.json'));
const v = {
  react:       lock.packages['node_modules/react'].version,
  'react-dom': lock.packages['node_modules/react-dom'].version,
  antd:        lock.packages['node_modules/antd'].version,
};

// 2. 期望产物（文件名 = 名字 + 版本号 + .js）
const expected = {
  'react':              `vendor/react-${v.react}.js`,
  'react-dom/client':   `vendor/react-dom-client-${v['react-dom']}.js`,
  'react/jsx-runtime':  `vendor/react-jsx-runtime-${v.react}.js`,
  'antd':               `vendor/antd-${v.antd}.js`,
};

// 3. 缺哪个跑哪个；全在则 skip 全部 vendor 编译（0 秒）
for (const [name, file] of Object.entries(expected)) {
  if (!existsSync(`../src/mutgui/static/${file}`)) await buildVendor(name, file);
}

// 4. libs + boot 总是重打（每个 1~2 秒）
await buildLibs();
await buildBoot();

// 5. 写 manifest.json，exports 指向带版本号的具体路径
writeManifest(expected);

// 6. 清理不在 expected 列表中的旧版本残留（避免目录无限膨胀）
cleanStaleVendors(Object.values(expected));
```

各场景行为：

| 场景 | 行为 | 耗时量级 |
|---|---|---|
| 首次 clone | 期望文件全缺 → 全部编译 + libs | ~15s |
| 改完业务代码 | vendor 全在 → skip + 重打 libs | **~3s** |
| `npm install` 升级 react | lockfile 改 → 期望文件名变 → 缺失 → 自动重打受影响项 | ~5s |
| 切分支回退 lockfile | 旧版本文件名又匹配上 → skip | ~3s |

收益：状态自包含（产物文件本身就是“上次 build 了什么版本”的真相），升级第三方依赖的工作流（改 package.json + npm install + npm run build）全自动无遗漏风险。

### mutgui 内部三个 lib 的改造

| Lib | 入口 | 形态 | peers | 备注 |
|---|---|---|---|---|
| `@mutgui/core` | `frontend/src/core.tsx` | ESM lib | `react`, `react-dom/client`, `react/jsx-runtime` | 含 `mount`、`registerComponents`、内置组件，是 boot 必引 |
| `@mutgui/antd` | `frontend/src/integrations/antd.ts` | ESM lib | `react`, `react/jsx-runtime`, `antd`, `@mutgui/core` | 改造为薄壳：`import * as antd from 'antd'; registerComponents({__name__:'antd', ...antd})`;不再挂 window |
| `@mutgui/theme-dark` | `frontend/src/plugins/theme-dark/index.ts` | ESM plugin | `react`, `antd`, `@mutgui/core` | `default export` 一个 plugin 函数，boot 自动收集 |

`mutgui-core.js` 不再自带 antd（当前 IIFE 模式 antd 是 external，新模式同样 external），不再自带 React(vendor 化后 react 是独立 ESM）。

`@mutgui/antd` 不再“挂 antd 到全局”--antd 本身就是 import map 中的一个名字，需要时直接 `import * as antd from 'antd'` 即可。它存在的唯一价值是把 antd 的所有组件批量注册到 mutgui registry(`$component: 'antd.Button'` 这套机制依赖它），同时也作为 entries `kind: "lib"` 的样板用法（证明“普通 lib 通过 entries 自动加载”路径可行）。后续可以考虑让组件注册按需触发，本规范不做。

`@mutgui/theme-dark` 的 plugin 协议不变（`(ctx) => void`），只是导出方式从 `window.MutguiThemeDark = plugin` 改为 `export default plugin`。

`@mutgui/theme-dark` 的 CSS 仍保留 `?inline` + `ctx.addCss()` 形式，不产出单独 CSS 文件；这是 deliberate design：dark theme 是按 mount 可选的条件能力，不属于 eager global CSS。

### 不发 npm，但保留 `@mutgui/*` 命名

import map 的名字保留 `@mutgui/core` / `@mutgui/antd` / `@mutgui/theme-dark` 的写法。这只是字符串约定，不要求对应的 npm 包真实存在。

下游开发期获得类型 / vite alias 的方式（本规范暂不实施，留待下游迁移时设计）：
- 候选 A:mutgui 提供 CLI 命令读 Python 包路径生成 vite/tsconfig 配置
- 候选 B:build-preset 内部自动 spawn `python -c "import mutgui; print(...)"` 解析路径

本规范阶段 mutgui 自己开发时所有 peers 都在同一仓库，用 vite 的 alias 直接指向源码即可，不需要这套 helper。

### 开发期工作模式

mutgui 开发者改前端代码时，统一用单一命令：

```bash
# 首次 / 任何源码变更后
cd mutgui/frontend
npm install   # 仅在 package.json 改动时
npm run build # vendor 自动 skip,libs + boot 重打,约 3 秒

# 另一终端跑 demo
python -m demo
```

浏览器手动刷新看效果。`npm run build` 是唯一入口，没有 `build:vendor` / `build:libs` 等子命令需要记忆--vendor 通过版本号文件名自然 skip，无脑跑就对了。

首次启动：后端 `ModuleRegistry.add_from_package()` 检测到 `static/manifest.json` 缺失时直接抛错并提示 `cd frontend && npm run build`，避免 404 白屏。

本规范不引入 vite dev server / HMR;如未来确实需要 watch，可在 `scripts/build.mjs` 加 `--watch` 参数对 libs 部分起 vite watch(vendor 不进 watch）。

### CDN 与缓存策略（暂不实施）

本规范阶段不引入 CDN、不加缓存控制头、libs 产物文件名不带 hash（开发期靠浏览器强刷 Ctrl+Shift+R 即可）。MVP 在单机跑 demo 验证机制，没有 CDN 需求。

但路径选型已为 CDN 升级预留空间：

- `/static/modules/<pkg>/` 路径与业务 API 路由隔离，能被 `/static/*` 一条 CDN 规则覆盖
- vendor 文件名已天然带版本号（如 `react-19.1.0.js`），具备 immutable 长缓存条件

未来 CDN 升级时仅需补齐 libs 部分，无破坏性改动：

1. `defineLib` 产物加 content hash（`mutgui-core.[hash].js`），`manifest.json` 同步记录带 hash 的路径
2. `ModuleRegistry` 增加 `cdn_base: str | None` 参数，输出 import map 时优先用 CDN 绝对 URL
3. 后端 static mount 不变（CDN 回源用），vendor 与带 hash 的 libs 产物响应增加 `Access-Control-Allow-Origin` 与长缓存头
4. `/api/manifest` 始终不缓存（它是版本索引）

### 变更对外契约总结

| 项 | 旧 | 新 |
|---|---|---|
| HTML 加载 | 3 个 `<script>` + `MutguiApp.mount(...)` | 1 个 `<div data-mutgui-app data-ws-url=... data-plugins=...>` + 内联 import map / manifest JSON + 1 个 `<script src="boot.js">` |
| 全局对象 | `window.MutguiApp.*` / `window.MutguiThemeDark` | 无（全部走 ESM import) |
| 资源路径 | `/static/*.js` 平铺 | `/static/modules/<包名>/...` 按包隔离 |
| 后端依赖声明 | HTML 模板硬编码 | `ModuleRegistry.add_from_package(...)` |
| 第三方库共享 | bundle 进各自 IIFE | 独立 ESM 文件，import map 单例 |
| 构建命令 | `build`(npm 包形态）+ `build:standalone`(IIFE 三件套） | 单一 `npm run build`(vendor + libs + boot + manifest），产物不入 git |

下游项目（mutagent / mutbot / 第三方）本规范不动，仍可继续用旧的 IIFE 加载方式直到它们各自迁移。但 mutgui demo 自身切换到新机制后，旧 IIFE 文件（`mutgui.js` / `mutgui-antd.js` / `mutgui-theme-dark.js`）从 `src/mutgui/static/` 删除，下游若直接引用会失效--这是用户接受的范围。

## 消费者场景

| 消费者 | 场景 | 依赖的输出 | 本轮验收 |
|---|---|---|---|
| mutgui demo | `python -m demo` 启动后页面正常渲染（含 dark theme 切换、antd 组件） | boot.js + manifest 协议 + 三个 ESM lib | ✅ 必须 |
| mutgui standalone demo | `python demo/standalone/starlette.py` 同样工作 | 同上 | ✅ 必须 |
| mutagent | mutagent-ui 改造为 ESM lib，挂到 import map | build-preset + manifest 协议 | ❌ 本轮不做 |
| mutbot | 同上 | 同上 | ❌ 本轮不做 |
| 第三方扩展 | 写 `cool-ext` 包按模板接入 | build-preset + 项目模板 + 类型分发 | ❌ 本轮不做 |

下游迁移在 mutgui MVP 完成后单独立项。下游迁移期间它们暂时跑不起来是已接受的代价。

## 实施步骤清单

- [x] 更新 `feature-component-lib-extension.md` 的阻塞设计并完成自检：import map 生效时机、CSS 协议、plugin 选择规则收敛为单一方案
- [x] 新增 `mutgui.modules.ModuleRegistry`，支持读取包内 `static/manifest.json`、生成运行时 import map、输出静态挂载信息
- [x] 改造 `demo/framework/_routes.py` 与 `demo/standalone/starlette.py`：HTML 改为 mount div + import map + manifest JSON + boot.js，静态挂载切到 `/static/modules/<pkg>/`
- [x] 改造 `frontend` 构建链：新增 `src/boot.ts`、`src/core.tsx`、vendor/runtime lib 构建配置与 `scripts/build.mjs`
- [x] 生成 `src/mutgui/static/manifest.json` 与 runtime 产物，移除旧的 `mutgui.js` / `mutgui-antd.js` / `mutgui-theme-dark.js` 依赖路径
- [x] 改造 `@mutgui/antd` 与 `@mutgui/theme-dark` 为 ESM 入口，前者负责命名空间注册，后者默认导出 plugin
- [x] 更新 integration test 装配，切换测试 HTML 与静态路由到新协议
- [x] 同步更新 `docs/design/frontend-build.md`、`docs/design/framework-capabilities.md` 与 `feature-pluggable-component-libs.md`
- [x] 执行 `npm --prefix frontend run build`、`npm --prefix frontend run test`、`pytest --ignore=tests/integration`，并在浏览器中验证 `basic` / `antd` demo 正常渲染；全量 `pytest` 仍因环境缺少 `playwright` 在 collection 阶段中断

## 测试验证

- `npm --prefix frontend run build`
- `npm --prefix frontend run test`
- `pytest --ignore=tests/integration`
- 浏览器验收：`python -m demo` 下的 `basic` 与 `antd` 页面已确认走 import map + manifest + boot 协议并正确渲染

## 实现对齐说明

- `ModuleRegistry.runtime_manifest()` 现在会为导出的 JS/CSS URL 追加 `?v=<mtime_ns>`，用于浏览器缓存失效；因此 runtime import map 和 manifest 都是版本化 URL。
- runtime vendor 额外做了两层约束，保证浏览器端单实例行为成立：
  - React / ReactDOM client / jsx-runtime / antd 都以 ESM vendor 形式单独输出
  - `antd` 与 `react-dom/client` vendor 对 `react` 保持 external，避免重复打包出第二份 React 实例

## 关联文档更新

实施完成后同步更新：

- `mutgui/docs/design/frontend-build.md` - **整体重写**，按新机制描述：
  - 不再有“两种构建模式”(IIFE/npm 包），只有一种 ESM lib 形态
  - “在 mutgui 之上做组件库” 章节用 `defineLib` + manifest.json 替代洋葱式 external
  - “加载顺序” 章节由 import map + boot.ts 协议替代
  - 新增“开发期工作模式”和“路径与隔离”章节
  - 移除“已知局限”章节
- `mutgui/docs/design/framework-capabilities.md` - 检查是否提到 `MutguiApp.*`，相应改写
- `mutgui/docs/specifications/feature-pluggable-component-libs.md` - 命名空间注册机制不变，但底层加载机制相关描述更新
