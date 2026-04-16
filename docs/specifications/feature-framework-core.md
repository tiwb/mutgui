# mutgui 基础框架设计规范

**状态**：✅ 已完成
**日期**：2026-04-16
**类型**：功能设计

## 需求

1. 将 mutbot/ui 的 UI 能力抽象为独立框架 mutgui，基于 mutobj 声明-实现分离模式构建
2. 实现后端驱动 UI 的核心机制：协议定义、事件模型、组件注册表、render+diff
3. 实现基础输入组件（number、string、bool、select），验证值同步的完整往返
4. 为后续 virtual-list、属性编辑器等上层功能提供框架基础

### 现有实现参考
- `mutbot/src/mutbot/ui/context.py` — UIContext Declaration（4 个桩方法：set_view / wait_event / show / close）
- `mutbot/src/mutbot/ui/context_impl.py` — UIContext 的 @impl 实现（asyncio.Queue + WebSocket，全局注册表 _active_contexts）
- `mutbot/src/mutbot/ui/events.py` — UIEvent 数据结构（type/data/source/context_id）
- `mutbot/src/mutbot/ui/toolkit.py` — UIToolkitBase 绑定链（Toolkit.owner → ToolSet → Agent → Session → broadcast_json）
- `mutbot/frontend/src/components/ToolCallCard.tsx` — ViewRenderer 实现（switch-case 渲染 10 种组件类型）

### 后续文档
- `mutgui/docs/specifications/feature-virtual-list.md` — virtual-list 组件设计（依赖本文档的基础框架）

## 设计方案

### 定位

mutgui 是**通用 UI 层**（remote UI primitive），不是应用框架，不是编辑器框架。它可以用来构建任何类型的应用 — 简单 web 应用、聊天工具、属性编辑器、完整编辑器。

mutgui 不知道什么是 Document、EditSession、Property。它提供的是更底层的抽象：连接管理、视图推送、事件路由。应用层在这些原语之上构建业务逻辑。

### 核心设计原则（来自讨论共识）

1. **后端是 source of truth** — 数据以后端为准，前端可随时刷新重连、从后端恢复状态
2. **前端有边界的自治** — 表现层（动画、拖拽手感、滚动）前端自治，数据和结构由后端决定
3. **协议是核心契约** — View Schema + Event Model 是前后端的分界线，前端可替换（React → WebGL/Native）
4. **前端不能太复杂** — 如果不是在做具体的前端控件，就应该在写后端逻辑。绝大多数框架复杂度在后端 Python 上
5. **v1 全量推送，diff 后续优化** — 第一版只实现全量推送，前端 React 自己做 DOM reconciliation。协议级 diff 作为后续优化
6. **配置驱动，零注册** — 沿用 mutobj 理念，组件通过 register() 注册，配置中指定类路径自动加载

### 范围

本次设计覆盖：
- 协议定义（组件描述 + 事件 + `$` 命名空间约定）
- 前端组件注册表、通用渲染器、Ant Design 适配
- 后端 View + ViewSession + Transport + 事件 helper（notify/handler/bind）
- Demo（Starlette + uvicorn，验证全流程往返）
- Python 单元测试

v1 限定：
- 全量推送（无 diff）
- 基础控件（Input / InputNumber / Checkbox / Select / Button / Form / FormItem / Slider / Switch / DatePicker / Radio）
- 共享 session 模式（demo 中所有连接共享同一 View，事件后广播）

不覆盖：virtual-list（单独文档）、属性编辑器、绑定机制、多渲染器、插件运行时加载、协议级 diff。

### 项目结构

```
mutgui/
├── src/mutgui/          ← Python 库（纯数据，不含网络代码）
│   ├── view.py          ← View 基类
│   ├── session.py       ← ViewSession（render→serialize→send）
│   ├── transport.py     ← Transport 抽象接口
│   └── events.py        ← notify / handler / bind helpers
├── frontend/            ← 前端库（React + Ant Design）
│   ├── src/registry.ts  ← 组件注册表
│   ├── src/renderer.tsx ← 通用渲染器（`$component` 查找 + `$` 标签处理）
│   └── src/antd.ts      ← Ant Design 组件注册
├── demo/                ← Starlette + uvicorn demo
│   └── app.py           ← WebSocket 桥接 + 示例 View
└── tests/               ← Python 单元测试
```

