# Demo 框架重构 + mutio.net 迁移

**状态**：✅ 已完成
**日期**：2026-04-21
**类型**：重构

## 需求

1. **统一 demo 框架**：现有 3 个独立 demo 脚本用 Starlette + uvicorn，需要一个基于 mutio.net 的轻量框架统一管理
2. **拆分 example**：每个 example 展示一个功能点，降低学习曲线
3. **保留 Starlette demo**：证明 mutgui 核心 transport-agnostic
4. **测试 fixture 迁移**：conftest.py 的 TestApp 从 uvicorn 迁移到 mutio.net

## 设计方案

### 整体架构

mutgui 核心不引入 mutio 依赖，保持 transport-agnostic。mutio 仅用于 demo 框架和测试。

```
mutgui 核心 (src/mutgui/)   → 只依赖 mutobj（不变）
demo 框架 (demo/framework/) → 使用 mutio.net
examples (demo/examples/)   → 使用 framework
standalone (demo/standalone/) → Starlette + uvicorn
集成测试 (tests/integration/) → 使用 mutio.net
```

### 依赖变更

核心 dependencies 不变。mutio 加入 dev/test optional-dependencies：

```toml
[project.optional-dependencies]
demo = ["mutio"]
test = ["mutio", "pytest>=7.0", "pytest-asyncio>=0.23", "playwright>=1.40"]
```

mutobj 版本需先从 `~=0.2.0` 升级到 `~=0.6.0`（与 mutio 对齐），这是前置步骤。

### 目录结构

```
demo/
  __init__.py             # 标记为 package
  __main__.py             # python -m demo 启动 Gallery
  framework/              # 框架包
    __init__.py           # 导出 MutguiRoute、DemoApp 等
    _routes.py            # MutguiRoute、DemoApp、mutgui_page
    _server.py            # Gallery 页面、文件扫描、路由分发、懒加载
    _channel.py           # 基于 mutio WebSocketConnection 的 Channel 实现
  examples/               # 基于 framework 的 demo（每个文件一个功能点）
    basic.py              # 最简 mutgui — 一个 View、基础元素
    antd.py               # Ant Design 控件 — Form、Input、Select、Checkbox
    nesting.py            # View 嵌套 — 父 View 包含子 View
    virtual_list.py       # VirtualList — 大列表虚拟滚动
    dock.py               # DockPanel — IDE 风格多面板布局
  games/                  # 游戏类 demo
    mahjong.py            # 多视图麻将 — 同一状态、多路由展示不同视角
  standalone/
    starlette.py          # 独立 Starlette + uvicorn demo
```

### Demo 路由声明

每个 example 导出 `app` 对象（`DemoApp` 实例），可独立运行也可被 Gallery 发现：

```python
# demo/examples/basic.py
"""最简 mutgui 示例 — 一个计数器按钮。"""
from demo.framework import MutguiRoute, DemoApp
from mutgui import View, ViewBlock, Callback

class CounterView(View):
    def __init__(self):
        self.count = 0

    def render(self) -> ViewBlock:
        return ViewBlock([
            {"$component": "Button", "$id": "btn",
             "children": f"Clicked {self.count}",
             "onClick": Callback(self._on_click)},
        ])

    def _on_click(self):
        self.count += 1
        self.invalidate()

app = DemoApp([
    MutguiRoute("/", CounterView(), title="Basic"),
])

if __name__ == "__main__":
    app.run()
```

### MutguiRoute

核心路由组件，同一路径同时处理 HTTP GET 和 WebSocket：

- **HTTP GET** → 返回 HTML 页面（加载 mutgui.js + mount WebSocket）
- **WebSocket** → 封装 accept → Channel → ViewPort → event loop → detach

```python
MutguiRoute(path, view, *, title=None, html=None)
```

| 参数 | 说明 |
|------|------|
| `path` | 相对路径，如 `"/"`、`"/east"`。框架自动加 `/{文件名}` 前缀 |
| `view` | 单个 mutgui View 实例 |
| `title` | 页面标题（用于默认 HTML 模板和 Gallery 列表） |
| `html` | 自定义 HTML 字符串。不传则使用默认模板 |

默认 HTML 模板生成标准 mutgui 页面，WebSocket 用 `location.pathname` 连接（同路径，不需要 `/ws`）：

