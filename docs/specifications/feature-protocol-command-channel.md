# Protocol Command Channel — 后端到前端的副作用通道

**状态**：✅ 已完成
**日期**：2026-04-26
**类型**：功能设计

## 需求

mutbot 在 setup wizard 中实现了 `mutbot.Redirect` 自定义组件（`mutbot/frontend/setup/Redirect.tsx`，8 行 React + `useEffect`），用于在后端驱动的 mutgui View 中触发浏览器跳转 URL。

继续往下推会发现，类似"让前端做某个动作"的需求是一类，不止 redirect：

- 整页跳转 / 跳转回首页（OAuth 完成后）
- 设置 `document.title`
- 复制到剪贴板
- 滚动到指定位置 / focus 某元素
- 触发 Notification 权限请求
- 触发文件下载
- `window.open` 新开标签页
- 关闭当前 tab
- 倒计时 + 延迟跳转
- 全屏 / 退出全屏

这些**都不是"UI 长什么样"**，而是**"请前端执行某个动作"**。当前协议只有 render（声明 UI）一类下行消息，缺少表达"副作用指令"的位置。

应用层（mutbot 等）现在的处置方式是把每个副作用包装成"渲染零像素 + `useEffect` 触发副作用"的伪组件，然后注册到自定义命名空间。这条路有几个根本性问题：

1. **哲学冲突**：组件树语义是"长什么样"，伪组件硬塞进去后整棵树不再是纯描述
2. **组件命名空间膨胀**：每个副作用一个伪组件，且都得在前端单独 import + register
3. **幂等性管理负担**：`useEffect` 的 deps 数组要业务自己管。同样 props 重渲染时该不该再触发？组件方案下要靠每个伪组件自己防
4. **重连重放问题**：Connection 重连时后端会重发最新的 render tree，伪组件会重新挂载导致副作用再触发一次（OAuth 跳转被重复触发等）
5. **编辑器自举不友好**（探索文档信号 31/32）：未来要做可视化编辑器编辑 mutgui UI 数据时，组件树里出现"空白节点 + 跳转副作用"是怪的

## 关键参考

### mutbot 侧（现有伪组件实现）
- `mutbot/frontend/setup/Redirect.tsx` — 当前组件本体（8 行）
- `mutbot/frontend/setup/index.tsx` — `registerComponents({ __name__: 'mutbot', Redirect })` 注册位置
- `mutbot/src/mutbot/auth/setup_view.py:260-264` — 后端 `_render_redirecting` 输出 `{"$component": "mutbot.Redirect", "url": ...}`
- `mutbot/frontend/src/App.tsx:410` — `setTimeout(() => { window.location.href = redirect; }, 100);` 等其他散落的纯前端副作用代码

### mutgui 侧
- `mutgui/src/mutgui/_viewport_impl.py:145` — 唯一的 `channel.send({"type": "render", ...})` 位置，新增 command 消息类型在此对称扩展
- `mutgui/src/mutgui/channel.py` — `Channel.send(message: dict)` 协议层抽象，传 `{"type": "command", ...}` 即可，不需要改 Channel 接口
- `mutgui/src/mutgui/events.py` — 上行 Event 路由实现，下行 Command 设计参考其对偶
- `mutgui/frontend/src/standalone.tsx:73` — 前端 message 派发位置（当前只处理 `msg.type === 'render'`），新增 command 分支
- `mutgui/frontend/src/core/registry.ts` 附近 — `registerComponents` API 定义位置，`registerCommands` 在此对称添加
- `mutgui/frontend/src/core/resolve-path.ts` — 现有的"前端表达式萌芽"，未来 Step 2 会跟它统一

### 设计探索背景
- `mutgui/docs/explorations/2026-04-15-protocol-layer-design-exploration.md` — 协议层设计探索，**信号 31/32（编辑器自举）**、**信号 34（LLM 友好）**、**主线 5（render+diff + 绑定共存）** 都直接影响本文档决策

