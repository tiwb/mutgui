# VirtualList 组件设计规范

**状态**：✅ 已完成
**日期**：2026-04-17
**类型**：功能设计

## 需求

1. 实现 VirtualList 组件，支持大量 item（上万级）的虚拟滚动
2. 每个 item 是独立的 View，支持独立更新和状态保持
3. 支持树形结构（后端压平为扁平列表，前端只看到扁平列表）
4. 支持可变高度 item（内容驱动高度，渲染后测量）
5. 为属性编辑器、文件浏览器、Outliner 等业务提供基础容器

### 前置依赖

- `feature-framework-core.md` — 基础框架（协议、事件、View/ViewPort）
- `feature-view-nesting.md` — View 嵌套（`$view`、`$id`、MutguiView、事件路由）
- `feature-session-sharing.md` — Declaration 化（View/Channel/ViewPort）与多客户端支持
- `refactor-view-render-ownership.md` — 渲染职责归 View（invalidate → deferred render → push）

## 关键参考

### 外部参考

- **Blazor `<Virtualize>`** — `ItemsProvider` 回调（count + fetch），`@key` stable ID，`<Placeholder>` 加载占位
- **Vaadin `DataProvider`** — `fetch(offset, limit)` + `count()`，`refreshItem(item)` 单 item 刷新，层次化 `HierarchicalDataProvider` 支持树
- **Android RecyclerView** — `Adapter`（create + bind + viewType），`DiffUtil`（areItemsTheSame + areContentsTheSame），按 viewType 分桶的 RecycledViewPool
- **Phoenix LiveView Streams** — `stream_insert/delete` 增量操作，DOM id 驱动复用

### 设计参照对比

| | mutgui VirtualList |
|---|---|
| 数据耦合 | View 不碰数据 |
| 复用机制 | item_id 匹配（ID 驱动） |
| item 表示 | View（独立更新单元） |
| 网络延迟 | 有（WebSocket，需占位符） |

## 设计方案

### 核心模型

VirtualList 的解耦模型：**View 不碰数据，只管 count + ID + item View 生命周期**。数据通过 Adapter 桥接。

```
VirtualList（View）
├── 管理：item_count、viewport、item View 生命周期
├── 不持有：业务数据
└── items
    ├── Item View 0（View）— 独立状态、独立渲染、独立事件
    ├── Item View 1（View）
    └── ...（只有可见 + overscan 范围内的 item 有 View 实例）

VirtualListItemAdapter（应用提供）
├── item_count → 总数
├── item_id(index) → stable ID
└── create_item_view(index) → 创建 item View
```

### VirtualListItemAdapter —— 数据到 UI 的桥接

应用继承此类，提供业务数据到 View 的映射。命名来源：它**适配**业务 Model（Document / ItemsModel）为 VirtualList 能消费的 View。全称 `VirtualListItemAdapter` 自解释——VirtualList 的 Item 适配器。

```python
class VirtualListItemAdapter:
    """应用继承，VirtualList 消费。"""

    @property
    def item_count(self) -> int:
        """当前可用的 item 总数。
        固定列表：len(items)。
        增量加载：len(loaded_items)，加载更多后 invalidate()。
        未来可扩展为 item_range 支持双向增长（如聊天窗口）。"""
        ...

    def item_id(self, index: int) -> str:
        """返回 index 位置的 stable ID。
        驱动 View 复用——同一 id 的 View 实例保持不变。
        业务对象通常自带 ID；简单列表可用 str(index)。"""
        ...

    def create_item_view(self, index: int) -> View:
        """创建新的 item View（不需要设 id，VirtualList 自动赋值）。
        仅在 VirtualList 找不到匹配 id 的已有 View 时调用。"""
        ...

    def invalidate(self):
        """通知 VirtualList 数据已变化（count 或 id 映射变了）。
        VirtualList 会重新查询 adapter，对比 id，复用/创建/销毁 View。"""
        self._virtual_list.invalidate()
```

### Item 是 View

每个 item 是独立的 View（参考 `feature-view-nesting.md`）。理由：

1. **独立更新** — 修改一个属性值只推送这一个 item，不影响其他 4999 个
2. **状态保持** — item View 持有状态（展开的子树、编辑中的输入值），滚出去再回来状态不丢（ID 匹配复用）
3. **ID 作用域** — 多个 item 内部组件有相同的 `$id`（如 `"value"`），各自 View 作用域隔离

### ID 驱动的 View 复用

VirtualList 内部维护 `id → View` 映射。核心逻辑：

```
viewport 变化或 adapter.invalidate() 时：
1. 查询 viewport 范围 [start, end) 的 item_id 列表
2. 对比已有的 id → View 映射：
   ┌─ id 已存在 → 复用 View 实例（状态保持，可能触发 re-render）
   ├─ id 是新的 → 调 adapter.create_item_view() 创建新 View
   └─ id 消失 → 销毁 View（或进入缓存池，后续由框架决策）
```

