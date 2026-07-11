"""Native activity and tag selection dialogs."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..models import ActivityCandidate, TagOption


class ActivityPickerDialog(QDialog):
    def __init__(
        self,
        activities: tuple[ActivityCandidate, ...],
        title: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(460, 520)
        self._activities = activities
        self._search = QLineEdit(self)
        self._search.setPlaceholderText("搜索事件或标签")
        self._list = QListWidget(self)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Ok,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._list.itemDoubleClicked.connect(lambda _item: self.accept())
        self._search.textChanged.connect(self._populate)
        layout = QVBoxLayout(self)
        layout.addWidget(self._search)
        layout.addWidget(self._list, 1)
        layout.addWidget(buttons)
        self._populate("")

    def selected_activity_id(self) -> str:
        item = self._list.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole) or "") if item else ""

    def _populate(self, query: str) -> None:
        selected_id = self.selected_activity_id()
        normalized = query.strip().casefold()
        self._list.clear()
        for activity in self._activities:
            search_text = " ".join(
                (activity.title, activity.label, *activity.tags)
            ).casefold()
            if normalized and normalized not in search_text:
                continue
            suffix = " ".join(f"#{tag}" for tag in activity.tags)
            item = QListWidgetItem(
                "  ·  ".join(part for part in (activity.label, suffix) if part)
            )
            item.setData(Qt.ItemDataRole.UserRole, activity.activity_id)
            self._list.addItem(item)
            if activity.activity_id == selected_id:
                self._list.setCurrentItem(item)
        if self._list.currentRow() < 0 and self._list.count():
            self._list.setCurrentRow(0)


class TagPickerDialog(QDialog):
    def __init__(
        self,
        tags: tuple[TagOption, ...],
        selected: tuple[str, ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("编辑当前标签")
        self.resize(360, 460)
        selected_names = set(selected)
        self._list = QListWidget(self)
        for tag in tags:
            item = QListWidgetItem(tag.name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked
                if tag.name in selected_names
                else Qt.CheckState.Unchecked
            )
            self._list.addItem(item)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Ok,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("标签", self))
        layout.addWidget(self._list, 1)
        layout.addWidget(buttons)

    def selected_tags(self) -> list[str]:
        return [
            self._list.item(index).text()
            for index in range(self._list.count())
            if self._list.item(index).checkState() == Qt.CheckState.Checked
        ]


def choose_activity(
    activities: tuple[ActivityCandidate, ...],
    title: str,
    parent: QWidget,
) -> str:
    dialog = ActivityPickerDialog(activities, title, parent)
    return dialog.selected_activity_id() if dialog.exec() == QDialog.DialogCode.Accepted else ""


def choose_tags(
    tags: tuple[TagOption, ...],
    selected: tuple[str, ...],
    parent: QWidget,
) -> list[str] | None:
    dialog = TagPickerDialog(tags, selected, parent)
    return dialog.selected_tags() if dialog.exec() == QDialog.DialogCode.Accepted else None


def prompt_new_tag(parent: QWidget) -> str:
    value, accepted = QInputDialog.getText(parent, "新建标签", "标签名称")
    return value.strip() if accepted else ""


def choose_custom_tag(tags: tuple[TagOption, ...], parent: QWidget) -> str:
    custom = [tag.name for tag in tags if not tag.is_default]
    if not custom:
        return ""
    value, accepted = QInputDialog.getItem(
        parent,
        "删除标签",
        "自定义标签",
        custom,
        editable=False,
    )
    return str(value) if accepted else ""