Frontend ↔ Backend 通过 JSON over WebSocket 通信（demo 中实现）。Python 核心库不包含 WebSocket 代码，只负责构建 JSON 和处理事件。

跨进程 Model（如编辑器连接游戏运行时）是已识别的未来需求，当前设计不堵死这个方向，但不主动设计。

### 协议设计

#### `$` 命名空间约定

协议中 `$` 前缀的键名属于框架命名空间，其余键名属于组件 props：

- **`$component`** — 组件类型标识（如 `"Input"`、`"Button"`），用于注册表查找
- **`$` 标签**（值对象中的 `"$"` 键）— 框架指令标记（如 `"handler"`、`"bind"`），用于区分普通数据和事件处理器
- **`id`** — 双重用途：框架用于事件路由，同时透传给组件作为 HTML 属性
- **其余键** — 全部透传给组件（包括 `type`、`style`、`className` 等）

这一约定确保框架关注点（`$` 前缀）与组件关注点（无前缀）互不冲突。

#### 组件描述（Backend → Frontend）

组件 `$component` 直接使用 Ant Design 组件名（如 `InputNumber`、`Select`、`Checkbox`），不发明自有名称（LLM 对 Ant Design API 的训练数据饱和度高，零认知负担）。Props 对齐 Ant Design API，前端可直接透传。

```json
{"$component": "InputNumber", "id": "opacity", "value": 0.8, "min": 0, "max": 1, "step": 0.01}
{"$component": "Input", "id": "name", "value": "hello", "placeholder": "输入名称"}
{"$component": "Checkbox", "id": "enabled", "checked": true}
{"$component": "Select", "id": "mode", "value": "normal",
 "options": [{"value": "normal", "label": "Normal"}, {"value": "advanced", "label": "Advanced"}]}
```

前端注册表将 `$component` 名映射到实际的 React 组件。内置适配覆盖 Ant Design 常用组件；第三方或自定义组件通过 `register(name, component)` 扩展。

#### 事件模型（Frontend → Backend）

对齐 React 事件模型 — 组件可触发任意 `onXXX` 事件，后端自行决定响应哪些。不预定义事件类型列表。

```json
{"source": "name",   "event": "onChange", "data": {"value": "hello"}}
{"source": "agree",  "event": "onChange", "data": {"checked": true}}
{"source": "submit", "event": "onClick", "data": {}}
```

**事件数据统一规则**：`data` 就是组件 schema 中**变化了的 props 子集**，使用相同的 key 名。前端发给后端的事件 data，等价于 schema 的一个 patch。

#### `$` 标签约定

协议中 JSON 对象需要区分"普通数据"和"框架构造"（如事件处理器）。约定：**含 `$` 键的 JSON 对象由框架处理，不含则原样透传给组件**。

```jsonc
// 普通数据 → 透传
{"style": {"color": "red", "fontSize": 14}}

// 事件处理器 → 框架生成 function
{"onChange": {"$": "handler", "extract": {"value": "$0.target.value"}}}
```

`$` 标签可扩展到其他框架构造（组件引用、插槽等），v1 只实现 `"$": "handler"`。

**提取路径语法**：`$0` 指回调的第一个参数，`.` 访问属性，`()` 调用方法。
- `$0` → `args[0]`（直接值，如 InputNumber）
- `$0.target.value` → `args[0].target.value`（如 Input）
- `$0.target.checked` → `args[0].target.checked`（如 Checkbox）
- `$0.toHexString()` → `args[0].toHexString()`（如 ColorPicker）

#### 全量推送（v1）

v1 不实现协议级 diff。后端每次 re-render 后推送完整组件树。前端用 React 自身的 reconciliation 做 DOM diff。

```jsonc
// Backend → Frontend: 完整视图推送
{"type": "render", "tree": [
  {"$component": "Input", "id": "name", "value": "hello",
   "onChange": {"$": "handler", "extract": {"value": "$0.target.value"}}},
  {"$component": "InputNumber", "id": "age", "value": 18,
   "onChange": {"$": "handler", "extract": {"value": "$0"}}}
]}
```

协议级 diff（按组件 id 只推送变化的组件）是已识别的后续优化方向。

### 前端设计

#### 组件注册表