**复用的关键是 ID 匹配，不是对象池**。开发者只需要给 item 一个稳定 ID，VirtualList 自动处理。

**框架层面**：VirtualList.render() 返回的 `$children` 中的 View 实例列表变化时，框架（`_process_items`）自动对比上次 render 结果，为新出现的子 View 创建 ViewPort，为消失的子 View 销毁 ViewPort。VirtualList 不需要手动管理推送。

**为什么不用 bind（rebind 到新数据）**：View 持有数据引用，数据变了 View 自己 re-render。不需要"重新绑定到另一条数据"的机制。

### 脏标记合并刷新

多次变更合并为一次推送：

```python
adapter.invalidate()  # 标记 dirty
adapter.invalidate()  # 多次调用
# → 合并为一次：invalidate() → call_soon → re-render → push wire_tree
```

### 协议

VirtualList 是一个 View，在父 View 的 render 树中通过 `$view` 出现，自身 render 中声明 `$component`：

#### VirtualList 在父 View 的 render 中

父 View render 时，VirtualList 作为 View 实例出现在返回值中。框架自动转换为 `$view` 节点：

```json
{"$view": "properties"}
```

VirtualList 的 `$component`、`itemCount` 等 props 在自身 render 输出中，作为独立 render 消息推送。

#### VirtualList 自身的 render（独立推送）

```json
{"type": "render", "viewId": ["properties"], "tree": [
    {"$component": "VirtualList", "$id": "list", "itemCount": 5000,
     "onViewport": {"$": "handler", "extract": {"start": "$0.start", "end": "$0.end"}},
     "$children": [
         {"$view": 0},
         {"$view": 1}
     ]}
]}
```

- `$component` = 用 VirtualList 前端组件渲染（滚动容器、虚拟化）
- `$id` = 事件路由标识，`onViewport` handler 依赖此字段
- `itemCount` = 前端据此估算总高度、渲染滚动条
- `$children` 中的 `$view` 节点 = 当前 viewport 内的 item View，由框架标准子 View 机制管理

#### item View 的渲染（独立推送）

每个 item View 独立推送自己的 render 结果（`viewId` 为数组格式）：

```json
{"type": "render", "viewId": ["properties", "prop_opacity"], "tree": [
    {"$component": "Text", "$id": "label", "children": "Opacity"},
    {"$component": "InputNumber", "$id": "value", "value": 0.8, "min": 0, "max": 1,
     "onChange": {"$": "handler", "extract": {"value": "$0"}}}
]}
```

#### viewport 事件（Frontend → Backend）

```json
{"source": ["properties", "list"], "event": "onViewport", "data": {"start": 100, "end": 125}}
```

前端根据滚动位置 + 已测量高度算出可见 index 范围，发送给后端。source 数组由 ScopeProvider 自动拼接：`"properties"`（View scope）+ `"list"`（组件 `$id`）。

#### item 内部事件（Frontend → Backend）

```json
{"source": ["properties", "prop_opacity", "value"], "event": "onChange", "data": {"value": 0.65}}
```

事件路径由 View 嵌套自动拼接（MutguiView 的 ScopeProvider 机制），每段对应一层 View scope 或组件 `$id`。

### 后端 API

#### VirtualList 类

```python
class VirtualList(View):
    """虚拟滚动列表。管理 item View 的生命周期。"""

    def __init__(self, id: str, adapter: VirtualListItemAdapter):
        self.id = id
        self.adapter = adapter
        adapter._virtual_list = self  # 反向引用，供 invalidate() 使用
        self._item_views: dict[str, View] = {}  # id → View
        self._viewport: tuple[int, int] = (0, 0)  # 当前 viewport range

    def render(self):
        """返回 VirtualList 容器 + 当前 viewport 内的 item View。

        每次 render 都重新查询 adapter（adapter.invalidate() 后
        数据可能已变），框架标准子 View 机制自动管理 ViewPort
        创建/复用/销毁（_process_items 对比 View 实例）。
        """
        self._refresh_visible()
        visible_items = [self._item_views[id]
                         for id in self._visible_ids]
        return {
            "$component": "VirtualList",
            "$id": "list",
            "itemCount": self.adapter.item_count,
            "onViewport": handler(self._on_viewport,
                                  start="$0.start", end="$0.end"),
            "$children": visible_items,
        }

    def _on_viewport(self, data: dict):
        """handler 回调：前端 viewport 变化时更新 viewport range。"""
        self._viewport = (data["start"], data["end"])
        # handler 调用后框架自动 invalidate → re-render → push

    def _refresh_visible(self):
        """根据当前 viewport range 重新查询 adapter，更新 visible items。

        统一入口：_on_viewport 和 adapter.invalidate() 都走这里。
        """
        start, end = self._viewport
        # 查询当前 viewport 的 id 列表
        new_ids = [self.adapter.item_id(i) for i in range(start, end)]
        # 创建新 item View（VirtualList 负责赋 id）
        for i, item_id in enumerate(new_ids):
            if item_id not in self._item_views:
                view = self.adapter.create_item_view(start + i)
                view.id = item_id  # VirtualList 赋 id，adapter 不需要关心
                self._item_views[item_id] = view
        # 清理不在 viewport 内的旧 View（v1 简单策略）
        visible_set = set(new_ids)
        for old_id in list(self._item_views):
            if old_id not in visible_set:
                del self._item_views[old_id]
        self._visible_ids = new_ids
```

