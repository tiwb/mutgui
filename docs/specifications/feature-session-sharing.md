# 核心抽象重构 — Declaration 化与多客户端支持

**状态**：✅ 已完成
**日期**：2026-04-17
**类型**：重构

## 需求

1. 将 mutgui 核心抽象（View、传输、渲染管道）引入 mutobj Declaration 模式，明确接口设计与实现细节的分界
2. 多个客户端共享同一个 View 实例树时，`invalidate()` 能通知所有观察者，只推送真正变化的 View
3. 当前 `View._session` 是 1:1 引用，后者覆盖前者；demo 用 `push()` 暴力全量广播绕过限制
4. mutgui 最终需要被 mutbot 使用，传输层抽象需要与 mutbot 的 Channel/Session 体系良好对接

### 前置依赖

- `feature-view-nesting.md` — View 嵌套机制（ViewSession、viewId 路径、dirty flush）
- `feature-framework-core.md` — 基础框架（协议、事件模型、View/ViewSession/Transport）

## 关键参考

### 内部实现

- `mutgui/src/mutgui/session.py` — 当前 ViewSession（将重构为 ViewPort）
- `mutgui/src/mutgui/view.py` — 当前 View 基类（将改为 Declaration）
- `mutgui/src/mutgui/transport.py` — 当前 Transport（将重命名为 Channel）
- `mutgui/src/mutgui/events.py` — 事件 helper（notify/handler/bind，不变）
- `mutgui/demo/app.py` — 共享 View demo，`push()` 广播模式

### Declaration-Implementation 分离参考

- `mutagent/src/mutagent/net/client.py` — Declaration 文件范例（MCPClient：属性 + 桩方法）
- `mutagent/src/mutagent/net/_client_impl.py` — impl 文件范例（Extension + @impl）
- `mutagent/src/mutagent/net/__init__.py` — impl 注册范例（side-effect import）

### mutbot 传输层参考

- `mutbot/src/mutbot/web/transport.py` — Client 类（物理连接生命周期、ACK、重连）
- `mutbot/src/mutbot/channel.py` — Channel Declaration（逻辑管道，send_json/send_binary）
- `mutbot/src/mutbot/session.py:166-184` — SessionChannels Extension[Session]（1:N 广播模式）

### 当前架构问题

```
View (1个实例)          Sessions (N个)
┌──────────────┐       ┌─────────────┐
│ RootView     │       │ Session A   │  transport A
│              │       └─────────────┘
│ _session ──────────► ┌─────────────┐
│              │       │ Session B   │  transport B （覆盖了 A）
└──────────────┘       └─────────────┘

invalidate() → 只通知 Session B
Session A 完全不知道 View 状态变了
demo 用 push() 暴力广播所有 Session
```

### 目标架构

```
View (Declaration)       ViewPort (N个，各自独立 render)
┌──────────────┐       ┌─────────────┐
│ RootView     │       │ ViewPort A  │→ Channel A → 客户端 A
│              │◄──────│  (observes) │
│ invalidate() │       └─────────────┘
│   ↓ @impl    │       ┌─────────────┐
│ ViewObservers│◄──────│ ViewPort B  │→ Channel B → 客户端 B
│ (Extension)  │       │  (observes) │
└──────────────┘       └─────────────┘

invalidate() → ViewObservers → 各 ViewPort 异步 flush
push() 不再需要
```

## 设计方案

### 范围

原始需求是解决 View._session 的 1:1 限制。讨论后范围扩展为：将 mutgui 核心抽象全面 Declaration 化，明确接口与实现的分界。多客户端共享作为自然结果解决。

**重命名**：

| 旧名 | 新名 | 理由 |
|------|------|------|
| Transport | Channel | 对应 mutbot 的 Channel 概念（逻辑管道） |
| ViewSession | ViewPort | "Session" 是用户编辑状态（应用层概念），ViewPort 是渲染管道（框架层概念） |

### 文件结构

遵循 mutagent 的 Declaration-Implementation 分离模式。

**接口层（Declaration 文件，公开）**：用户看这些文件理解 API

| 文件 | 内容 |
|------|------|
| `view.py` | View Declaration |
| `channel.py` | Channel Declaration |
| `viewport.py` | ViewPort Declaration |
| `events.py` | 事件 helper（notify/handler/bind，纯函数，不变） |