纯组件映射（`$component` 名 → React 组件），不含事件提取逻辑（提取由 `$` 标签驱动）：

```typescript
const registry = new Map<string, React.ComponentType<any>>();

function register(type: string, component: React.ComponentType<any>) {
  registry.set(type, component);
}
```

内置适配一次性注册整个 Ant Design 库：

```typescript
import * as Antd from 'antd';
export function registerAntd() {
  for (const [name, comp] of Object.entries(Antd)) {
    if (typeof comp === 'function' || typeof comp === 'object') {
      register(name, comp as React.ComponentType);
    }
  }
}
```

#### 通用渲染器

遍历 JSON 树，对每个组件：查 registry 取组件 → 处理 `$` 标签生成事件函数 → 透传其余 props（包括 `id`）。

```typescript
function MutguiRenderer({ tree, ws }) {
  return tree.map(schema => {
    const Component = registry.get(schema.$component);
    if (!Component) return <UnknownComponent $component={schema.$component} />;
    const props = processProps(schema, ws);
    return <Component key={schema.id} {...props} />;
  });
}

function processProps(schema, ws) {
  const props = {};
  for (const [key, val] of Object.entries(schema)) {
    if (key === '$component') continue;  // 框架字段，不透传
    if (val && typeof val === 'object' && '$' in val) {
      props[key] = createHandler(val, schema.id, key, ws);
    } else if (key === 'children' && Array.isArray(val)) {
      props[key] = <MutguiRenderer tree={val} ws={ws} />;
    } else {
      props[key] = val;  // id、type、style 等全部透传
    }
  }
  return props;
}

function createHandler(spec, sourceId, eventName, ws) {
  return (...args) => {
    const data = {};
    for (const [key, path] of Object.entries(spec.extract || {})) {
      data[key] = resolvePath(args, path);
    }
    ws.send(JSON.stringify({ source: sourceId, event: eventName, data }));
  };
}
```

`resolvePath` 解析 `$0.target.value` 等路径，从回调参数中提取值。

### 后端设计

#### View 基类

应用开发者继承 View，实现 `render()` 返回组件树。v1 不使用 mutobj Declaration（应用开发者在同一个类里写 render 和事件处理，不需要声明-实现分离）。

```python
class View:
    def render(self) -> list[dict]:
        """声明当前 UI 应该长什么样。框架调用，应用重写。"""
        return []

    def on_event(self, event: dict) -> None:
        """处理前端事件（fallback，未被 handler/bind 捕获的事件）。"""
        pass
```

`render()` 返回 `list[dict]`（组件列表）或 `dict`（单根组件）。框架兼容两种形式。

支持嵌套：组件可以有 `children` 字段（`list[dict]`），形成树结构。v1 基础控件都是叶子节点。

#### 事件 helper：notify / handler / bind

后端 schema 中 `onXXX` 的值由 helper 函数生成，显式声明提取规则（不隐藏在前端 registry 中）：

```python
def notify(**extract: str):
    """提取数据，发送到 view.on_event()"""
    return {"$": "handler", "extract": extract}

def handler(fn: Callable, **extract: str):
    """提取数据，调用指定方法"""
    return {"$": "handler", "fn": fn, "extract": extract}

def bind(obj: Any, attr: str, path: str = "$0"):
    """提取数据，自动写回对象属性"""
    return {"$": "bind", "obj": obj, "attr": attr, "path": path}
```

用法：

```python
def render(self):
    return [
        {"$component": "Input", "id": "name", "value": self.name,
         "onChange": bind(self, "name", "$0.target.value")},
        {"$component": "InputNumber", "id": "age", "value": self.age,
         "onChange": bind(self, "age", "$0")},
        {"$component": "Button", "id": "save", "children": "Save",
         "type": "primary",
         "onClick": handler(self.save)},
    ]
```

#### ViewSession

管理一个 View 的 render→serialize→send 循环。处理 `$` 标签中的 callable 提取和事件分发：

