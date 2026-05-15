# 浏览器系统事件通道 + Hash 导航原语

**状态**：✅
**日期**：2026-05-15
**类型**：功能设计

## 需求

1. 后端需要能控制浏览器 URL hash（程序化导航），与现有 `mutgui.redirect` / `mutgui.history` / `mutgui.reload` 同级，作为「浏览器导航原语的后端触发入口」。
2. 浏览器自身的全局事件（首先是 `hashchange`）需要回传到后端，让后端能响应用户点 back/前进、手动改 hash、新标签页直接打开带 hash 的 URL。
3. 这两个能力是 SPA 路由的通用基础设施，**不应**把"路由表/页面映射"等应用语义放进 mutgui，应用层（如 mutagent）按需自己拼装路由策略。
4. 双向同步必须**没有循环风险**，且**没有时序窗口**：不依赖任何标记位、setTimeout 清除等机制。

## 关键参考

- `frontend/src/core.tsx` — `createConnection` + `registerCommands`，命令通道与 WS 收发的入口
- `frontend/src/core/commands.ts` + `core/namespaced-registry.ts` — 命令命名空间解析（`mutgui.<name>` 走 `__name__: 'mutgui'` 源）
- `frontend/src/core/navigation.ts` — 现有 `runRedirectCommand` / `runHistoryCommand` / `runReloadCommand`，新原语放这里
- `src/mutgui/_view_impl.py` `_route_event` — 事件按 source 数组逐层路由；`source: []` 命中根 View，`event.component_id == ""`
- `src/mutgui/events.py` — `Event` / `EventFilter` / `EventHandler`，根级事件由 View.on_event 处理
- `tests/integration/test_command_channel.py` — 现有 redirect/history/reload 集成测试模板
- `docs/specifications/feature-navigation-commands.md`（✅ 已完成）— 内置导航命令的范围约定，本设计延续同一原则

## 设计方案

### 总体职责切分

mutgui 提供两件事，**都是原语，不带任何应用语义**：

1. **`mutgui.setHash` 命令**：后端 → 前端单向，调用 `history.pushState` / `replaceState` 修改当前 URL 的 hash，**不**手动触发任何事件。
2. **浏览器系统事件回传**：前端 → 后端单向，把 `hashchange` 包成框架级事件 `$hashchange`（`source: []`）发给后端 root View。

应用层（mutagent 等）：监听 `$hashchange`、维护自己的"当前路由"状态、在状态变化时调 `send_command("mutgui.setHash", ...)`。**mutgui 不感知 route 概念**。

#### 前向兼容备注（多应用 shell 容器愿景）

本期实现服务于**单 mutgui 应用占据整个浏览器入口**的场景。未来 mutbot 可能演化为基于 mutgui 的 shell 容器，把多个 mutgui 应用（含 mutagent）嵌入同一入口（详见 `feature-multi-app-shell-container.md`）。届时浏览器全局唯一的 hash 与 root View 事件入口要被多个 sub-app 分时复用，需要在原语之上叠加一层路由容器（即 Q2 提到的 `RouterView` 抽象）。

为此本期实现保持以下"开放性约束"：

- `runSetHashCommand` 实现保持纯粹——只接受 hash 字符串，**不**引入"全局 = 调用者意图"的隐式契约。未来 shell 拦截层可以在命令 dispatch 之前重写 hash 字符串。
- `NavigationRuntime.pushState` / `replaceState` 接口签名保持"接受完整 url 字符串"，不绑定调用者身份，便于未来按子段重映射。
- 后端 `_route_event` 对 `source: []` 的处理保持"路由到 root View"的简单语义，不内嵌"root 一定是某种应用 View"的假设。未来 root 是 `AppContainer` 容器时，由它负责把 `$hashchange` 拆段派发到 active sub-app，mutgui 后端无需改动。

**本期不为此改动任何代码**，仅在文档里显式声明：当前"Conversation 是 root、独占整个 hash"的形态是单应用便利路径，不是永久契约。

### 防循环：W3C 规范天然保证

`history.pushState` / `replaceState` **不**触发 `hashchange` 也不触发 `popstate`。这是 W3C 规范明确规定的行为。

利用这一点：

- 后端发 `mutgui.setHash` → 前端 `pushState` → 浏览器 URL 变了 → **没有任何事件触发** → 不会回传 → 不会循环 ✓
- 用户点 back/前进跨 hash 项 → `hashchange` 触发（同时也会触发 `popstate`，但本期不监听 `popstate`）→ 回传后端 → 后端更新状态 ✓
- 用户手动改地址栏 hash → `hashchange` 触发 → 回传后端 → 后端更新状态 ✓