```js
MutguiApp.mount(document.getElementById('app'),
    `ws://${location.host}${location.pathname}`)
```

如果 demo 想完全自定义 HTML 或路由，可以传 `html=` 参数，或直接用 mutio.net 原生 View 类放进 `routes`。

### 多路由 Example

多视图用多个 `MutguiRoute` 实现，每个视图独立 URL（不需要 `?view=` query param 或 hash 路由）：

```python
# demo/games/mahjong.py
"""多视图麻将 — 同一游戏状态，不同客户端看不同视角。"""
from demo.framework import MutguiRoute, DemoApp

# ... 游戏 View 定义 ...

app = DemoApp([
    MutguiRoute("/", table_view, title="麻将"),
    MutguiRoute("/east", player_views[Seat.EAST], title="东家"),
    MutguiRoute("/south", player_views[Seat.SOUTH], title="南家"),
    MutguiRoute("/west", player_views[Seat.WEST], title="西家"),
    MutguiRoute("/north", player_views[Seat.NORTH], title="北家"),
])

if __name__ == "__main__":
    app.run()
```

实际 URL：`/mahjong/`、`/mahjong/east`、`/mahjong/south` ...

### 框架行为

**文件发现**（类 pytest）：
- 扫描 `demo/examples/*.py`，排除 `_` 开头
- 文件名 = URL 前缀（`basic.py` → `/basic/`）

**懒加载**：
- 启动时只扫描文件名（不 import）
- 访问 `/{name}/...` 时才 `importlib` 加载对应模块，优先读取 `app` 对象（`DemoApp` 实例），fallback 到 `routes` 列表

**Gallery 首页**（`/`）：
- 列出所有 example 文件名作为链接
- title 可从 docstring 提取（不需要 import 模块）

**共享静态文件**：
- `/static/` 服务 mutgui.js、antd.js 等
- 各 example 不需要单独处理静态文件

### Starlette 独立 Demo

`demo/standalone/starlette.py` 从现有 app.py 精简而来，独立运行（`python demo/standalone/starlette.py`）。展示 mutgui 核心的 transport-agnostic 特性——Channel 接口可适配任何 Web 框架。

### 测试 fixture 迁移

conftest.py 的 TestApp 从 uvicorn 迁移到 mutio.net：

```python
from mutio.net import Server

class TestApp:
    async def start(self):
        server = Server(host="127.0.0.1", port=0, views=(...))
        self._server = server
        await server.start()
        self.port = server.ports[0]  # 直接获取，不需要 polling

    async def stop(self):
        await self._server.stop()
```

### 尾斜杠处理

`/basic`（无尾斜杠）由框架层 301 重定向到 `/basic/`。

### Gallery title

Gallery 首页直接用文件名作为 demo 标题，不解析 docstring。后续需要时再加。

## 实施步骤清单

- [x] 升级 mutgui 的 mutobj 依赖到 ~=0.6.0，验证现有测试通过
- [x] pyproject.toml 添加 mutio 到 demo/test optional-dependencies
- [x] 创建 `demo/framework/` 包 — MutguiRoute、DemoApp、_channel、_server、Gallery 路由分发
- [x] 创建 `demo/examples/` — 拆分现有 demo 为 basic、antd、nesting、virtual_list、dock、mahjong
- [x] 创建 `demo/standalone/starlette.py` — 基础 Starlette + uvicorn 集成示例
- [x] 迁移 `tests/integration/conftest.py` 的 TestApp 到 mutio.net
- [x] 删除旧 demo 文件（demo/app.py、demo/dock_demo.py、demo/mahjong.py）
- [x] 端到端验证 — Gallery 首页 + 所有 example HTTP/WebSocket + 单元测试 59 通过

## 关键参考

- `mutio/src/mutio/net/server.py` — View/WebSocketView/StaticView/Server 声明
- `mutio/src/mutio/net/_server_impl.py` — 路由发现、路径匹配、_send_response、_make_ws_connection
- `mutio/src/mutio/net/asgi.py` — ASGI 服务器（start/stop/ports）
- `src/mutgui/channel.py` — Channel 抽象接口
- `demo/framework/_routes.py` — MutguiRoute、DemoApp 定义
- `demo/framework/_server.py` — Gallery 服务器、run_single、_handle_ws
- `tests/integration/conftest.py` — TestApp fixture（基于 mutio.net）