```python
class ViewSession:
    def __init__(self, view: View, transport: Transport):
        self.view = view
        self.transport = transport
        self._callbacks: dict[tuple[str, str], Callable] = {}

    async def initialize(self):
        """首次 render，推送完整树"""
        tree = self.view.render()
        wire_tree = self._process_tree(tree)
        await self.transport.send({"type": "render", "tree": wire_tree})

    async def handle_event(self, event: dict):
        """处理前端事件 → dispatch → re-render → 推送"""
        key = (event["source"], event["event"])
        cb = self._callbacks.get(key)
        if cb:
            cb(event.get("data", {}))
        else:
            self.view.on_event(event)
        # re-render + 全量推送
        tree = self.view.render()
        wire_tree = self._process_tree(tree)
        await self.transport.send({"type": "render", "tree": wire_tree})

    def _process_tree(self, tree):
        """提取 callable/bind，替换为 $ 标签，构建 callback registry"""
        self._callbacks.clear()
        # 遍历树，处理 onXXX 中的 callable/bind...
        ...
```

#### Transport 接口

```python
class Transport:
    """传输抽象 — 只负责把消息送出去"""
    async def send(self, message: dict) -> None: ...
```

Python 核心库不包含任何 WebSocket/HTTP 代码。demo 中通过 Starlette WebSocket 实现 Transport。

#### 与 mutbot/ui 的关系

mutbot/ui 已验证的模式（push view + wait event 的往返循环）是 mutgui 的起点。主要改进：
- 解耦 mutbot 依赖（不再绑定 Session/broadcast_json）
- 组件注册表替代 switch-case
- React-style 事件模型替代固定事件类型
- Ant Design 组件替代自定义控件

### Demo

Demo 用 Starlette + uvicorn，验证全流程往返。mutgui Python 核心不含 web 服务器。

Demo 采用**共享 session 广播模式**：所有 WebSocket 连接共享同一个 View 实例，任何客户端的操作都会广播到其他连接。`ViewSession.push()` 是框架提供的主动推送方法，应用层自行管理广播逻辑。

前端使用预构建的 standalone bundle（`mutgui.js`，IIFE 全量包含 React + Ant Design + 渲染器），通过 `<script>` 标签加载，无需前端构建工具。

```python
# demo/app.py — 关键片段
view = SignupView()
sessions: list[ViewSession] = []

async def ws_handler(websocket):
    await websocket.accept()
    session = ViewSession(view, WebSocketTransport(websocket))
    sessions.append(session)
    await session.initialize()
    try:
        while True:
            raw = await websocket.receive_text()
            event = json.loads(raw)
            await session.handle_event(event)
            # 广播到其他连接
            for s in sessions:
                if s is not session:
                    await s.push()
    except Exception:
        pass
    finally:
        sessions.remove(session)
```

Demo 依赖 `starlette` 和 `uvicorn`，不加入 mutgui 核心包依赖。

## 已决策问题

以下问题在设计讨论中已确认：

- **View 的结构**：支持嵌套。组件可以有 `children` 字段。v1 基础控件都是叶子节点
- **re-render 触发机制**：事件驱动 + `push()`。收到前端 event 后框架自动 re-render；应用层可调用 `ViewSession.push()` 主动推送
- **diff 粒度**：v1 不做 diff，全量推送。前端 React 自身的 reconciliation 足够
- **前端构建与部署**：mutgui 仓库内 `frontend/` 目录，Vite 构建。库模式供 mutbot 通过 `file:` 协议依赖；standalone 模式（IIFE bundle）供 demo 和独立应用
- **后端独立运行**：demo 用 Starlette + uvicorn 独立验证。mutgui 核心不含 web 服务器
- **`$` 命名空间**：`$component` 标识组件类型，`$` 标签标识框架指令。`id` 双重用途（路由 + 透传）。其余 props 全部透传

## 实施步骤清单

- [x] Python 核心库 — View / ViewSession / Transport / 事件 helpers（notify / handler / bind）
- [x] 前端项目初始化 — package.json（含 antd 依赖）、Vite + TypeScript 配置
- [x] 前端核心 — 组件注册表、通用渲染器（`$` 标签处理 + resolvePath）
- [x] 前端 Ant Design 适配 — registerAntd() 批量注册
- [x] Demo — Starlette WebSocket 桥接 + SignupView 示例
- [x] 端到端验证 — WebSocket 协议往返验证通过（初始渲染、bind 值同步、条件渲染、handler 调用）
- [x] Python 单元测试 — 18 个测试全部通过（events 6 + session 10 + basic 2）