**实现层（_impl 文件，私有）**：所有 @impl、Extension、内部逻辑

| 文件 | 内容 |
|------|------|
| `_view_impl.py` | ViewObservers Extension[View] + @impl(View.invalidate) |
| `_viewport_impl.py` | ViewPortRuntime Extension[ViewPort] + 所有 @impl（render 循环、事件路由、dirty tracking、子 View 管理） |

**注册**：`__init__.py` 通过 side-effect import 加载 impl 模块

### 接口设计（Declaration 层）

所有公开接口使用 Declaration 桩方法，保持声明文件简洁直观。

#### View — 视图声明

```python
# view.py
class View(Declaration):
    """mutgui 视图基类。

    应用开发者继承此类，覆盖 render() 描述 UI 应该长什么样。
    框架负责 render → serialize → send 循环。
    """

    id: str | int = ""

    def render(self) -> list[Any] | dict[str, Any]:
        """声明当前 UI 应该长什么样。

        返回组件列表 (list[dict | View]) 或单根组件 (dict)。
        """
        ...

    def on_event(self, event: dict[str, Any]) -> None:
        """处理未被 handler/bind 捕获的事件（fallback）。"""
        ...

    def invalidate(self) -> None:
        """标记需要重新 render，合并到下一次推送。"""
        ...
```

- 三个方法全是桩。render/on_event 由 `_view_impl.py` 提供默认 @impl（返回空列表 / 空操作），用户通过子类覆盖
- invalidate 由 `_view_impl.py` 的 ViewObservers @impl 提供，通知所有 ViewPort
- **View 不 import ViewPort，不知道观察者的存在**

#### Channel — 通信管道声明

```python
# channel.py
class Channel(Declaration):
    """通信管道接口。

    mutgui 核心不包含网络代码。具体传输方式（WebSocket、IPC 等）
    由使用方子类实现。
    """

    async def send(self, message: dict[str, Any]) -> None:
        """发送一条 JSON 消息到前端。"""
        ...
```

- 用户通过子类提供具体传输实现（如 demo 的 WebSocketChannel）
- mutbot 集成时：适配器将 mutbot.Channel → mutgui.Channel

#### ViewPort — 渲染管道声明

```python
# viewport.py
class ViewPort(Declaration):
    """将一个 View 渲染并推送到一个 Channel。

    每个 ViewPort 代表"一个客户端正在观察一个 View"。
    同一个 View 可以被多个 ViewPort 观察，invalidate() 通知所有。
    """

    def __init__(self, view: View, channel: Channel) -> None:
        """创建 ViewPort，绑定 View 和 Channel。"""
        ...

    async def initialize(self) -> None:
        """首次 render，推送完整树。"""
        ...

    async def handle_event(self, event: dict[str, Any]) -> None:
        """处理前端事件 → 路由 → flush dirty views。"""
        ...

    async def flush(self) -> None:
        """Flush 所有 dirty views（配合 invalidate 使用）。"""
        ...

    def detach(self) -> None:
        """从 View 解除绑定，移除观察者注册。"""
        ...
```

- 标准构造函数 `ViewPort(view, channel)`（`__init__` 桩 + @impl，符合 mutobj `feature-positional-init` 规范）
- 所有状态（callbacks、children、dirty flag）在 Extension 中，声明文件无任何实现

### 实现层

#### ViewObservers — Extension[View]

```python
# _view_impl.py
class ViewObservers(Extension[View]):
    """追踪一个 View 实例的所有 ViewPort 观察者。"""
    _viewports: list = field(default_factory=list)

@impl(View.render)
def _default_render(self: View) -> list:
    return []

@impl(View.on_event)
def _default_on_event(self: View, event: dict) -> None:
    pass

@impl(View.invalidate)
def _view_invalidate(self: View) -> None:
    ext = ViewObservers.get(self)
    if ext is not None:
        for vp in ext._viewports:
            vp._schedule_flush()
```

- 三件套模式（同 mutbot 的 SessionChannels）：Declaration 声明接口 → Extension 附着状态 → @impl 提供实现
- View 完全不知道 ViewObservers 和 ViewPort 的存在

