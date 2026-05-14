# 麻将 Demo 设计规范

**状态**：✅ 已完成
**日期**：2026-04-19
**类型**：功能设计

## 需求

用四人麻将作为载体，展示 mutgui 的**多设备多视图、后端统一控制**能力。

设想场景：牌桌是一台电脑或 iPad，每个玩家一部手机。每个设备显示不同内容，全部由后端统一驱动。

第一版目标是展示这种形式，不追求视觉效果像游戏。

核心展示点：
1. 同一份游戏状态，5 个不同视图（1 牌桌 + 4 玩家）
2. 后端决定每个客户端看到什么
3. 一个客户端的操作实时反映到其他客户端

### 入口与导航

- 单入口：所有设备打开同一个 URL
- 默认进入牌桌视图（URL 无 hash 时自动定向到 `#table`）
- 牌桌上点击座位导航到对应玩家视图（修改 hash 为 `#east` / `#south` / `#west` / `#north`）
- 刷新页面保持当前视图（根据 hash 恢复）
- 支持多标签：一个标签 `#table` 看牌桌，另一个 `#east` 当东家

### 牌桌视图

- 俯视全局，显示四家的公开信息（弃牌、明牌）
- 手牌显示为背面（牌数可见，内容不可见）
- 管理操作：重新发牌
- 四个座位位置可点击，导航到对应玩家视图

### 玩家视图

- 第一人称视角，显示自己的手牌（正面）
- 出牌操作：点击手牌打出
- 摸牌操作：从牌墙取一张
- 返回牌桌按钮

### 视觉风格

- Unicode 麻将字符（🀇🀈🀉🀊...），不做自定义组件库
- 使用 antd 组件做布局和交互控件
- 先能用，后美化

### 游戏规则范围

第一版：
- 发牌（洗牌 + 每家 13 张）
- 轮流摸牌、出牌
- 不实现吃、碰、杠、胡判定
- 玩家手动管理手牌顺序（或后端基本排序）

后续可迭代：
- 吃碰杠胡判定
- LLM 玩家

## 关键参考

- `docs/design/framework-capabilities.md` — mutgui 框架能力参考
- `demo/app.py` — 现有 demo（View 嵌套 + VirtualList，Starlette + WebSocket）
- `src/mutgui/view.py` — View 声明
- `src/mutgui/viewport.py` — ViewPort 声明
- `src/mutgui/events.py` — Bind / Callback 事件
- `frontend/src/standalone.tsx` — 前端入口，`MutguiApp.mount()`
- `frontend/src/registry.ts` — 组件解析链

## 设计方案

### 架构总览

```
MahjongGame（牌局状态）
  ├── TableView（牌桌视图）──── ViewPort × N（看牌桌的标签页）
  ├── PlayerView("east") ──── ViewPort × N（看东家的标签页）
  ├── PlayerView("south") ─── ViewPort × N
  ├── PlayerView("west") ──── ViewPort × N
  └── PlayerView("north") ─── ViewPort × N
```

5 个 View 实例共享同一个 `MahjongGame` 对象。Game 状态变化时 `invalidate()` 所有相关 View，每个 ViewPort 收到各自该看到的内容。

### 视图选择机制

WebSocket 连接时通过查询参数传递视图选择：`ws://host/ws?view=east`

前端 `MutguiApp.mount()` 目前不支持传参给 WebSocket URL，需要在 HTML 模板中根据 hash 构造 WebSocket URL：

```javascript
// 前端：读 hash 构造 ws URL
const hash = location.hash.slice(1) || 'table';
if (!location.hash) history.replaceState(null, '', '#table');
const wsUrl = `ws://${location.host}/ws?view=${hash}`;
MutguiApp.mount(document.getElementById('app'), wsUrl);
```

后端根据 `?view=` 参数将 ViewPort 绑定到对应 View。

### 视图间导航

牌桌上点击座位 → 前端 `location.hash = '#east'` → 页面 reload → 重新连接 WebSocket（带新 view 参数）→ 绑定到 PlayerView。

简单直接，不需要框架层面的"视图切换"能力。hash 变化触发页面刷新即可（利用浏览器原生行为而不是 SPA 路由——让实现保持最简）。

### 牌局数据模型

```python
class Seat(Enum):
    EAST = "east"
    SOUTH = "south"
    WEST = "west"
    NORTH = "north"

