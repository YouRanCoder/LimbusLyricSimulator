"""Fluent 风格对话框：文本输入、播放器配置与确认对话框"""

from PyQt5.QtWidgets import QDialog, QHBoxLayout, QWidget

from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    ComboBox,
    LineEdit,
    MessageBox,
    MessageBoxBase,
    SubtitleLabel,
    SwitchButton,
)


class TextInputDialog(MessageBoxBase):
    """单行文本输入对话框"""

    def __init__(self, title: str, placeholder: str = "", default: str = "",
                 parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(title, self)
        self.lineEdit = LineEdit(self)
        self.lineEdit.setPlaceholderText(placeholder)
        self.lineEdit.setText(default)
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.lineEdit)

        self.yesButton.setText("确定")
        self.cancelButton.setText("取消")
        self.widget.setMinimumWidth(360)

    def value(self) -> str:
        return self.lineEdit.text().strip()


def ask_text(parent, title: str, placeholder: str = "",
             default: str = "") -> str:
    """弹出文本输入框，返回输入内容（取消返回空字符串）"""
    dialog = TextInputDialog(title, placeholder, default, parent)
    if dialog.exec() == QDialog.Accepted:
        return dialog.value()
    return ""


class PlayerConfigDialog(MessageBoxBase):
    """添加/修改播放器对话框：名称 + SMTC 会话 + 是否支持同步进度"""

    def __init__(self, title: str, sessions: list, default_name: str = "",
                 default_process: str = "", support_progress: bool = True,
                 parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(title, self)

        # 播放器名称
        self.nameEdit = LineEdit(self)
        self.nameEdit.setPlaceholderText("输入播放器显示名称：")
        self.nameEdit.setText(default_name)

        # SMTC 会话选择（重新筛选会话）
        self.sessionCombo = ComboBox(self)
        for s in sessions:
            self.sessionCombo.addItem(s, userData=s)
        if default_process:
            idx = self.sessionCombo.findData(default_process)
            if idx >= 0:
                self.sessionCombo.setCurrentIndex(idx)
            else:
                # 当前配置的会话不在活跃列表中，仍保留为可选项
                self.sessionCombo.addItem(
                    f"{default_process}（保留当前会话）", userData=default_process)
                self.sessionCombo.setCurrentIndex(self.sessionCombo.count() - 1)

        # 是否支持同步进度（默认勾选）
        self.progressCheck = SwitchButton(self)
        self.progressCheck.setChecked(support_progress)
        _progress_row = QWidget(self)
        _row = QHBoxLayout(_progress_row)
        _row.setContentsMargins(0, 0, 0, 0)
        _row.addWidget(BodyLabel("是否支持同步进度"))
        _row.addStretch(1)
        _row.addWidget(self.progressCheck)

        # 小字提示
        _hint = CaptionLabel("如果运行异常则取消勾选")
        _hint.setStyleSheet("color: rgba(128, 128, 128, 0.9);")

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.nameEdit)
        self.viewLayout.addWidget(self.sessionCombo)
        self.viewLayout.addWidget(_progress_row)
        self.viewLayout.addWidget(_hint)

        self.yesButton.setText("确定")
        self.cancelButton.setText("取消")
        self.widget.setMinimumWidth(420)

    def values(self) -> dict:
        """返回配置：名称、SMTC 会话、是否支持同步进度"""
        return {
            "name": self.nameEdit.text().strip(),
            "process": self.sessionCombo.currentData(),
            "support_progress": self.progressCheck.isChecked(),
        }


class SelectDialog(MessageBoxBase):
    """下拉选择对话框"""

    def __init__(self, title: str, items: list, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(title, self)
        self.combo = ComboBox(self)
        self.combo.addItems(items)
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.combo)

        self.yesButton.setText("确定")
        self.cancelButton.setText("取消")
        self.widget.setMinimumWidth(360)
        if items:
            self.combo.setCurrentIndex(0)
        else:
            self.yesButton.setEnabled(False)

    def value(self) -> str:
        return self.combo.currentText()


def ask_select(parent, title: str, items: list) -> str:
    """弹出下拉选择框，返回选中的项（取消返回空字符串）"""
    dialog = SelectDialog(title, items, parent)
    if dialog.exec() == QDialog.Accepted:
        return dialog.value()
    return ""


def confirm(parent, title: str, content: str) -> bool:
    """弹出确认对话框，返回是否确认"""
    box = MessageBox(title, content, parent)
    box.yesButton.setText("确定")
    box.cancelButton.setText("取消")
    return box.exec() == QDialog.Accepted


def warn(parent, title: str, content: str) -> None:
    """弹出警告对话框（只有一个确定按钮）"""
    box = MessageBox(title, content, parent)
    box.yesButton.setText("确定")
    box.cancelButton.hide()
    box.exec()
