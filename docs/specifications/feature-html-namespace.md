# 组件解析增强：HTML 命名空间与 Fallback 控制

**状态**：✅ 已完成
**日期**：2026-06-17
**类型**：功能设计

## 需求

1. **关闭单段名字 fallback** — 当前 `resolve("div")` 未命中后返回字符串 `"div"`，由 `React.createElement("div", ...)` 渲染原生 HTML。这个隐式 fallback 应移除，强制所有组件使用命名空间前缀。
2. **新增 `html` 命名空间** — 通过 `html.div`、`html.pre` 等方式访问原生 HTML 元素和 Web Components，语义明确且有命名空间的可控性。
3. **`html` 作为可选控件库** — 加载 `@mutgui/html` 才启用，后端项目可控制。不加载时 `html.*` 不可用。
4. **新增动态命名空间接口** — `html` 是"无穷"标签集合（原生 100+ 标签 + 任意 Web Components），不适合枚举注册。需提供与 `registerComponents` 平级的、基于映射函数的命名空间注册方式。

## 设计方案

### 核心接口

两个注册 API 平级，共享内部解析链但独立存储：

```typescript
// 已有 — 枚举组件库（antd、用户自定义）
function registerComponents(source: ComponentSource): void;

// 新增 — 动态命名空间（html 等需要无穷标签映射的场景）
function registerNamespace(
  name: string,
  resolveFn: (key: string) => string | ComponentType | null,
): void;
```

### resolve 返回值语义变更

| 名字 | 当前 | 方案 A（本次） |
|------|------|---------------|
| `antd.Button` | Button 组件 | 不变 |
| `html.div` | （不存在） | `'div'` → React.createElement('div') |
| `html.my-button` | （不存在） | `'my-button'` → Web Component |
| `div` | `'div'`（fallback） | **`null`**（不渲染，日志可见违规） |

**实现**：`resolve` 返回值类型从 `ComponentType | string` 改为 `ComponentType | string | null`。`null` 表示未解析，渲染器跳过该节点。

### registerNamespace 实现策略

`registerNamespace` 不与 `resolveFromSources` + `walk` 共享解析路径。它走独立路径：

```
resolve("html.div")
  → 遍历 namespaces 列表，匹配前缀 "html"
  → 切出 key = "div"
  → 调用 resolveFn("div")
  → 返回 'div'
```

`walk` 逻辑（按 `.` 逐层穿透对象）仅用于 `registerComponents` 的枚举源，嵌套对象穿透（如 `antd.Form.Item`）仍正常工作。

### html 命名空间的默认实现

```typescript
registerNamespace('html', (key) => key);
// key 原样作为 HTML 标签名 — 原生标签（div, pre, span...）和 Web Components（date-picker, my-widget...）全覆盖
```

### html 独立 entry，需显式加载

`html` 不打包进 `mutgui-core`，作为独立 runtime entry `@mutgui/html`，项目必须显式 `runtime.import("@mutgui/html")` 才能用 `html.*`。mutgui-core 保持纯粹——只含渲染器核心，不预设任何控件库。

### 不留 bare name 白名单

关闭 fallback 后，`div`、`pre` 等单段名字统一不可用。所有原生 HTML 元素必须通过 `html.*` 访问。不留白名单，规则一致。

### 构建与分发

- `html` 注册代码打包进 `mutgui-core`（代码量 ~15 行，不占体积）
- 保留独立的 `@mutgui/html` runtime entry（`libs/mutgui-html.js`），项目可选的加载
- `mutgui.build.mjs` 新增 runtime entry：
  ```javascript
  {
    importName: '@mutgui/html',
    entry: 'src/integrations/html.ts',
    outFile: 'mutgui-html.js',
    peers: ['@mutgui/core'],
    kind: 'lib',
  }
  ```

### 解析失败时向前端推送错误事件

后端不做组件名校验——`_view_impl.py` 将 `$component` 字段原封不动序列化到 JSON。

