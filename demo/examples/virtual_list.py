"""VirtualList 展示 — 大列表虚拟滚动 + CRUD 操作。"""
from __future__ import annotations

from typing import Any

import mutobj

from mutgui import View, ViewBlock, Bind, Callback, VirtualList, VirtualListItemAdapter

from demo.framework import MutguiRoute, DemoApp


class RecordItemView(View):
    uid: int = 0
    name: str = ""
    age: int = 0
    plan: str = ""
    on_edit: Any = None
    on_delete: Any = None

    def render(self) -> ViewBlock:
        return ViewBlock([{
            "$component": "antd.Row", "$id": "row",
            "wrap": False,
            "style": {"lineHeight": "32px", "flexWrap": "nowrap"},
            "$children": [
                {"$component": "antd.Col", "$id": "c-idx", "flex": "50px",
                 "$children": [
                     {"$component": "antd.Typography.Text", "$id": "idx",
                      "type": "secondary", "children": f"#{self.uid}"},
                 ]},
                {"$component": "antd.Col", "$id": "c-name", "flex": "auto",
                 "$children": [
                     {"$component": "antd.Typography.Text", "$id": "name",
                      "children": self.name},
                 ]},
                {"$component": "antd.Col", "$id": "c-age", "flex": "60px",
                 "$children": [
                     {"$component": "antd.Typography.Text", "$id": "age",
                      "children": str(self.age)},
                 ]},
                {"$component": "antd.Col", "$id": "c-plan", "flex": "100px",
                 "$children": [
                     {"$component": "antd.Typography.Text", "$id": "plan",
                      "children": self.plan},
                 ]},
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

    def _do_edit(self) -> None:
        if self.on_edit:
            self.on_edit(self.uid)

    def _do_delete(self) -> None:
        if self.on_delete:
            self.on_delete(self.uid)


class RecordAdapter(VirtualListItemAdapter):
    records: list[tuple[int, str, int, str]] = mutobj.field(default_factory=list)
    on_edit: Any = None
    on_delete: Any = None
    _next_uid: int = 0

    def __init__(self, on_edit: Any = None, on_delete: Any = None) -> None:
        super().__init__(on_edit=on_edit, on_delete=on_delete)
        plans = ["Free", "Pro", "Enterprise"]
        for i in range(100):
            self._add(f"User-{i}", 18 + (i % 50), plans[i % 3])

    def _add(self, name: str, age: int, plan: str) -> None:
        self.records.append((self._next_uid, name, age, plan))
        self._next_uid += 1

    @property
    def item_count(self) -> int:
        return len(self.records)

    def item_id(self, index: int) -> str:
        return f"rec-{self.records[index][0]}"

    def create_item_view(self, index: int) -> View:
        uid, name, age, plan = self.records[index]
        return RecordItemView(
            uid=uid, name=name, age=age, plan=plan,
            on_edit=self.on_edit, on_delete=self.on_delete,
        )

    def _find_by_uid(self, uid: int) -> int | None:
        for i, rec in enumerate(self.records):
            if rec[0] == uid:
                return i
        return None

    def add_record(self, name: str, age: int, plan: str) -> None:
        self._add(name, age, plan)
        self.invalidate()

    def update_record(self, uid: int, name: str, age: int, plan: str) -> None:
        index = self._find_by_uid(uid)
        if index is None:
            return
        self.records[index] = (uid, name, age, plan)
        item_id = self.item_id(index)
        for vl in self.virtual_lists:
            if item_id in vl.item_views:
                del vl.item_views[item_id]
        self.invalidate()

    def delete_record(self, uid: int) -> None:
        index = self._find_by_uid(uid)
        if index is None:
            return
        self.records.pop(index)
        self.invalidate()


class VirtualListView(View):
    def __init__(self) -> None:
        super().__init__()
        self.adapter = RecordAdapter(
            on_edit=self._on_edit, on_delete=self._on_delete,
        )
        self.record_list = VirtualList(id="records", adapter=self.adapter)
        self.name = ""
        self.age = 18
        self.editing_uid: int | None = None
        self.message = ""

    def _on_edit(self, uid: int) -> None:
        index = self.adapter._find_by_uid(uid)
        if index is None:
            return
        _, name, age, plan = self.adapter.records[index]
        self.name = name
        self.age = age
        self.editing_uid = uid
        self.message = f"Editing #{uid}"
        self.invalidate()

    def _on_delete(self, uid: int) -> None:
        if self.editing_uid == uid:
            self.editing_uid = None
        self.adapter.delete_record(uid)
        self.message = f"Deleted #{uid}"
        self.invalidate()

    def _on_save(self) -> None:
        name = self.name or "Anonymous"
        if self.editing_uid is not None:
            self.adapter.update_record(self.editing_uid, name, self.age, "Free")
            self.message = f"Updated #{self.editing_uid}"
            self.editing_uid = None
        else:
            self.adapter.add_record(name, self.age, "Free")
            self.message = f"Added: {name}"
        self.invalidate()

    def _on_cancel(self) -> None:
        self.editing_uid = None
        self.message = ""
        self.invalidate()

    def render(self) -> ViewBlock:
        is_editing = self.editing_uid is not None
        btn_label = "Save" if is_editing else "Add"

        action_items: list[Any] = [
            {"$component": "antd.Input", "$id": "name",
             "value": self.name, "placeholder": "Name", "size": "small",
             "style": {"width": 120},
             "onChange": Bind(self, "name", "$0.target.value")},
            {"$component": "antd.InputNumber", "$id": "age",
             "value": self.age, "min": 0, "max": 150, "size": "small",
             "onChange": Bind(self, "age", "$0")},
            {"$component": "antd.Button", "$id": "add",
             "type": "primary", "size": "small", "children": btn_label,
             "onClick": Callback(self._on_save)},
        ]
        if is_editing:
            action_items.append(
                {"$component": "antd.Button", "$id": "cancel",
                 "size": "small", "children": "Cancel",
                 "onClick": Callback(self._on_cancel)},
            )
        if self.message:
            action_items.append(
                {"$component": "antd.Typography.Text", "$id": "msg",
                 "type": "success", "children": self.message},
            )

        return ViewBlock([
            {"$component": "antd.Typography.Title", "$id": "title",
             "level": 3,
             "children": f"mutgui — VirtualList ({self.adapter.item_count} items)"},
            {"$component": "antd.Space", "$id": "actions", "$children": action_items},
            {"$component": "antd.Divider", "$id": "div",
             "style": {"margin": "12px 0"}},
            {"$component": "div", "$id": "list-wrapper",
             "style": {"height": 500, "display": "flex", "flexDirection": "column"},
             "$children": [self.record_list]},
        ])


app = DemoApp([
    MutguiRoute("/", VirtualListView(), title="VirtualList", layout="plain"),
])

if __name__ == "__main__":
    app.run()