**关键约束**：`runSetHashCommand` 内部**禁止**手动 `dispatchEvent('hashchange')`，否则就主动制造循环。其他三种"防循环机制"（标记位、setTimeout、内部方法不发命令）一概不需要，源头就没有循环。

### `mutgui.setHash` 命令

文件：`frontend/src/core/navigation.ts`

```typescript
// 把用户传入的 hash 字符串规范化为「pathname + search + #...」完整 URL。
// 直接 pushState(hash) 会被当成相对 URL 解析（例如 "settings" 会替换 pathname 末段），
// 必须显式拼成绝对 URL 才能保证只动 hash、不动 pathname/search。
function normalizeHashUrl(hash: string): string {
  const base = location.pathname + location.search;
  if (hash === "") return base;                       // 清空 hash，导航到 pathname
  if (hash.startsWith("#")) return base + hash;       // 已带 # 前缀
  return base + "#" + hash;                           // 自动补 #
}

export function runSetHashCommand(
  { hash, replace }: { hash: string; replace?: boolean },
  runtime: NavigationRuntime = browserNavigation,
): void {
  const url = normalizeHashUrl(hash);
  if (replace) runtime.replaceState(url);
  else runtime.pushState(url);
}
```

**规范化语义**（与 Q4 对齐，写入主体而非待定）：
- `"#/foo"` → `pathname + search + "#/foo"`
- `"foo"` → `pathname + search + "#foo"`（自动补 `#`）
- `""` → `pathname + search`（清空 hash）
- 永远不动 pathname / search，需要改这两段请用 `mutgui.redirect`。

`NavigationRuntime` 接口扩展两个方法：

```typescript
export interface NavigationRuntime {
  assign(url: string): void;
  replace(url: string): void;
  go(delta: number): void;
  reload(): void;
  pushState(url: string): void;     // 新增
  replaceState(url: string): void;  // 新增
}

const browserNavigation: NavigationRuntime = {
  // ... existing ...
  pushState(url) { window.history.pushState(null, '', url); },
  replaceState(url) { window.history.replaceState(null, '', url); },
};
```

在 `core.tsx` 的 `registerCommands` 里追加：

```typescript
registerCommands({
  __name__: 'mutgui',
  redirect: ...,
  history: ...,
  reload: ...,
  setHash: (args: { hash: string; replace?: boolean }) => runSetHashCommand(args),
});
```

参数语义：
- `hash`：完整的 hash 字符串，含或不含 `#` 前缀均被接受（实现内部规范化为 `#...`）。空字符串 `""` 等价于清除 hash（导航到 `pathname`）。
- `replace`：缺省 `false`，走 `pushState` 留下历史记录；`true` 走 `replaceState` 不留记录。

**命名决策**：保持 `setHash({hash, replace})` 单一命令而非拆 `pushHash` / `replaceHash` 两命令，与现有 `mutgui.redirect({url, replace})` 风格一致；`replace` 缺省值合理（push），调用点几乎不会显式写 `replace=False`，bool 参数不会成为可读性负担。

**为什么不复用 `mutgui.redirect` 处理 hash**：`location.assign("#/foo")` 会触发 `hashchange` 事件，破坏「防循环靠 W3C 天然行为」的核心约束。`setHash` 必须走独立的 `pushState` / `replaceState` 通道，不可与 `redirect` 合并。

**作用域决策**：本命令只改 hash，永远不动 pathname / search。需要改 pathname 请用 `mutgui.redirect`（整页导航）。`pushState` 的原生签名虽然能接受完整 url，但同时改 pathname + hash 的场景在 mutgui 后端驱动模型下很少出现（pathname 切换基本意味着切应用），把这两类操作分离让命令意图更清晰。

### 浏览器系统事件通道

新增文件：`frontend/src/core/system-events.ts`

```typescript
// 浏览器全局事件 → 后端的统一通道。
// 与 View 组件事件区分：source 为 [] 表示框架级，event 名以 $ 前缀。
export function setupSystemEvents(
  sendRaw: (data: string) => void,
): () => void {
  const sendSystemEvent = (name: string, data: Record<string, unknown>) => {
    sendRaw(JSON.stringify({ source: [], event: `$${name}`, data }));
  };

  const onHashChange = (e: HashChangeEvent) => {
    const previousHash = new URL(e.oldURL).hash;
    sendSystemEvent('hashchange', {
      hash: location.hash,
      previousHash,
      cause: 'user',
    });
  };

  window.addEventListener('hashchange', onHashChange);

  return () => {
    window.removeEventListener('hashchange', onHashChange);
  };
}
```