### 前端设计

VirtualList 在前端是一个注册在 registry 中的 React 组件。它负责：

1. 滚动容器和虚拟化布局
2. 根据滚动位置计算可见 index 范围
3. 发送 `onViewport` 事件（通过框架 handler 机制，source 由 ScopeProvider 自动拼接）
4. 渲染 `$children`（框架已将 item View 渲染为 MutguiView 列表）
5. item 的高度测量和锚点滚动

```tsx
function VirtualListComponent({ itemCount, children, onViewport }) {
  // children = 框架递归渲染 $children 后的 MutguiView 列表（当前 viewport 内的 item）
  // onViewport = 框架从 $ handler 生成的事件函数
  // 滚动和虚拟化逻辑...

  return (
    <div className="virtual-list" onScroll={handleScroll}>
      {/* 占位区域（撑起滚动条） */}
      <div style={{ height: estimatedTotalHeight }} />
      {/* 可见 item — children 由框架从 $children 渲染而来 */}
      <div style={{ position: 'absolute', top: offsetTop }}>
        {children}
      </div>
    </div>
  );
}
```

#### 可变高度

采用渲染后测量方式：

1. 用估算高度（如 28px）做初始布局
2. item 渲染后测量真实 DOM 高度
3. 更新高度缓存，修正总高度估算
4. 锚点滚动保持视口稳定（"第 X 个 item 在视口顶部偏移 Y"）

高度完全是前端的事，后端不需要知道 item 高度。

#### 网络延迟

前端发送 viewport 请求到后端返回 item 数据之间有延迟。延迟期间显示 loading placeholder（骨架屏）。VirtualList 组件内置处理。

#### viewport 防抖

前端防抖（debounce viewport 事件，50-100ms），避免快速滚动时大量请求。

### 使用场景

#### 场景 1：属性编辑器

```python
class PropertyItemView(View):
    def __init__(self, prop):
        self.prop = prop

    def render(self):
        return [
            {"$component": "Text", "$id": "label",
             "children": self.prop.display_name},
            {"$component": "InputNumber", "$id": "value",
             "value": self.prop.value,
             "onChange": bind(self.prop, "value")},
        ]


class PropertyAdapter(VirtualListItemAdapter):
    def __init__(self, properties):
        self.properties = properties

    @property
    def item_count(self):
        return len(self.properties)

    def item_id(self, index):
        return self.properties[index].name  # 属性名天然唯一

    def create_item_view(self, index):
        return PropertyItemView(self.properties[index])


class EditorView(View):
    def __init__(self, document):
        self.prop_list = VirtualList(
            id="properties",
            adapter=PropertyAdapter(document.properties),
        )

    def render(self):
        return [
            {"$component": "Text", "children": "属性编辑器"},
            self.prop_list,
        ]
```

数据流：用户改 opacity → `bind` 触发 `prop.value = 0.65` → PropertyItemView re-render → 只推送这一个 item 的更新。

#### 场景 2：树形结构（展开/折叠）

```python
class TreeNodeView(View):
    def __init__(self, node, level, adapter):
        self.node = node
        self.level = level
        self.adapter = adapter

    def render(self):
        children = [
            {"$component": "Text", "$id": "label",
             "style": {"paddingLeft": self.level * 20},
             "children": self.node.name},
        ]
        if self.node.children:
            children.append(
                {"$component": "Button", "$id": "toggle",
                 "children": "▼" if self.node.expanded else "▶",
                 "onClick": handler(self.toggle)}
            )
        return children

    def toggle(self, data):
        self.node.expanded = not self.node.expanded
        self.adapter.rebuild_flat_list()
        self.adapter.invalidate()


class TreeAdapter(VirtualListItemAdapter):
    def __init__(self, root_nodes):
        self.root_nodes = root_nodes
        self.flat_items: list[tuple[TreeNode, int]] = []
        self.rebuild_flat_list()

    def rebuild_flat_list(self):
        self.flat_items = []
        for node in self.root_nodes:
            self._flatten(node, 0)

    def _flatten(self, node, level):
        self.flat_items.append((node, level))
        if node.expanded:
            for child in node.children:
                self._flatten(child, level + 1)

    @property
    def item_count(self):
        return len(self.flat_items)

    def item_id(self, index):
        return self.flat_items[index][0].id

    def create_item_view(self, index):
        node, level = self.flat_items[index]
        return TreeNodeView(node, level, self)
```

