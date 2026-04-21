# 全栈交互测试框架 设计规范

**状态**：✅ 已完成
**日期**：2026-04-20
**类型**：功能设计

## 需求

1. 为 mutgui 提供全栈交互测试能力，验证前后端联动的交互行为（拖拽、resize、点击等）
2. Python 测试用例同时控制后端状态和前端交互，断言覆盖前端 DOM + 后端对象状态
3. 支持 headed 模式（开发期间肉眼观察交互行为）和 headless 模式（CI 环境）
4. 复用已有的 chrome-cdp 基础设施（Chrome CDP 端口 9222）
5. 支持多 viewport 测试场景（同一 View 多个客户端连接）
6. 为后续 DockPanel 等复杂组件的响应式行为测试提供基础

### 前置依赖

- `feature-framework-core.md` — 基础框架（协议、事件、View/ViewPort）
- `feature-view-nesting.md` — View 嵌套与事件路由
- `feature-session-sharing.md` — 多客户端支持

## 关键参考

### 已有基础设施

- **mutgui standalone 入口** — `frontend/src/standalone.tsx`，WebSocket 连接 + MutguiView 渲染
- **mutgui demo** — `demo/app.py`，启动 Web 服务器 + 挂载 View
- **chrome-cdp skill** — `~/.claude/skills/chrome-cdp/`，Chrome CDP 实例管理 + Playwright 浏览器自动化
- **mutbot Playwright 封装** — 已有将 Playwright MCP 包装为 Python API 的实践

### 测试对象（验证用）

- **VirtualList** — 复杂交互组件（滚动、item 点击、多 viewport 可见范围）
- **Input / Button** — 基础交互组件（输入、点击事件）
- **Row/Col/Card** — 纯布局组件（渲染正确性）

## 设计方案

### 测试分层

| 层次 | 工具 | 验证内容 | 速度 |
|------|------|----------|------|
| 第一层：单元测试 | pytest（纯 Python） | 后端逻辑（render 输出、事件路由、状态管理） | 快（ms级） |
| 第二层：全栈交互测试 | pytest + Playwright Python | 前后端联动（交互→事件→状态→重渲染） | 中（秒级） |
| 第三层：手动验收 | 开发者 + headed Chrome | 视觉细节、动画流畅性、边缘交互 | 慢 |

本文档设计的是**第二层**。第一层已有（pytest），第三层无需框架支持。

### 架构概览

```
┌─────────────────────────────────────────────┐
│            Python Test Case                  │
│                                              │
│  ┌─────────────┐    ┌────────────────────┐  │
│  │ Backend     │    │ Frontend           │  │
│  │ (View 实例) │    │ (Playwright Page)  │  │
│  │             │    │                    │  │
│  │ • 创建 View │    │ • 导航到页面       │  │
│  │ • 断言状态  │    │ • 模拟交互         │  │
│  │ • 触发变更  │    │ • 断言 DOM         │  │
│  └──────┬──────┘    └────────┬───────────┘  │
│         │    WebSocket       │              │
│         └────────────────────┘              │
└─────────────────────────────────────────────┘
```

测试用例在同一个 Python 进程中：
- 直接持有后端 View 对象（可读写状态、调用方法）
- 通过 Playwright 控制浏览器（模拟用户交互、断言 DOM）
- 后端与前端通过真实 WebSocket 连接

### Test Fixture 设计

#### Playwright Fixture（session 级别）

管理 Playwright 驱动进程生命周期：

```python
@pytest.fixture(scope="session")
async def pw():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        yield p
```

#### Browser Fixture（session 级别）

见「浏览器连接方式」章节，依赖 `pw` fixture。

#### App Fixture（session 级别）

启动一个 mutgui 测试服务器。内部用 Starlette + uvicorn，提供 View 注册和 WebSocket 连接管理：

```python
@pytest.fixture(scope="session")
async def app():
    server = TestApp()
    await server.start()    # 随机端口启动
    yield server
    await server.stop()
```

#### Page Fixture（test 级别）

每个测试用例获得一个独立的 Playwright Page：

```python
@pytest.fixture
async def page(app, browser):
    ctx = await browser.new_context()
    page = await ctx.new_page()
    yield page
    await ctx.close()
```

#### Multi-viewport Fixture

测试多客户端场景：

```python
@pytest.fixture
async def pages(app, browser):
    ctx1 = await browser.new_context()
    ctx2 = await browser.new_context()
    page1 = await ctx1.new_page()
    page2 = await ctx2.new_page()
    yield page1, page2
    await ctx1.close()
    await ctx2.close()
```

### View 挂载机制

采用**注册表 + 通配路由**方案：TestApp 内部维护 `{view_id: View}` 字典，通过通配路由 `/view/{view_id}` 和 `/ws/{view_id}` 统一处理。不需要运行时动态添加路由。

```python
# 测试用例中
async def test_button(app, page):
    view = MyView()
    url = app.mount(view)                       # 注册 view，返回 URL
    await page.goto(url)                        # 浏览器导航
    await page.get_by_test_id("btn").click()    # 通过 data-testid 定位
    assert view.clicked is True                 # 后端断言
```

`app.mount(view)` 内部：生成唯一 view_id → 存入注册表 → 返回 `http://localhost:{port}/view/{view_id}`。

HTML 页面加载 `mutgui.js`，自动连接 `/ws/{view_id}`，WebSocket handler 从注册表查找 View 并创建 ViewPort。

#### 元素定位约定