class MahjongGame:
    wall: list[str]                    # 牌墙（未摸的牌）
    hands: dict[Seat, list[str]]       # 4 家手牌
    discards: dict[Seat, list[str]]    # 4 家弃牌
    current_turn: Seat | None          # 当前轮到谁（None = 未开局）

    def deal(self) -> None: ...        # 洗牌发牌
    def draw(self, seat: Seat) -> str: ...       # 摸牌
    def discard(self, seat: Seat, tile: str) -> None: ...  # 出牌
```

牌用字符串标识：`"1m"`~`"9m"`（万）、`"1p"`~`"9p"`（筒）、`"1s"`~`"9s"`（条）、`"east"` `"south"` `"west"` `"north"`（风）、`"zhong"` `"fa"` `"bai"`（箭）。

Unicode 映射：`"1m"` → `🀇`，`"2m"` → `🀈`，... 后端渲染时直接输出 Unicode 字符。

### TableView 渲染

```
         北家弃牌区
    ┌─────────────────┐
    │  🀫🀫🀫🀫...（北·13张）│
西  │                   │ 东
家  │    公共信息区      │ 家
弃  │  牌墙剩余: 70     │ 弃
牌  │  当前: 东家        │ 牌
区  │                   │ 区
    │  🀫🀫🀫🀫...（南·13张）│
    └─────────────────┘
         南家弃牌区

    [重新发牌]
```

- 四个方位显示手牌背面 `🀫`（或 `🀪`）+ 张数
- 各家弃牌正面显示
- 方位文字可点击，导航到对应玩家视图
- 管理按钮：重新发牌

### PlayerView 渲染

```
    对面（北家）: 🀫×13  弃牌: 🀇🀈
    ─────────────────────
    左家（西家）: 🀫×13  弃牌: 🀉
    右家（东家）: 🀫×13  弃牌: 🀊
    ─────────────────────
    弃牌区: 🀇 🀈 🀉
    ─────────────────────
    我的手牌（南家）:
    🀇 🀈 🀉 🀊 🀋 🀌 🀍 🀎 🀏 🀙 🀚 🀛 🀜
    （点击出牌）

    [摸牌]  [返回牌桌]
```

- 自己手牌正面显示，可点击出牌
- 其他三家手牌背面 + 张数
- 所有弃牌正面显示
- 摸牌按钮（轮到自己时可用）

### 文件结构

单文件 `demo/games/mahjong.py`，放在独立的 `games/` 分类下，便于未来继续添加其他游戏 demo：

```bash
cd mutgui
python -m demo.games.mahjong
```

通过 Gallery 访问时建议使用 `/games/mahjong/`；结构参照 `app.py`：WebSocketChannel → Game + Views → Starlette routes → uvicorn。

### 不做自定义前端组件

全部使用 antd 组件 + Unicode 字符：
- 布局：antd `Row`/`Col`/`Card`/`Space`/`Divider`
- 交互：antd `Button`
- 牌面：Unicode 字符作为 `span` 文本，通过 `style.fontSize` 放大显示
- 牌背：`🀫` 字符

不需要新建前端组件库，不需要 `npm run build`。

## 实施步骤清单

- [x] 实现牌局数据模型（Seat 枚举、牌定义、Unicode 映射、MahjongGame 类：洗牌/发牌/摸牌/出牌）
- [x] 实现 TableView（俯视全局：四家手牌背面+张数、弃牌正面、牌墙剩余、座位可点击导航、重新发牌按钮）
- [x] 实现 PlayerView（第一人称：自己手牌正面可点击出牌、其他三家背面+弃牌、摸牌按钮、返回牌桌按钮）
- [x] 实现 WebSocket 路由（解析 `?view=` 参数，绑定对应 View；HTML 模板读 hash 构造 ws URL、无 hash 自动定向 `#table`）
- [x] 实现 Starlette 应用入口（路由、静态文件挂载、uvicorn 启动端口 8081）
- [x] 启动测试（多标签页验证：牌桌视图、玩家视图、跨视图操作同步、刷新保持视图）

## V2 设计方案：数字牌桌 + 完整操作

> V1 实施中发现：Callback kwargs 是提取路径不是常量，需用闭包传值；导航用 `<a>` 标签 + hashchange 监听而非 Callback。