前端 `resolve` 返回 null 时，通过 Channel 将错误推回后端日志：

```typescript
// renderer.tsx — MutguiComponent
if (!resolved) {
  conn.send(JSON.stringify({
    type: "render.error",
    component: schema.$component,
    source: [...scope, schema.$id],
  }));
  return null;
}
```

后端打印 warning 日志，无需新增协议——与现有的用户事件走同一 Channel：

```python
elif msg["type"] == "render.error":
    logger.warning("组件解析失败: %s (source=%s)", msg["component"], msg["source"])
```

无时序问题：`boot.ts` 消息处理是 Promise 链串行，`await importModule` 执行完 `registerNamespace` 后才处理渲染树消息，namespace 在 resolve 之前已注册完毕。

```python
# mutagent/_server.py — 加载 html 的项目
{"type": "runtime.import", "module": "@mutgui/html"}

# 不加载的项目 — html.* resolve 失败 → 后端日志报 warning
```

## 关键参考

- `mutgui/frontend/src/core/registry.ts` — `registerComponents`、`resolve`、`ComponentSource` 声明
- `mutgui/frontend/src/core/namespaced-registry.ts` — `resolveFromSources`、`walk`、`NamespacedSource` 声明
- `mutgui/frontend/src/core/renderer.tsx` — `MutguiComponent`、`processProps`、返回值的消费方式
- `mutgui/frontend/src/integrations/antd.ts` — 枚举组件库注册示例
- `mutgui/frontend/mutgui.build.mjs` — 构建配置（vendors、runtimes）
- `mutgui/src/mutgui/modules.py` — ModuleRegistry 声明
- `mutgui/src/mutgui/_modules_impl.py` — ModuleRegistry 实现、manifest 聚合
- `mutgui/frontend/src/boot.ts` — runtime.import 消息处理

## 消费者场景

| 消费者 | 场景 | 依赖的输出 | 验收标准 |
|--------|------|-----------|---------|
| mutagent | 迁移 ~102 处 `div` / `pre` → `html.div` / `html.pre` | `html` 命名空间可用、bare name fallback 关闭 | 所有页面正常渲染，无 `div`/`pre` bare name 遗留 |
| mutbot | 同上迁移 | 同上 | 同上 |

## 待定问题

（无 — 所有问题已确认并融入设计方案）

## 实施步骤清单

### 阶段一：mutgui 框架层

- [x] `registry.ts` — 新增 `registerNamespace`，`resolve` 关闭 bare name fallback（返回 `ComponentType | string | null`）
- [x] `renderer.tsx` — `resolve` 返回 `null` 时推送 `render.error`（component 名 + source 路径）
- [x] 新建 `integrations/html.ts` — `registerNamespace('html', key => key)`
- [x] `core.tsx` — 导出 `registerNamespace`
- [x] `mutgui.build.mjs` — 新增 `@mutgui/html` runtime entry
- [x] `_viewport_impl.py` — `view_port_handle_event` 拦截 `render.error` 打印 warning
- [x] `src/index.ts` — 公开 API 同步导出 `registerNamespace` / `NamespaceResolver`
- [x] 构建产物 — `npm run build` 生成 `mutgui-html.js`，manifest 注册 `@mutgui/html`

### 阶段二：下游适配

- [x] mutgui demo / test — bare name 迁移为 `html.*`（220 处），`DEFAULT_RUNTIME_IMPORTS` 加入 `@mutgui/html`
- [x] mutagent — bare name 迁移为 `html.*`（107 处），`_runtime_messages` 加入 `runtime.import("@mutgui/html")`
- [x] mutbot — bare name 迁移为 `html.*`（2 处），`setup/index.tsx` 加入 `registerNamespace('html', key => key)`
- [x] 全量测试通过 — mutgui 246 ✅，mutgui 前端 47 ✅，mutagent 726 ✅
