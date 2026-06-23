"""VirtualList 展示 — 大列表虚拟滚动 + Inline 编辑 + 可变高度测试。"""
from __future__ import annotations

from typing import Any, cast

import mutobj

from mutgui import View, ViewBlock, Bind, Callback, VirtualList, VirtualListItemAdapter

from demo.framework import MutguiRoute, DemoApp


# 不同长度 description，测试 VirtualList 对可变高度 item 的处理
_DESCRIPTIONS: list[str] = [
    "",  # 空，最小高度
    "Short bio.",  # 1 行
    "Experienced developer.\nLoves clean code and architecture.",  # 2 行
    "Senior engineer in distributed systems.\nLed multiple large-scale projects.\nMentored junior developers.",  # 3 行
    "Full-stack developer, 10+ years.\nExpert in Python, TypeScript, React.\nOpen-source contributor.\nHiking, photography, coffee.",  # 4 行
    "Lorem ipsum dolor sit amet.\nConsectetur adipiscing elit.\nSed do eiusmod tempor incididunt.\nUt labore et dolore magna aliqua.\nUt enim ad minim veniam.",  # 5 行
]


class RecordItemView(View):
    """单条记录 View — 支持 display / inline-edit 双模式。

    display 模式：只读展示 name / age / plan / description + Edit / Del 按钮。
    edit 模式：内联表单（Input / InputNumber / TextArea）+ Save / Cancel 按钮。
    """

    uid: int = 0
    name: str = ""
    age: int = 0
    plan: str = ""
    description: str = ""

    # Inline 编辑状态 — 父级直接写入 editing_uid 再 invalidate 本 View
    editing_uid: int | None = None
    # 编辑副本：Bind 绑定到这些字段，不影响原始 display 字段
    edit_name: str = ""
    edit_age: int = 18
    edit_plan: str = ""
    edit_description: str = ""

    on_edit_start: Any = None     # Callback(uid) — 用户点击 Edit
    on_inline_save: Any = None    # Callback(uid, name, age, plan, description)
    on_delete: Any = None         # Callback(uid)
    on_cancel: Any = None         # Callback(uid) — 用户取消编辑

    @property
    def _is_editing(self) -> bool:
        return self.editing_uid == self.uid

    def render(self) -> ViewBlock:
        if self._is_editing:
            return self._render_edit()
        return self._render_display()

    # ---- display mode ----

    def _render_display(self) -> ViewBlock:
        desc_children: list[Any]
        if self.description:
            desc_children = [
                {"$component": "antd.Typography.Paragraph", "$id": "desc",
                 "type": "secondary",
                 "style": {"marginBottom": 0, "whiteSpace": "pre-wrap"},
                 "children": self.description},
            ]
        else:
            desc_children = [
                {"$component": "antd.Typography.Text", "$id": "desc",
                 "type": "secondary",
                 "style": {"fontSize": "12px"},
                 "children": "(no description)"},
            ]

        return ViewBlock([{
            "$component": "antd.Row", "$id": "row",
            "wrap": False,
            "style": {"lineHeight": "32px", "flexWrap": "nowrap", "alignItems": "flex-start",
                      "padding": "4px 0"},
            "$children": [
                {"$component": "antd.Col", "$id": "c-idx", "flex": "50px",
                 "$children": [
                     {"$component": "antd.Typography.Text", "$id": "idx",
                      "type": "secondary", "children": f"#{self.uid}"},
                 ]},
                {"$component": "antd.Col", "$id": "c-name", "flex": "90px",
                 "$children": [
                     {"$component": "antd.Typography.Text", "$id": "name",
                      "strong": True, "children": self.name},
                 ]},
                {"$component": "antd.Col", "$id": "c-age", "flex": "50px",
                 "$children": [
                     {"$component": "antd.Typography.Text", "$id": "age",
                      "children": str(self.age)},
                 ]},
                {"$component": "antd.Col", "$id": "c-plan", "flex": "100px",
                 "$children": [
                     {"$component": "antd.Tag", "$id": "plan",
                      "color": "blue", "children": self.plan},
                 ]},
                {"$component": "antd.Col", "$id": "c-desc", "flex": "auto",
                 "$children": desc_children},
                {"$component": "antd.Col", "$id": "c-actions", "flex": "none",
                 "$children": [
                     {"$component": "antd.Space", "$id": "btns", "size": 4,
                      "$children": [
                          {"$component": "antd.Button", "$id": "edit",
                           "size": "small", "children": "Edit",
                           "onClick": Callback(self._do_edit)},
                          {"$component": "antd.Button", "$id": "del",
                           "size": "small", "danger": True,
                           "children": "Del",
                           "onClick": Callback(self._do_delete)},
                      ]},
                 ]},
            ],
        }])

    # ---- inline edit mode ----

    def _render_edit(self) -> ViewBlock:
        return ViewBlock([{
            "$component": "antd.Row", "$id": "row-edit",
            "wrap": False,
            "style": {"lineHeight": "32px", "flexWrap": "nowrap", "alignItems": "flex-start",
                      "background": "#f6ffed", "border": "1px solid #b7eb8f",
                      "borderRadius": "4px", "padding": "6px 0"},
            "$children": [
                {"$component": "antd.Col", "$id": "c-idx", "flex": "50px",
                 "$children": [
                     {"$component": "antd.Typography.Text", "$id": "idx",
                      "type": "secondary", "children": f"#{self.uid}"},
                 ]},
                {"$component": "antd.Col", "$id": "c-name", "flex": "90px",
                 "$children": [
                     {"$component": "antd.Input", "$id": "name-inp",
                      "value": self.edit_name, "size": "small",
                      "style": {"width": "100%"},
                      "onChange": Bind(self, "edit_name", "$0.target.value")},
                 ]},
                {"$component": "antd.Col", "$id": "c-age", "flex": "50px",
                 "$children": [
                     {"$component": "antd.InputNumber", "$id": "age-inp",
                      "value": self.edit_age, "min": 0, "max": 150,
                      "size": "small", "style": {"width": "100%"},
                      "onChange": Bind(self, "edit_age", "$0")},
                 ]},
                {"$component": "antd.Col", "$id": "c-plan", "flex": "100px",
                 "$children": [
                     {"$component": "antd.Input", "$id": "plan-inp",
                      "value": self.edit_plan, "size": "small",
                      "style": {"width": "100%"},
                      "onChange": Bind(self, "edit_plan", "$0.target.value")},
                 ]},
                {"$component": "antd.Col", "$id": "c-desc", "flex": "auto",
                 "$children": [
                     {"$component": "antd.Input.TextArea", "$id": "desc-inp",
                      "value": self.edit_description, "size": "small",
                      "autoSize": {"minRows": 1, "maxRows": 6},
                      "style": {"width": "100%", "fontSize": "12px"},
                      "onChange": Bind(self, "edit_description", "$0.target.value")},
                 ]},
                {"$component": "antd.Col", "$id": "c-actions", "flex": "none",
                 "$children": [
                     {"$component": "antd.Space", "$id": "btns", "size": 4,
                      "$children": [
                          {"$component": "antd.Button", "$id": "save",
                           "type": "primary", "size": "small", "children": "Save",
                           "onClick": Callback(self._do_save)},
                          {"$component": "antd.Button", "$id": "cancel",
                           "size": "small", "children": "Cancel",
                           "onClick": Callback(self._do_cancel)},
                      ]},
                 ]},
            ],
        }])

    def _do_edit(self) -> None:
        # 将原始字段拷贝到编辑副本，保证 Cancel 后原始数据不受影响
        self.edit_name = self.name
        self.edit_age = self.age
        self.edit_plan = self.plan
        self.edit_description = self.description
        if self.on_edit_start:
            self.on_edit_start(self.uid)

    def _do_save(self) -> None:
        if self.on_inline_save:
            self.on_inline_save(
                uid=self.uid,
                name=self.edit_name or "Anonymous",
                age=self.edit_age,
                plan=self.edit_plan or "Free",
                description=self.edit_description,
            )

    def _do_cancel(self) -> None:
        if self.on_cancel:
            self.on_cancel(self.uid)

    def _do_delete(self) -> None:
        if self.on_delete:
            self.on_delete(self.uid)