### 核心设计变更：数字牌桌模型

V1 用 `current_turn` 强制轮次。V2 改为**线下麻将思路**——系统提供场地和操作，规矩靠玩家口头协商。

**不强制轮次**：任何玩家随时可以执行任何操作，系统只做基本合法性校验（你手里有没有这些牌），不管该不该你操作。

**提示而非强制**：根据上一次操作自然推导当前该谁操作，显示提示文字。

```python
# 提示推导规则（纯提示，不阻止操作）
出牌后 → 提示下家摸牌
摸牌后 → 提示摸牌者出牌
碰/吃后 → 提示碰/吃者出牌
```

### 选牌机制

点击手牌不再直接出牌，改为**选中 → 确认**两步：

- 点击手牌 → 该牌上移（`marginTop: -12px`）标记为选中
- 再次点击同一张 → 取消选中
- 点击另一张 → 切换选中
- 点"出牌"按钮 → 打出选中的牌

选中状态存储在 PlayerView（`selected_index: int | None`），不影响 Game 模型。

出牌按钮动态文案：未选中时灰色"请选牌"，选中时高亮"出 🀇"。

数据结构用 `selected_indices: list[int]` 预留多选（吃需要选 2 张）。

### 牌局数据模型变更

```python
@dataclass
class Meld:
    type: str              # "chi" / "pong" / "kong"
    tiles: list[str]       # 组成牌
    source_seat: Seat      # 来源（谁打的牌被碰/吃）

class MahjongGame:
    wall: list[str]
    hands: dict[Seat, list[str]]
    discards: dict[Seat, list[str]]
    melds: dict[Seat, list[Meld]]          # 新增：亮出的组合
    last_discard: tuple[Seat, str] | None  # 新增：最后打出的牌（碰吃来源）
    hint: tuple[Seat, str] | None          # 新增：提示（seat, "draw"/"discard"）

    # V1 保留
    def deal(self) -> None: ...
    def draw(self, seat: Seat) -> str: ...
    def discard(self, seat: Seat, tile: str) -> None: ...

    # V2 新增
    def pong(self, seat: Seat) -> None: ...
    def chi(self, seat: Seat, tile1: str, tile2: str) -> None: ...
    def kong(self, seat: Seat) -> None: ...
```

去掉 `current_turn`，用 `hint` 替代（纯提示）。`last_discard` 被碰/吃/下家摸牌后清空。

### 操作定义

| 操作 | 校验 | 效果 | 提示更新 |
|------|------|------|----------|
| **摸牌** | 牌墙非空 | 从牌墙取 1 张加入手牌 | → 提示该玩家出牌 |
| **出牌** | 手里有该牌 | 手牌移除，加入弃牌，设为 last_discard | → 提示下家摸牌 |
| **碰** | last_discard 存在，手里有 2 张相同 | 取走 last_discard + 手中 2 张 → 亮出 Meld | → 提示碰者出牌 |
| **吃** | last_discard 存在，手中 2 张能组成顺子 | 取走 last_discard + 手中 2 张 → 亮出 Meld | → 提示吃者出牌 |
| **明杠** | last_discard 存在，手里有 3 张相同 | 取走 last_discard + 手中 3 张 → 亮出 Meld，补摸 1 张 | → 提示杠者出牌 |
| **暗杠** | 手里有 4 张相同 | 手中 4 张 → 亮出 Meld（背面），补摸 1 张 | → 提示杠者出牌 |
| **胡** | 不校验（玩家自行判断） | 声明胡牌，游戏结束 | → 显示结果 |

碰/吃/杠成功后清空 `last_discard`（防止重复碰吃）。摸牌也清空 `last_discard`（表示无人抢，正常轮转）。

### PlayerView 操作区

```
我的手牌:
🀇 🀈 🀉 🀊 🀋 🀌 🀍 🀎 🀏 🀙 🀚 🀛 🀜
     ↑ 选中（上移）

[摸牌] [出 🀊] [碰] [吃] [杠] [胡]  [返回牌桌]
```

按钮可用性根据当前状态灰显（提示性，不强制）：
- "碰"：有 last_discard 且手里有 2 张相同 → 高亮
- "吃"：有 last_discard 且手里有能组顺子的牌 → 高亮（点击后需选 2 张确认）
- "杠"：有 last_discard 且手里有 3 张相同，或手里有 4 张相同 → 高亮
- "出牌"：有选中的牌 → 高亮，文案显示选中的牌