设计要点：

- **只监听 `hashchange`，不监听 `popstate`**：W3C 规定用户 back/前进跨 hash 历史项时会**先后**触发 `popstate` 和 `hashchange`，两者都监听会重复发事件；同时本期只支持 hash 路由（pathname 路由会引起整页刷新，与 mutgui 后端驱动模型冲突），`popstate` 在此场景下是 `hashchange` 的真子集，没有独立信号。未来引入 pathname 路由（或 `pushState` 携带 state 数据）时再追加独立的 `$popstate` 事件，data 带 `pathname` / `state` 字段。
- **`$` 前缀**：标识"框架级保留事件"，与应用层 View 自定义事件名分隔。未来追加 `$resize` / `$online` 等遵循同一约定。
- **`source: []`**：路由到 root View 的 `on_event`，`event.component_id == ""`。后端根 View 的 `on_event` override 通过 `event.name == "$hashchange"` 匹配处理。
- **没有运行期补发初始 hash**：初始 hash 通过 `mount.attach` 握手字段带给后端（见下节），不在 `setupSystemEvents` 内部 `queueMicrotask` 补发，彻底消除"首屏 render 与 $hashchange 谁先谁后"的时序依赖。

**事件 `data` 字段**：

| 字段 | 类型 | 语义 |
|------|------|------|
| `hash` | `string` | 当前 `location.hash`，可能为 `""`（hash 已被清空） |
| `previousHash` | `string \| null` | 上一次的 hash 值。`cause="user"` 时一定存在（来自 `HashChangeEvent.oldURL` 的 hash 部分，可能为 `""`）；`cause="initial"` 时为 `null` 或字段缺失（首次入口没有"上一次"）。**为什么不用 `""` 表示"无 previous"**：`""` 是合法 hash 值（清空 hash），不能复用作哨兵 |
| `cause` | `"user" \| "initial"` | `"user"`：运行期事件（back/前进、手动改地址栏）；`"initial"`：首屏入口路径（见下节握手约定）。**枚举字段**，未来扩展只追加新值，老值语义不变；应用层据此区分滚动恢复、埋点、首次进入逻辑等场景 |

把 `previousHash` 下沉到原语层而非让应用自己缓存，是因为：(1) 浏览器原生事件已携带 `oldURL`，前端零成本；(2) 避免每个根 View 都重复实现 `useRef(prev)` 缓存；(3) WS 重连时后端缓存重建复杂，原语层统一约定 `initial → previousHash=null` 让应用少踩边界坑。

### 初始 hash 通过 `mount.attach` 握手传递

在前端首次发出的 `mount.attach` 消息中追加 `client` 容器，承载初始 hash 等浏览器侧握手字段：

```json
{ "type": "mount.attach", "viewportId": ..., "client": { "hash": "#/settings/llm" } }
```

**为什么用 `client` 嵌套容器而非 flat `initialHash`**：本期只有 hash 一个字段，但浏览器侧握手字段必然增长（viewport 尺寸、时区、`prefers-color-scheme`、UA hints 等）。从一开始就放进 `client` 容器，未来扩展不需要再迁一次协议。

后端 `viewport.initialize()` 拿到 `client.hash` 后，在首次调用 root View 的 `on_event` 之前合成一条等价事件（不走 wire，直接路由；走与 wire 事件相同的 `_route_event` 路径以保证 EventFilter 链一致）：

```json
{ "source": [], "event": "$hashchange",
  "data": { "hash": "#/settings/llm", "previousHash": null, "cause": "initial" } }
```

这样首屏 render 已经能拿到正确路由状态，无须依赖 deferred render 的合并兜底。WS 重连时同样走这条路径，重连前后行为一致。

空 hash（`location.hash === ""`）也照常发送 `cause: "initial"` 事件（`hash: ""`、`previousHash: null`），让根 View 永远能在初始化时拿到一次入口信号，不必区分"有没有 hash"。

（备选方案 `queueMicrotask` 补发 + 依赖 deferred render 合并被否决：首屏会先用空 route 渲染一遍再被覆盖，语义混浊；握手字段方案协议成本低、收益明确。）