class RecordAdapter(VirtualListItemAdapter):
    """记录数据适配器 — 生成含不同长度 description 的测试数据。"""

    records: list[tuple[int, str, int, str, str]] = mutobj.field(default_factory=list)
    on_edit_start: Any = None
    on_inline_save: Any = None
    on_delete: Any = None
    on_cancel: Any = None
    _next_uid: int = 0

    def __init__(
        self,
        on_edit_start: Any = None,
        on_inline_save: Any = None,
        on_delete: Any = None,
        on_cancel: Any = None,
    ) -> None:
        super().__init__(
            on_edit_start=on_edit_start,
            on_inline_save=on_inline_save,
            on_delete=on_delete,
            on_cancel=on_cancel,
        )
        plans = ["Free", "Pro", "Enterprise"]
        for i in range(500):
            self._add(
                f"User-{i}",
                18 + (i % 50),
                plans[i % 3],
                _DESCRIPTIONS[i % len(_DESCRIPTIONS)],
            )

    def _add(self, name: str, age: int, plan: str, description: str = "") -> None:
        self.records.append((self._next_uid, name, age, plan, description))
        self._next_uid += 1

    @property
    def item_count(self) -> int:
        return len(self.records)

    def item_id(self, index: int) -> str:
        return f"rec-{self.records[index][0]}"

    def create_item_view(self, index: int) -> View:
        uid, name, age, plan, description = self.records[index]
        return RecordItemView(
            uid=uid,
            name=name,
            age=age,
            plan=plan,
            description=description,
            on_edit_start=self.on_edit_start,
            on_inline_save=self.on_inline_save,
            on_delete=self.on_delete,
            on_cancel=self.on_cancel,
        )

    def _find_by_uid(self, uid: int) -> int | None:
        for i, rec in enumerate(self.records):
            if rec[0] == uid:
                return i
        return None

    def add_record(self, name: str, age: int, plan: str, description: str = "") -> None:
        self._add(name, age, plan, description)
        self.invalidate()

    def update_record(self, uid: int, name: str, age: int, plan: str, description: str = "") -> None:
        index = self._find_by_uid(uid)
        if index is None:
            return
        self.records[index] = (uid, name, age, plan, description)
        item_id = self.item_id(index)
        for vl in self.virtual_lists:
            item_view = vl.get_item_view(item_id)
            if item_view:
                # 同步更新 item view 的显示字段 + 清除编辑状态
                iv = cast(RecordItemView, item_view)
                iv.name = name
                iv.age = age
                iv.plan = plan
                iv.description = description
                iv.editing_uid = None
                iv.invalidate()
        self.invalidate()

    def delete_record(self, uid: int) -> None:
        index = self._find_by_uid(uid)
        if index is None:
            return
        self.records.pop(index)
        self.invalidate()