### TableView 变更

牌桌视图新增亮牌区（melds）展示：

```
东
🀫🀫🀫🀫🀫🀫🀫🀫🀫🀫  亮: [🀇🀇🀇碰]
弃: 🀉 🀊
```

提示信息在牌桌中央显示（替代 V1 的"轮到：东"强制文案）：
- "提示：东家摸牌"
- "提示：南家出牌"

### 实施顺序

按增量迭代，每步可独立验证：

1. 选牌机制 + 出牌确认（纯 UI 交互改进，不改 Game 模型）
2. 去掉强制轮次，改为 hint 提示
3. 添加 Meld 数据结构 + 碰操作 + 亮牌区渲染
4. 添加吃操作（多选 + 顺子校验）
5. 添加杠操作（明杠/暗杠）
6. 添加胡声明

## 本轮实现范围（2026-04-30）

- 本轮先**不做手动排序**，继续保持后端自动整理手牌。
- 吃 / 碰 / 杠 / 胡必须做**基本合法性判断**，按钮不是任意时刻都可操作：
  - 吃：仅最后弃牌的下家可用，且选中的 2 张手牌能和最后弃牌组成顺子
  - 碰：最后弃牌存在，且手里至少有 2 张同牌
  - 杠：支持明杠 / 暗杠；明杠要求最后弃牌存在且手里有 3 张同牌，暗杠要求当前操作家手里选中 4 张同牌
  - 胡：仅在已开局且当前存在可胡场景时可声明（自摸时轮到自己出牌，或别人刚打出最后一张弃牌），并且当前牌型必须满足**基础和牌结构：4 组面子 + 1 对将**；本轮先不支持七对、十三幺等特殊牌型
- 增加隐藏的 `/all` 调试入口：不在普通导航中展示，但知道 URL 时可进入同屏四家调试页。

## 当前 UX 约定（2026-04-30）

- 玩家手牌改为**单选**：摸到的牌默认选中，便于直接出牌。
- 主操作按钮文案保持固定，避免因状态切换导致界面跳动：
  - 固定操作位顺序为 `胡 / 杠 / 吃 / 碰 / 主操作`
  - 主操作按钮在 `摸牌` / `出牌` 间切换（都为两个字，减少跳动）
  - 采用左胡右摸的顺序，适配默认右手操作习惯
- 牌墙剩余数量显示在提示行，不再放进“摸牌”按钮文案。
- 碰、明杠、胡不需要预先选牌；暗杠只需单选一个已有 4 张的牌种。
- 吃牌分两种：
  - 只有一个合法组合时，直接点固定的“吃”按钮
  - 有多个合法组合时，显示固定的“吃牌方案按钮”，而不是依赖多选
- 自己的亮牌与手牌显示在同一行；弃牌区域始终保留占位，减少页面高度波动。

## AI 托管（2026-04-30）

- 牌桌视图可按座位切换 `切到AI / 切回人工`。
- AI 托管开启后，该座位的人类操作按钮禁用，由后端自动执行。
- AI 每次动作前等待 **1 秒**，一次只执行一步（摸 / 打 / 吃 / 碰 / 杠 / 胡）。
- AI 策略目标是“合理但不强”：
  - 能胡就胡
  - 有机会时会考虑杠、碰、吃
  - 常规出牌时优先打出孤张、边张、价值较低的牌

## 实施步骤清单

- [x] 更新麻将牌局模型，改成提示型流程并加入吃碰杠胡、亮牌与赢家状态
- [x] 更新牌桌视图与玩家视图，支持选牌确认、操作按钮合法性、亮牌区与返回导航
- [x] 增加 `/all` 隐藏调试页，同屏操作四家并观察公共状态
- [x] 补充测试，覆盖吃碰杠胡合法性与调试入口

## 测试验证

- `python -m pytest -q tests\test_mahjong_demo.py tests\test_theming_demo.py`
- `python -m pytest -q tests --ignore=tests\integration`
- 当前全量 `python -m pytest -q` 在仓库现状下仍会因缺少 `playwright` 依赖而在 `tests/integration/` 收集阶段失败，本轮改动未引入新的失败项