#### ViewPortRuntime — Extension[ViewPort]

```python
# _viewport_impl.py
class ViewPortRuntime(Extension[ViewPort]):
    """ViewPort 的运行时私有状态。"""
    _view: View | None = None
    _channel: Channel | None = None
    _path: list = field(default_factory=list)
    _callbacks: dict = field(default_factory=dict)
    _children: dict = field(default_factory=dict)
    _dirty: bool = True
    _flush_scheduled: bool = False

@impl(ViewPort.__init__)
def _viewport_init(self: ViewPort, view: View, channel: Channel) -> None:
    ext = ViewPortRuntime.get_or_create(self)
    ext._view = view
    ext._channel = channel
    ext._dirty = True
    ViewObservers.get_or_create(view)._viewports.append(self)
```

继承当前 ViewSession 的全部逻辑：render → process → send 循环、callback registry、子 View 嵌套管理、事件路由（source 数组逐层路由）。

**异步 flush 合并**：`_schedule_flush()` 标脏并在事件循环下一轮 flush，多次 invalidate() 合并为一次推送。

### 与 mutbot 的集成模型

```python
# mutbot 侧 — 适配器 + Session 回调
class MutguiChannelAdapter(mutgui.Channel):
    """mutbot.Channel → mutgui.Channel 适配器。"""
    def __init__(self, channel: mutbot.Channel):
        self._channel = channel
    async def send(self, message):
        self._channel.send_json(message)

class GuiSession(Session):
    async def on_connect(self, channel, ctx):
        adapter = MutguiChannelAdapter(channel)
        vp = ViewPort(self.view, adapter)
        await vp.initialize()

    async def on_message(self, channel, raw, ctx):
        vp = self._find_viewport(channel)
        await vp.handle_event(raw)
        # 不需要手动 push()
        # handle_event 内部的状态变更 → invalidate()
        # → ViewObservers → 自动通知所有 ViewPort

    async def on_disconnect(self, channel, ctx):
        vp = self._find_viewport(channel)
        vp.detach()
```

### 不变的部分

- 协议格式（`$component`、`$`、handler/bind/notify 标签）
- 事件路由逻辑（source 数组逐层路由）
- 前端代码（registry、renderer、antd adapter、context）
- 子 View 嵌套机制（ViewPort 内部管理 children，对应当前 ViewSession 的嵌套逻辑）
- events.py（纯函数，不涉及 Declaration）

### Q1 决策记录

ViewPort 使用标准构造函数 `ViewPort(view, channel)`，不用工厂方法（Python 惯例、与 View/Channel 创建方式一致、可发现性更好）。`__init__` 桩 + `@impl` 模式符合 mutobj `feature-positional-init` 规范。

## 实施步骤清单

- [x] 将 `view.py` 改为 Declaration（id 属性 + render/on_event/invalidate 三个桩方法）
- [x] 新建 `channel.py`（Channel Declaration，send 桩方法）
- [x] 新建 `viewport.py`（ViewPort Declaration，__init__/initialize/handle_event/flush/detach 桩方法）
- [x] 新建 `_view_impl.py`（ViewObservers Extension + render/on_event/invalidate 的 @impl）
- [x] 新建 `_viewport_impl.py`（ViewPortRuntime Extension + 所有 @impl，从当前 session.py 迁移逻辑）
- [x] 更新 `__init__.py`（导出新 API + side-effect import 加载 impl）
- [x] 更新 `demo/app.py`（Transport→Channel, ViewSession→ViewPort, push()→自动通知）
- [x] 更新测试（适配新类名和新 API + 新增多客户端测试）
- [x] 删除旧文件（`transport.py`、`session.py`）
- [x] 运行全部测试验证（28 passed）

### 实施中发现的问题

1. **View.id 不能是 Declaration 属性**：`id: str | int = ""` 会变成 `AttributeDescriptor`，子类 `id = "child"` 被父类 data descriptor 拦截。改为无注解的 class variable `id = ""` 解决。
2. **事件处理需调用 view.invalidate()**：原 `_route_event` 只标脏当前 ViewPort。改为调用 `view.invalidate()` 通知所有观察者，多客户端共享自然工作。