class VirtualListView(View):
    """顶层 View — 顶部提供 Add 表单，列表中每条记录支持 inline 编辑。"""

    adapter: RecordAdapter
    record_list: VirtualList
    name: str = ""
    age: int = 18
    description: str = ""
    editing_uid: int | None = None
    message: str = ""

    def __init__(self) -> None:
        super().__init__()
        self.adapter = RecordAdapter(
            on_edit_start=self._on_edit,
            on_inline_save=self._on_inline_save,
            on_delete=self._on_delete,
            on_cancel=self._on_cancel,
        )
        self.record_list = VirtualList(
            id="records",
            adapter=self.adapter,
            estimated_item_height=50,  # 略高于默认值，适应含 description 的 item
        )

    # ---- inline edit 生命周期 ----

    def _on_edit(self, uid: int) -> None:
        """用户点击某项的 Edit 按钮：清除上一个编辑项，激活当前项。"""
        if self.editing_uid is not None and self.editing_uid != uid:
            self._set_item_editing(self.editing_uid, editing=False)
        self._set_item_editing(uid, editing=True)
        self.editing_uid = uid
        self.invalidate()

    def _on_inline_save(self, *, uid: int, name: str, age: int, plan: str, description: str) -> None:
        """用户点击 inline Save：持久化数据，item 自动回到 display 模式。"""
        self.adapter.update_record(uid, name, age, plan, description)
        self.editing_uid = None
        self.message = f"Updated #{uid}"
        self.invalidate()

    def _on_cancel(self, uid: int) -> None:
        """用户点击 inline Cancel：丢弃编辑副本，回到 display。"""
        self._set_item_editing(uid, editing=False)
        self.editing_uid = None
        self.message = ""
        self.invalidate()

    def _on_delete(self, uid: int) -> None:
        if self.editing_uid == uid:
            self.editing_uid = None
        self.adapter.delete_record(uid)
        self.message = f"Deleted #{uid}"
        self.invalidate()

    # ---- item view 编辑状态切换 ----

    def _set_item_editing(self, uid: int, editing: bool) -> None:
        idx = self.adapter._find_by_uid(uid)
        if idx is None:
            return
        item_id = self.adapter.item_id(idx)
        item_view = self.record_list.get_item_view(item_id)
        if item_view:
            iv = cast(RecordItemView, item_view)
            iv.editing_uid = uid if editing else None
            iv.invalidate()

    # ---- Add 新记录 ----

    def _on_add(self) -> None:
        name = self.name or "Anonymous"
        self.adapter.add_record(name, self.age, "Free", self.description)
        self.message = f"Added: {name}"
        self.name = ""
        self.age = 18
        self.description = ""
        self.invalidate()

    # ---- render ----

    def render(self) -> ViewBlock:
        action_items: list[Any] = [
            {"$component": "antd.Input", "$id": "name",
             "value": self.name, "placeholder": "Name", "size": "small",
             "style": {"width": 100},
             "onChange": Bind(self, "name", "$0.target.value")},
            {"$component": "antd.InputNumber", "$id": "age",
             "value": self.age, "min": 0, "max": 150, "size": "small",
             "style": {"width": 70},
             "onChange": Bind(self, "age", "$0")},
            {"$component": "antd.Input.TextArea", "$id": "desc-new",
             "value": self.description, "placeholder": "Description",
             "size": "small", "autoSize": {"minRows": 1, "maxRows": 3},
             "style": {"width": 200, "verticalAlign": "top"},
             "onChange": Bind(self, "description", "$0.target.value")},
            {"$component": "antd.Button", "$id": "add",
             "type": "primary", "size": "small", "children": "Add",
             "onClick": Callback(self._on_add)},
        ]
        if self.editing_uid is not None:
            action_items.append(
                {"$component": "antd.Typography.Text", "$id": "editing-hint",
                 "type": "warning",
                 "children": f"Editing #{self.editing_uid} inline ⟶ scroll to see green row"},
            )
        if self.message:
            action_items.append(
                {"$component": "antd.Typography.Text", "$id": "msg",
                 "type": "success", "children": self.message},
            )

        return ViewBlock([{
            "$component": "html.div", "$id": "root",
            "style": {"height": "100%", "display": "flex", "flexDirection": "column"},
            "$children": [
                {"$component": "antd.Typography.Title", "$id": "title",
                 "level": 3,
                 "style": {"marginTop": 0},
                 "children": (
                     f"mutgui — VirtualList ({self.adapter.item_count} items, variable heights)"
                 )},
                {"$component": "antd.Space", "$id": "actions",
                 "$children": action_items, "wrap": True},
                {"$component": "antd.Divider", "$id": "div",
                 "style": {"margin": "12px 0"}},
                {"$component": "html.div", "$id": "list-wrapper",
                 "style": {"flex": 1, "overflow": "hidden",
                           "display": "flex", "flexDirection": "column"},
                 "$children": [self.record_list]},
            ],
        }])


app = DemoApp([
    MutguiRoute("/", VirtualListView(), title="VirtualList — Inline Edit + Variable Height", layout="fullscreen"),
])

if __name__ == "__main__":
    app.run()