### `core.tsx` 接入

`createConnection` 内部启动系统事件监听，返回值新增 `teardown`：

```typescript
export function createConnection(sendRaw: (data: string) => void): RuntimeConnection {
  // ... existing subs/cache/handleMessage ...
  const teardownSystemEvents = setupSystemEvents(sendRaw);

  return {
    handleMessage,
    send: (data: string) => sendRaw(data),
    subscribe: ...,
    teardown: () => { teardownSystemEvents(); },
  };
}
```

`ConnectedApp` 在 `useEffect` 清理时调用 `connection.teardown()`，以便 HMR / 切换 wsUrl 时不泄漏 listener。`mountWithConnection`（外部传入 connection）的调用方负责自己 teardown，与现状一致。

### 与现有事件机制的契合

后端 `_route_event`（在 `_view_impl.py`）已经支持 `source` 数组。当 `len(source) == 0` 时（本设计就是这种情况），构造 `Event("", event_name, data)` 调 `view.on_event(event)`。根 View 的应用方（如 mutagent.Conversation）只需 override `on_event` 拦截 `name == "$hashchange"` 即可。

**前置依赖**：根级 EventFilter 链补丁，见 [`bugfix-root-event-filter-chain.md`](./bugfix-root-event-filter-chain.md)。当前 `_route_event` 在 `len(source) == 0` 分支跳过 filter 链，与「filter 通过率 = 是否到达 on_event」的语义文档不符。本设计承诺「根 View 上的 EventFilter 能拦截 `$hashchange`」依赖该 bugfix 落地（含首屏合成事件路径）。

### 后端 `send_command` 的使用

应用层调用方式与现有命令一致：

```python
# 在某个 View 内，事件处理上下文中
await self.send_command("mutgui.setHash", hash="#/settings/llm")
await self.send_command("mutgui.setHash", hash="#/", replace=True)
```

`send_command` 已实现，无需改动 mutgui 后端。

### 协议：wire 消息示例

后端 → 前端（命令）：
```json
{ "type": "command", "viewId": [], "name": "mutgui.setHash",
  "args": { "hash": "#/settings/llm" } }
```

前端 → 后端（运行期 hashchange 事件）：
```json
{ "source": [], "event": "$hashchange",
  "data": { "hash": "#/settings/llm", "previousHash": "#/", "cause": "user" } }
```

前端 → 后端（mount.attach 握手）：
```json
{ "type": "mount.attach", "viewportId": ..., "client": { "hash": "#/settings/llm" } }
```

后端在 `viewport.initialize()` 内合成（不走 wire，直接路由；`previousHash: null` 表无前驱）：
```json
{ "source": [], "event": "$hashchange",
  "data": { "hash": "#/settings/llm", "previousHash": null, "cause": "initial" } }
```

### 影响范围

| 文件 | 改动 |
|------|------|
| `frontend/src/core/navigation.ts` | 新增 `runSetHashCommand` + `normalizeHashUrl`；`NavigationRuntime` 加 `pushState`/`replaceState` |
| `frontend/src/core/system-events.ts` | 新文件 ~25 行，仅监听 `hashchange`，事件 data 含 `hash` / `previousHash` / `cause` |
| `frontend/src/core.tsx` | `registerCommands` 追加 `setHash`；`createConnection` 调 `setupSystemEvents`，返回值加 `teardown`；`mount.attach` 消息追加 `client.hash` 嵌套字段 |
| `frontend/src/core/context.tsx` | `MutguiConnection` 接口可选追加 `teardown?: () => void`（向后兼容） |
| `src/mutgui/_viewport_impl.py`（或对应 mount.attach 处理处） | 解析 `client.hash` 字段；在 `viewport.initialize()` 首次 render 之前合成 `$hashchange (cause=initial, previousHash=null)` 事件，走与 wire 事件相同的 `_route_event` 路径 |
| `tests/integration/test_command_channel.py` | 新增 `setHash` 集成测试：push / replace / 规范化（裸串、带 #、空串、含 `?` 假 query 的 hash）四类 |
| `tests/integration/test_system_events.py` | 新文件。三种场景：(a) `mount.attach.client.hash` → 后端首次 on_event 收到 `cause=initial, previousHash=null`；(b) 模拟 `hashchange` → 后端收到 `cause=user, previousHash=<old>`；(c) `setHash` 后再 `history.go(-1)` 触发 `hashchange` 完整闭环 |
| `tests/test_command_channel.py` | 新增 `setHash` wire 消息 + URL 规范化单元测试 |