mutgui 的 `$id` 是协议内部标识，**不会渲染为 DOM `id` 属性**（`renderer.tsx` 中 `$id` 被显式过滤）。测试中通过 `data-testid` 定位元素——非 `$` 前缀的 props 会透传到 Ant Design 组件并最终出现在 DOM 上：

```python
# View 定义中
{"$component": "Button", "$id": "inc", "data-testid": "inc-btn", ...}

# 测试中
btn = page.get_by_test_id("inc-btn")
await expect(btn).to_have_text("Count: 0")
```

### 交互工具函数

按需封装，随测试用例逐步引入：

```python
# 拖拽（splitter、面板等）
await drag(page, selector, delta_x=100, delta_y=0)

# 获取元素尺寸
size = await get_size(page, selector)

# 模拟 viewport resize
await resize_viewport(page, width=400, height=600)
```

### 等待策略

前后端通过 WebSocket 异步通信，交互后需要等待：

1. **前端→后端**：用户操作触发事件 → WebSocket 发送 → 后端处理
2. **后端→前端**：后端 invalidate → render → WebSocket 推送 → 前端重绘

不实现通用的 `wait_for_render()`——每个测试场景等待的信号不同。使用 Playwright 内置等待机制：
- `expect(locator).to_be_visible()` / `to_have_text()` 等自带重试（推荐）
- `page.wait_for_selector()` 等待特定 DOM 变化
- 后端侧 `await view.rendered()` 等待 render 完成

避免固定 `sleep()`——脆弱且慢。

### 断言工具

同时断言前端和后端状态：

```python
# 前端 DOM 断言（Playwright + data-testid）
await expect(page.get_by_test_id("tab-bar")).to_be_visible()
await expect(page.get_by_test_id("inc-btn")).to_have_text("Count: 1")

# 后端状态断言（直接访问 Python 对象）
assert view.some_state == expected_value
assert len(view._viewports) == 2
```

### 浏览器连接方式

三种模式，通过 pytest 命令行选项控制：

| 模式 | 触发 | 行为 |
|------|------|------|
| **默认（自动）** | 不传参数 | 先试 headless → 失败 fallback CDP 9222 → 都失败 skip |
| **`--headed`** | 显式指定 | 强制连 CDP 9222，连不上 fail（不 fallback） |
| **`--headless`** | 显式指定 | 强制启动 headless Chromium，不试 CDP |

默认先试 headless 而非 CDP（有 CDP 端口开着时 headed 模式会弹出大量窗口闪烁，日常体验差）。

```python
def pytest_addoption(parser):
    parser.addoption("--headed", action="store_true", help="强制 headed 模式（需 CDP 9222）")
    parser.addoption("--headless", action="store_true", help="强制 headless 模式")

@pytest.fixture(scope="session")
async def browser(request, pw):
    """根据命令行选项决定浏览器连接方式"""
    headed = request.config.getoption("--headed")
    headless = request.config.getoption("--headless")

    if headed:
        browser = await pw.chromium.connect_over_cdp("http://localhost:9222")
    elif headless:
        browser = await pw.chromium.launch(headless=True)
    else:
        # 默认：先试 headless（无闪窗），fallback CDP
        try:
            browser = await pw.chromium.launch(headless=True)
        except Exception:
            try:
                browser = await pw.chromium.connect_over_cdp("http://localhost:9222")
            except Exception:
                pytest.skip("No browser available")
    yield browser
    await browser.close()
```

典型用法：
- 开发调试：`pytest tests/integration/ --headed`（需先启动带 `--remote-debugging-port=9222` 的 Chrome）
- CI 环境：`pytest tests/integration/ --headless`（需 `playwright install chromium`）
- 本地随意跑：`pytest tests/integration/`（自动判断，无浏览器时静默 skip）

### pytest-asyncio 配置

session 级 fixture（app、browser）和 test function 必须共享同一个事件循环，否则 uvicorn server 的异步任务无法在测试中被调度。需要在 `pyproject.toml` 中配置：

```toml
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "session"
asyncio_default_test_loop_scope = "session"
```

### 设计决策

#### 测试文件组织

`tests/integration/` 目录，通过 pytest marker（`@pytest.mark.integration`）区分。CI 中可通过 `-m integration` 单独运行或排除。

#### Playwright 依赖管理

`playwright` 加入 `pyproject.toml` 的 `[project.optional-dependencies]` 下的 `test` 组（`pip install -e ".[test]"`），与 pytest 等测试依赖并列。

#### 与已有 chrome-cdp skill 的关系

独立实现，不复用 chrome-cdp skill。chrome-cdp skill 面向 AI 交互式调试（单次操作、经 pysandbox），测试框架需要 fixture 生命周期管理、pytest 集成等，职责不同。两者共享同一个 Chrome 实例（CDP 9222）。

## 实施步骤清单

- [x] `pyproject.toml` 添加 `test` 可选依赖组（playwright、pytest-asyncio），`dev` 组包含 `test`
- [x] 配置 pytest：注册 `integration` marker、`asyncio_mode = auto`
- [x] 创建 `tests/integration/__init__.py`
- [x] 创建 `tests/integration/conftest.py`：TestApp、Playwright/browser/page fixture、--headed/--headless 选项
- [x] 编写第一个验证用例：Button 点击 → 后端事件触发 → 断言前后端状态
- [x] 编写多 viewport 测试用例：两个 page 连接同一 View，验证状态同步
- [x] 验证三种浏览器模式均可用