## 设计方案

### 核心判断：Command 是 Event 的镜像

mutgui 协议有两个方向：

| 方向 | 上行（Event） | 下行（Command）— 本设计 |
|---|---|---|
| 触发者 | 用户操作 DOM | 后端业务逻辑 |
| 协议消息 | `{source, event, data}` | `{type: "command", viewId, name, args}` |
| 路由 | `View.on_event` 沿源路径下发 | viewport 沿目标路径下发到对应 MutguiView |
| 命名 | 事件名（`onChange`/`onClick`） | 命名空间.命令名（`mutgui.redirect`） |
| 扩展 | 后端 dispatch 自由 | `registerCommands({ __name__: "ns", ... })` |
| 注入上下文 | `@event` `@view`（后端注入） | command args 由后端预求值 |

**Command 在协议层的本质就是 "后端 → 前端 RPC"**，跟 Event "前端 → 后端 RPC（带 DOM 事件提取）" 严格对偶。spec 按对偶来组织，避免另起炉灶。

### 协议形态

下行 wire 消息：

```json
{
  "type": "command",
  "viewId": ["..."],
  "name": "mutgui.redirect",
  "args": {"url": "https://example.com", "replace": false}
}
```

字段说明：

- `type: "command"` — 与现有 `"render"` 平级的下行消息类型
- `viewId` — **必填**，目标 ViewPort 路径，与 render 消息的 `viewId` 同义。Step 1 只支持"当前 ViewPort"路由，但 wire 上仍显式携带此字段，与 render 消息形态对称，未来扩展跨 ViewPort 路由 / 广播时不需要改 wire 格式
- `name` — `"namespace.command"` 形式，与 `$component` 解析规则一致（命名空间查找 + 兜底）
- `args` — 命令参数，**Step 1 阶段只允许后端预求值的纯 JSON 值**（见"演化方向"章节关于未来表达式的考虑）

### 后端 API

ViewPort 提供 `send_command` 方法（与 `_vp_push_render` 对称）：

```python
class ViewPort:
    async def send_command(self, name: str, /, **args: Any) -> None:
        """触发前端命令。fire-and-forget，无返回值。"""
```

View 内部调用：

```python
class RedirectingView(mutgui.View):
    async def on_event(self, event):
        if event.name == "ready":
            await self.viewport.send_command("mutgui.redirect", url=self.target_url)
```

**只支持 `await` 的异步 API，不提供同步版本** —— 与现有 Channel.send 一致。

**fire-and-forget，无返回值**：当前已知用例（redirect、setTitle 等）都不需要前端执行结果。带返回值要引入请求 ID 匹配 + 超时 + 错误传播，复杂度跳一档。真有需求时（例如"读剪贴板内容"），未来另起 spec 加 `send_command_async` 之类扩展 API，不破坏 fire-and-forget 版本。

**不引入"自动响应式 command"** —— Command 永远是后端业务显式 `await send_command()` 的结果，不挂依赖追踪。Render 已经是"后端 state 变了自动推新 UI"的响应式通路，再多一条响应式 command 通路会破坏前端的幂等假设。

### 前端 API

与 `registerComponents` 完全对称的 `registerCommands`，**采用优先级栈，后注册优先**（与 registerComponents 解析链一致，应用可覆盖 core 命令，保持心智模型对称）：

```typescript
MutguiApp.registerCommands({
  __name__: 'mutgui',
  redirect: ({ url, replace }: { url: string; replace?: boolean }) => {
    if (replace) location.replace(url);
    else location.href = url;
  },
  setTitle: ({ title }: { title: string }) => {
    document.title = title;
  },
  // ... 后续按需扩展
});
```

派发：standalone.tsx 的 message handler 增加 command 分支，按 `name` 查命令注册表，调用对应函数，传入 `args`。

**未注册命令的处理**：warn-and-drop（`console.warn` + 忽略）。不报错以兼容版本不匹配场景（后端较新、前端较旧），不静默丢失避免调试困难。