**前置依赖**（独立 PR）：`src/mutgui/_view_impl.py` 的 `_route_event` 根分支补 EventFilter 链，详见 [`bugfix-root-event-filter-chain.md`](./bugfix-root-event-filter-chain.md)。

### 兼容性

- `redirect` / `history` / `reload` 命令行为不变，只是 `NavigationRuntime` 接口新增方法（runtime 实现是内部对象，无外部依赖）。
- 既有应用未注册 `$hashchange` 处理的话，事件抵达 root View 的 `on_event` 默认实现会查找 `(component_id="", event_name="$hashchange")` 的 handler，找不到就静默返回 False（见 `_view_impl.view_on_event`），无副作用。
- `MutguiConnection.teardown` 是可选字段，老调用方不实现也能正常工作。

## 设计决策记录

### 暂不提供 RouterView 抽象

mutgui 当前只暴露 `mutgui.setHash` 命令 + `$hashchange` 事件两个原语，**不**封装 `RouterView` 基类。原因：当前没有第二个消费方需要 SPA 路由，YAGNI。等 mutbot / demo 出现真实用例再抽。

**Reopen 触发条件**：mutbot 演化为多应用 shell 容器立项时（详见 `feature-multi-app-shell-container.md`）。届时 `RouterView` 不仅承担单应用路由，还要按 hash 子段把事件派发到挂载的 sub-app，是嵌入能力的核心抽象。

## 消费者场景

| 消费者 | 场景 | 依赖的输出 | 验收标准 |
|--------|------|-----------|---------|
| mutagent SettingsPage 路由 | Conversation 监听 `$hashchange` 切换页面 | `$hashchange` 事件 + `mutgui.setHash` 命令 | back/前进/复制 URL 在新 tab 打开均无整页刷新；WebSocket 不断连 |
| 未来 SPA 应用 | 任何需要 hash 路由的 mutgui 应用 | 同上 | 复用 mutgui 原语，应用层只写自己的 route 解析与状态映射，不改 mutgui |
| mutgui 集成测试 | 验证握手 `client.hash` / 运行期 hashchange / pushState 后用户后退 | `$hashchange` 后端可观察 | 三种场景后端都只收到一次事件：(a) 首屏带 hash 加载→`cause=initial, previousHash=null`；(b) 用户改地址栏→`cause=user, previousHash=<old>`；(c) `setHash` 后 `history.go(-1)` →`cause=user`（不会因 popstate 重复） |

## 实施步骤清单

### 前端：导航命令扩展

- [x] `frontend/src/core/navigation.ts`：扩展 `NavigationRuntime` 接口加 `pushState` / `replaceState`，`browserNavigation` 实现两个新方法
- [x] `frontend/src/core/navigation.ts`：实现 `normalizeHashUrl` + `runSetHashCommand`（覆盖三种规范化分支：裸串、带 `#`、空串；`normalizeHashUrl` 接受可注入的 `LocationBase` 以便无 jsdom 单测）
- [x] `frontend/src/core.tsx`：`registerCommands` 追加 `setHash`

### 前端：系统事件通道

- [x] 新建 `frontend/src/core/system-events.ts`：监听 `hashchange`，封装为 `$hashchange` 事件（`source: []`），data 含 `hash` / `previousHash` / `cause`，返回 teardown 函数
- [x] `frontend/src/core/context.tsx`：`MutguiConnection` 接口可选追加 `teardown?: () => void`
- [x] `frontend/src/core.tsx`：`createConnection` 调 `setupSystemEvents`，把返回的 teardown 通过 `RuntimeConnection.teardown` 暴露
- [x] `frontend/src/core.tsx`：`ConnectedApp` 的 `useEffect` cleanup 调用 `connection.teardown?.()`，避免 HMR / wsUrl 切换泄漏 listener

### 前端：mount.attach 握手扩展

- [x] `frontend/src/boot.ts`：发送 `mount.attach` 时追加 `client: { hash: location.hash }` 嵌套字段

### 后端：初始 hash 处理