展开 B 节点时的复用：
```
展开前：[A, B, C, D]       id=[a, b, c, d]
展开后：[A, B, b1, b2, C, D]  id=[a, b, b1, b2, c, d]

VirtualList 对比 id：
  a, b → 已有 View，复用（不动）
  b1, b2 → 新 id → 调 create_item_view
  c, d → 已有 View，复用（位置变了，View 不重建）
```

#### 场景 3：简单列表

```python
class SimpleAdapter(VirtualListItemAdapter):
    def __init__(self, items: list[str]):
        self.items = items

    @property
    def item_count(self):
        return len(self.items)

    def item_id(self, index):
        return str(index)

    def create_item_view(self, index):
        return SimpleItemView(self.items[index])


class SimpleItemView(View):
    def __init__(self, text):
        self.text = text

    def render(self):
        return {"$component": "Text", "$id": "t", "children": self.text}
```

### 关键行为矩阵

| 时机 | VirtualList | Adapter | Item View |
|---|---|---|---|
| **首次渲染** | 推送容器描述（itemCount） | 被查询 item_count | 不存在 |
| **viewport 事件** | 查询 id 范围，匹配/创建 View | 被查询 item_id、create_item_view | 新创建的 View 首次 render |
| **滚动** | 新 viewport → 对比 id → 复用/创建/销毁 | 被查询 | 进入的：首次 render；离开的：销毁 |
| **item 值变化** | 不介入 | 不介入 | bind 触发 → invalidate() → deferred render → 只推送自己 |
| **结构变化**（展开/增删） | 收到 invalidate → re-render → 框架对比 $children | rebuild → invalidate() | 新增的：创建；ID 不变的：复用 |

## 已决策问题

### Q1: 无限列表 → item_count 永远是 int
**结论**：去掉 `item_count = None`。无限列表不是特殊模式，只是 count 会随时间增长的普通列表。adapter 加载更多数据后调 `invalidate()`，count 自然增加，滚动条变长。加载不到新数据 → count 不变 → 滚动自然停止。

未来如需双向增长（如聊天窗口往上加载历史），可将 `item_count` 扩展为 `item_range: range`（如 `range(-100, 200)`），表示 index 空间两端都能增长。v1 用 `item_count`（等价于 `range(0, count)`）。

### Q2: overscan（预加载）
**决策**：v1 支持。VirtualList 组件可配置 overscan 数量，viewport 事件的 start/end 包含 overscan 范围。默认值待实测确定。

### Q3: item View 销毁策略
**决策**：v1 简单处理——`_refresh_visible` 中清理不在 viewport 范围内的旧 View。如果性能测试显示创建成本高，v2 加 LRU 缓存。

### Q4: 多模板支持
**决策**：Adapter 的 `create_item_view(index)` 天然支持——根据 index 对应的数据类型返回不同的 View 子类即可。不需要额外的模板机制。

## 实施步骤清单

### 后端 — VirtualList + Adapter

- [x] 新建 `src/mutgui/virtual_list.py`：VirtualListItemAdapter 基类（item_count / item_id / create_item_view / invalidate）+ VirtualList(View) 类（__init__ / render / _on_viewport / _refresh_visible）
- [x] 更新 `src/mutgui/__init__.py`：导出 VirtualList 和 VirtualListItemAdapter

### 前端 — VirtualList React 组件

- [x] 新建 `frontend/src/virtual-list.tsx`：VirtualList 组件（滚动容器、估算总高度、viewport 计算、onViewport 防抖、children 定位）
- [x] 注册组件：在 `frontend/src/antd.ts` 将 VirtualList 加入 registry
- [x] 构建 standalone bundle（`npm run build`）

### 测试

- [x] 新建 `tests/test_virtual_list.py`：后端单元测试（VirtualList render 产出正确协议、_on_viewport 更新 viewport、_refresh_visible 创建/清理 View、adapter.invalidate 触发 re-render、item View 的 id 赋值）— 8 passed

### Demo

- [x] 扩展现有 demo/app.py：Submit 改为 Add，预填充 3000 条记录的 VirtualList，点 Add 追加新条目，验证大数据量虚拟滚动 + 动态增长

