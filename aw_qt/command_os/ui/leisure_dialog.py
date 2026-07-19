"""Native editor for the server-owned Time Log leisure policy."""

from __future__ import annotations

from uuid import uuid4

from PyQt6.QtCore import QTime, QTimeZone, Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QStyle,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTimeEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..models import (
    ActivityCandidate,
    LeisurePolicy,
    TagOption,
)


INITIAL_THRESHOLD_MINUTES = 25
INITIAL_REWARD_MINUTES = 5


def system_iana_timezone() -> str:
    timezone_id = bytes(QTimeZone.systemTimeZoneId())
    if b"/" not in timezone_id:
        mapped = bytes(QTimeZone.windowsIdToDefaultIanaId(timezone_id))
        if mapped:
            timezone_id = mapped
    value = timezone_id.decode("utf-8")
    if not value:
        raise RuntimeError("The system timezone could not be resolved.")
    return value


class LeisureSettingsDialog(QDialog):
    def __init__(
        self,
        policy: LeisurePolicy | None,
        activities: tuple[ActivityCandidate, ...],
        tags: tuple[TagOption, ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("配置闲暇时刻")
        self.resize(620, 620)
        self._policy = policy
        self._enabled = QCheckBox("启用闲暇时刻", self)
        self._timezone = QComboBox(self)
        self._timezone.setEditable(True)
        self._timezone.addItems(
            sorted(
                bytes(value).decode("utf-8")
                for value in QTimeZone.availableTimeZoneIds()
            )
        )
        self._threshold = QSpinBox(self)
        self._threshold.setRange(1, 10_080)
        self._threshold.setSuffix(" 分钟")
        self._reward = QSpinBox(self)
        self._reward.setRange(1, 10_080)
        self._reward.setSuffix(" 分钟")
        self._windows = QTableWidget(0, 2, self)
        self._windows.setHorizontalHeaderLabels(["开始", "结束"])
        self._windows.horizontalHeader().setStretchLastSection(True)
        self._windows.verticalHeader().setVisible(False)
        self._activities = QListWidget(self)
        self._tags = QListWidget(self)
        self._stable_activities = tuple(
            item
            for item in activities
            if item.activity_id.startswith("base:") or bool(item.template_id)
        )
        self._build_layout()
        self._populate(policy, tags)

    def policy_payload(self) -> dict:
        windows = []
        for row in range(self._windows.rowCount()):
            start = self._time_widget(row, 0).time()
            end = self._time_widget(row, 1).time()
            if start == end:
                raise ValueError("固定闲暇区间的开始和结束时间不能相同。")
            windows.append(
                {
                    "window_id": str(
                        self._windows.item(row, 0).data(Qt.ItemDataRole.UserRole)
                    ),
                    "start_minute": start.hour() * 60 + start.minute(),
                    "end_minute": end.hour() * 60 + end.minute(),
                }
            )
        selectors = []
        for widget, kind in (
            (self._activities, "activity"),
            (self._tags, "tag"),
        ):
            for index in range(widget.count()):
                item = widget.item(index)
                if item.checkState() != Qt.CheckState.Checked:
                    continue
                value = str(item.data(Qt.ItemDataRole.UserRole) or "")
                selectors.append(
                    {
                        "selector_id": f"leisure_selector_{uuid4().hex}",
                        "kind": kind,
                        "value": value,
                    }
                )
        return {
            "enabled": self._enabled.isChecked(),
            "timezone": self._timezone.currentText().strip(),
            "earn_threshold_minutes": self._threshold.value(),
            "reward_minutes": self._reward.value(),
            "fixed_windows": windows,
            "selectors": selectors,
        }

    def accept(self) -> None:
        try:
            payload = self.policy_payload()
            if not payload["timezone"]:
                raise ValueError("请选择时区。")
        except ValueError as exc:
            QMessageBox.warning(self, "配置无效", str(exc))
            return
        super().accept()

    def _build_layout(self) -> None:
        main = QVBoxLayout(self)
        main.addWidget(self._enabled)
        tabs = QTabWidget(self)
        schedule = QWidget(tabs)
        schedule_layout = QVBoxLayout(schedule)
        schedule_form = QFormLayout()
        schedule_form.addRow("时区", self._timezone)
        schedule_layout.addLayout(schedule_form)
        schedule_layout.addWidget(self._windows, 1)
        window_actions = QHBoxLayout()
        add_window = QToolButton(schedule)
        add_window.setIcon(
            self.style().standardIcon(
                QStyle.StandardPixmap.SP_FileDialogNewFolder
            )
        )
        add_window.setToolTip("添加固定区间")
        add_window.clicked.connect(lambda: self._add_window(12 * 60, 14 * 60))
        remove_window = QToolButton(schedule)
        remove_window.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon)
        )
        remove_window.setToolTip("删除所选固定区间")
        remove_window.clicked.connect(self._remove_window)
        window_actions.addWidget(add_window)
        window_actions.addWidget(remove_window)
        window_actions.addStretch(1)
        schedule_layout.addLayout(window_actions)
        earning = QWidget(tabs)
        earning_layout = QVBoxLayout(earning)
        earning_form = QFormLayout()
        earning_form.addRow("每累计", self._threshold)
        earning_form.addRow("获得", self._reward)
        earning_layout.addLayout(earning_form)
        lists = QHBoxLayout()
        activity_column = QVBoxLayout()
        activity_column.addWidget(QLabel("事件", earning))
        activity_column.addWidget(self._activities, 1)
        tag_column = QVBoxLayout()
        tag_column.addWidget(QLabel("标签", earning))
        tag_column.addWidget(self._tags, 1)
        lists.addLayout(activity_column, 1)
        lists.addLayout(tag_column, 1)
        earning_layout.addLayout(lists, 1)
        tabs.addTab(schedule, "固定区间")
        tabs.addTab(earning, "积累规则")
        main.addWidget(tabs, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Save,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        main.addWidget(buttons)

    def _populate(
        self,
        policy: LeisurePolicy | None,
        tags: tuple[TagOption, ...],
    ) -> None:
        self._enabled.setChecked(policy.enabled if policy is not None else True)
        timezone = policy.timezone if policy is not None else system_iana_timezone()
        self._timezone.setCurrentText(timezone)
        self._threshold.setValue(
            policy.earn_threshold_minutes
            if policy is not None
            else INITIAL_THRESHOLD_MINUTES
        )
        self._reward.setValue(
            policy.reward_minutes
            if policy is not None
            else INITIAL_REWARD_MINUTES
        )
        selected_activities = {
            item.value
            for item in (policy.selectors if policy is not None else ())
            if item.kind == "activity"
        }
        selected_tags = {
            item.value
            for item in (policy.selectors if policy is not None else ())
            if item.kind == "tag"
        }
        for activity in self._stable_activities:
            item = QListWidgetItem(activity.label)
            item.setData(Qt.ItemDataRole.UserRole, activity.activity_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked
                if activity.activity_id in selected_activities
                else Qt.CheckState.Unchecked
            )
            self._activities.addItem(item)
        for tag in tags:
            item = QListWidgetItem(tag.name)
            item.setData(Qt.ItemDataRole.UserRole, tag.name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked
                if tag.name in selected_tags
                else Qt.CheckState.Unchecked
            )
            self._tags.addItem(item)
        for window in policy.fixed_windows if policy is not None else ():
            self._add_window(
                window.start_minute,
                window.end_minute,
                window.window_id,
            )

    def _add_window(
        self,
        start_minute: int,
        end_minute: int,
        window_id: str | None = None,
    ) -> None:
        row = self._windows.rowCount()
        self._windows.insertRow(row)
        start = QTimeEdit(self._windows)
        end = QTimeEdit(self._windows)
        start.setDisplayFormat("HH:mm")
        end.setDisplayFormat("HH:mm")
        start.setTime(QTime(start_minute // 60, start_minute % 60))
        end.setTime(QTime(end_minute // 60, end_minute % 60))
        marker = QTableWidgetItem()
        marker.setData(
            Qt.ItemDataRole.UserRole,
            window_id or f"leisure_window_{uuid4().hex}",
        )
        self._windows.setItem(row, 0, marker)
        self._windows.setCellWidget(row, 0, start)
        self._windows.setCellWidget(row, 1, end)

    def _remove_window(self) -> None:
        row = self._windows.currentRow()
        if row >= 0:
            self._windows.removeRow(row)

    def _time_widget(self, row: int, column: int) -> QTimeEdit:
        widget = self._windows.cellWidget(row, column)
        if not isinstance(widget, QTimeEdit):
            raise RuntimeError("Fixed leisure window editor is incomplete.")
        return widget


def edit_leisure_settings(
    policy: LeisurePolicy | None,
    activities: tuple[ActivityCandidate, ...],
    tags: tuple[TagOption, ...],
    parent: QWidget,
) -> dict | None:
    dialog = LeisureSettingsDialog(policy, activities, tags, parent)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialog.policy_payload()