- [x] `src/mutgui/viewport.py`：`ViewPort.__init__` 增加关键字参数 `_client: dict[str, Any] | None = None`
- [x] `src/mutgui/_viewport_impl.py`：`ViewPortRuntime` 增加 `client` 字段；`viewport_initialize` 在首次 render 之前合成一条 `$hashchange` 事件（`source: []`、`cause: "initial"`、`previousHash: null`），走与 wire 事件相同的 `view.handle_event` / `_route_event` 路径
- [x] `demo/standalone/starlette.py` / `demo/framework/_server.py` / `tests/integration/conftest.py`：解析 `mount.attach.client` 字段并传入 `ViewPort(_client=...)`；WS 重连场景同走该路径

### 测试

- [x] `frontend/tests/builtin-navigation-commands.test.ts`：新增 `setHash` 单元测试 + `normalizeHashUrl` 四类规范化（裸串、带 `#`、空串、含 `?` 假 query）以及 push/replace 分支
- [x] `tests/test_command_channel.py`：新增 `setHash` wire 消息单元测试
- [x] `tests/integration/test_command_channel.py`：新增 `setHash` 集成测试（push / replace / 裸串规范化 / 空串清空）
- [x] 新建 `tests/integration/test_system_events.py`：三种场景
  - [x] (a) `mount.attach.client.hash` → 后端首次 on_event 收到 `cause=initial, previousHash=null`（带 + 不带初始 hash 两用例）
  - [x] (b) 模拟 `hashchange` → 后端收到 `cause=user, previousHash=<old>`
  - [x] (c) `setHash` 后再 `history.go(-1)` 触发 `hashchange` 完整闭环（验证 popstate 不会引起重复事件；setHash 本身不产生 $hashchange）

### 兼容性与回归

- [x] 既有应用未注册 `$hashchange` handler 时，事件抵达根 View on_event 默认实现静默返回 False（未注册者零副作用验证：14 个集成测试 + 222 个后端单测全过）
- [x] `redirect` / `history` / `reload` 命令行为不变，`tests/integration/test_command_channel.py` 原有用例全过

### Demo 示例（人工验收用）

补一个能在浏览器肉眼跑通整条链路的示例，与 `demo/examples/command.py` 形成对照：`command.py` 演示「整页导航命令」（redirect/history/reload，每跳一次都换 pathname、断 WS 重连），`hash_nav.py` 演示「页内 hash 路由」原语（单 ViewPort、单 WebSocket、不重连，纯靠 `mutgui.setHash` + `$hashchange` 切换段）。

**文件**：`demo/examples/hash_nav.py`，单 `MutguiRoute("/", HashNavView())`，gallery 自动扫描收录。

**View 设计**：

- 状态：`self._hash`（最近一次的 hash 字符串）、`self._log`（最近 N 条 `$hashchange` 记录）。
- `on_event` 拦截 `event.component_id == "" and event.name == "$hashchange"`：写日志、更新 `self._hash`、`invalidate()`；其它事件 `super().on_event(event)` 走默认按钮 handler 分派。
- 按钮区：`Section A/B/C`（`setHash(hash="#/section/x")`，push）、`→ A (replace)`（`replace=True`）、`清空 hash`（`hash=""`）。
- 中部根据 `self._hash` 派发出 A / B / C / 空 四种内容块。
- 底部事件日志（最新在上），每行展示 `cause` + `previousHash` + `hash`。
- `render_viewport` 注入 `channel_id`，配文字「channel_id 全程不变 → WS 没有重连」给观察者。

**三条肉眼验收路径**（与「消费者场景」表里的集成测试三个 case 一一对应）：

1. **防循环**：点 `Section B` → 地址栏变 `#/section/b`，事件日志**不**新增条目（`setHash` 不触发 `hashchange`）。
2. **双向**：浏览器后退 → 日志新增 `cause=user, prev=#/section/b, now=#/section/a`，中段切回 A。
3. **首屏握手**：新标签页直接打开 `/#/section/c` → 首屏即 C 段，日志首条 `cause=initial, prev=null, now=#/section/c`。

**与 `command.py` 不复用代码**：两个 example 各自自包含（`_replace_children` 这类小工具就近内联），避免在 demo 间产生隐式依赖。两者并列在 gallery 的 Examples 段，标题足以引导观察者比较。

- [x] 新建 `demo/examples/hash_nav.py`，gallery 自动扫描收录
- [x] 人工验收三条路径（用户在浏览器跑）

### 构建与归档

- [x] `npm --prefix frontend run build` 构建前端，更新 `frontend/dist/` 与 `src/mutgui/static/`
- [x] 全量 `pytest` 通过（单元 222 + 集成 14）