### mutgui core 内置命令

第一批内置在 `mutgui` 命名空间下：

- `mutgui.redirect({url, replace?})` — 整页跳转，覆盖 mutbot 当前 Redirect 组件用例

其余命令（`setTitle`、`copyToClipboard`、`scrollTo` 等）**先不内置**，等出现实际用例再加。本 spec 起点只承诺 redirect 一个，避免一次设计太多。后续导航族扩展见 `docs/specifications/feature-navigation-commands.md`。

### 重放语义（与组件方案的关键差异）

Connection 重连时：

- **Render 消息**会按"最新 wire_tree"重发 —— 这是声明式的本质，需要重建 UI
- **Command 消息不重放** —— Command 是 fire-and-forget 的副作用指令，重发等于副作用重复触发

实现上：command 消息**不进入** ViewPort 的状态缓存（`render_state.wire_tree`），只在调用 `send_command` 当下发出去。如果前端不在线，这条命令就丢了 —— 这是预期行为（业务自己保证副作用在合适时机触发，例如响应一个上行事件之后）。

这是 command 协议比"伪组件 + useEffect" 干净的核心地方。

### 路由作用域

Step 1 范围内只支持一种路由：**当前 ViewPort**（即调用 `send_command` 的 View 所在的 viewport）。

`viewId` 字段标记目标 ViewPort 路径，前端按路径找到对应的 MutguiView 后，在该 scope 下调用命令处理函数。命令处理函数本身在前端的全局注册表（与组件相同），但接收消息时知道是"哪个 view scope 下发的"，未来如果命令需要操作局部 DOM 可以用上。

不支持的路由（暂定不做，等需求出现）：
- 广播给同一 View 的所有 ViewPort（多客户端同步动作）
- 跨 ViewPort 路由（一个 View 触发另一个 View 的客户端动作）
- 指定 Connection 路由

### 命名空间约定

与 `$component` 解析链复用心智模型：

- `mutgui.*` — core 内置命令
- `antd.*` — antd 插件附带命令（如有）
- `mutbot.*` / 应用自有命名空间 — 应用层自定义命令

## 待迁移项

mutbot 侧需要在 mutgui 核心 + Step 1 上线后跟进迁移，**不在本 spec 实施范围内**：

- `mutbot/frontend/setup/Redirect.tsx` — 删除
- `mutbot/frontend/setup/index.tsx` — 删除 `registerComponents({ __name__: 'mutbot', Redirect })`，按需追加 `registerCommands` 调用（如果要扩展自定义命令）
- `mutbot/src/mutbot/auth/setup_view.py` — `_render_redirecting` 改为不返回 Redirect 组件，而是在合适时机 `await viewport.send_command("mutgui.redirect", url=...)`
- `mutbot/frontend/src/App.tsx:410` 等散落的纯前端副作用 — 评估是否走 command 通道

## 演化方向（不在本 spec 实施范围）

本节预先点出几个明显的演化方向，**避免 Step 1 实现时把路堵死**。具体设计未来各自起独立 spec。

### Step 2：参数提取的统一表达式

`mutgui/frontend/src/core/resolve-path.ts` 现在的 `$0.target.value` / `$0.toHexString()` 已经是"前端表达式"的萌芽（DOM SyntheticEvent 不能整体序列化，必须前端先裁剪）。继续扩展会自然走向带参方法、算术、条件、模板字符串 —— 即一个完整 mini 表达式语言。

可预见的统一点：协议中引入受限的 `$expr` 标记，**事件提取、command 参数、render 数据**三处共用同一套语法基座，只是求值上下文不同：

| 面 | `$expr` 上下文 | 典型用途 |
|---|---|---|
| Event 提取 | event args（`$0`/`$1`） | 当前 resolvePath 的扩展 |
| Command 参数 | command args + 浏览器环境（`$window`/`$location`） | "scroll 到屏幕中央" 这类需要前端环境信息的命令 |
| Render 表达式 | view state（前端持有的本地状态） | QML 风格的纯前端绑定（探索文档主线 5） |

**红线**（必须遵守，否则退化为"前端 eval 任意代码"路线）：

- 不接受 JS 字符串 eval —— LLM 友好度（信号 34）和编辑器自举（信号 31/32）都要求格式可被反序列化和可视化
- 候选语法形态：JMESPath / JSONata 子集 / AST-JSON / 自研受限 DSL，未来 spec 选型
- 上下文按面差异化（Event 不允许引用 `$window`，Render 不允许引用 args 等），不一刀切开口子

### Step 3：纯前端联动绑定

Render 面引入 `$expr` + view state 的真正应用是"绑定" —— 例如颜色 R/G/B 滑块直接驱动预览色块、不走网络。这对应探索文档**主线 5（render+diff 保底 + 绑定优化共存）**和 NiceGUI / Vaadin 路线的落地点。

落地前提是 Step 2 的表达式语法已经稳定。本 spec 完全不触及。

### 不会演化的方向（明确排除）

- **后端 → 前端发送 JS 字符串让前端 eval**：违反 LLM 友好、自举可编辑、安全（多客户端共享 ViewPort 时一个客户端注入的代码会被推给所有其他客户端）多条原则，**不在任何 Step 范围内**
- **响应式 command（后端 state 变化自动推 command）**：破坏前端幂等假设，与 render 通路职责重叠，不做

## 实施步骤清单

### 后端（mutgui core）

- [x] 在 `mutgui/src/mutgui/_viewport_impl.py` 实现 `send_command` —— 构造 `{type:"command", viewId, name, args}` wire 消息，复用 `ext.channel.send`，不进 `render_state.wire_tree` 缓存
- [x] 在 `mutgui/src/mutgui/viewport.py` 的 ViewPort 声明上暴露 `async def send_command(self, name: str, /, **args: Any) -> None` API
- [x] View 侧便捷调用确认：View 在自身上下文中能拿到 viewport 引用并调用 send_command（必要时在 View 上加薄包装）
- [x] 单元测试：调用 `send_command` 后 channel 收到正确形态的 wire 消息（type / viewId / name / args 字段齐全）；多次调用顺序保持；不影响 render 消息流
- [x] 单元测试：command 消息**不**因 invalidate / 重连而被重发（验证不进缓存的语义）

### 前端（mutgui core）

- [x] 在 `mutgui/frontend/src/core/` 新增 command registry 模块 —— 与 `registerComponents` 对称的优先级栈，提供 `registerCommands(source)` 和 `resolveCommand(name)`
- [x] 在 `mutgui/frontend/src/standalone.tsx` 的 message handler 增加 `msg.type === 'command'` 分支：按 name 解析命令，调用 `cmd(args)`，未注册时 `console.warn` 并丢弃
- [x] 内置 `mutgui` 命名空间命令：实现并注册 `mutgui.redirect({url, replace?})`
- [x] 在 `window.MutguiApp` 暴露 `registerCommands`（与 `registerComponents` 并列）
- [x] 在 `mutgui/frontend/src/index.ts` 导出 `registerCommands` 类型与 API（npm 库包）

### 集成验证

- [x] 写一个最小集成 demo（或现有 demo 增加按钮）：点击触发后端 `await viewport.send_command("mutgui.redirect", url="...")`，验证浏览器跳转
- [x] 验证未注册命令场景：后端发一个不存在的 `name`，前端 console 出现 warning 且不崩溃

### 构建

- [x] `npm --prefix mutgui/frontend run build` —— 更新 npm 库包产物
- [x] `npm --prefix mutgui/frontend run build:standalone` —— 更新 demo / PyPI 分发的 standalone 产物

### 文档

- [x] 更新 `mutgui/docs/design/framework-capabilities.md` —— 在"事件系统"之后新增"命令系统"章节，记录协议形态、后端 / 前端 API、与 Event 的对偶关系、不重放语义
