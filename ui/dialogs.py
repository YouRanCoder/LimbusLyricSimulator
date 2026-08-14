"""Fluent 风格对话框：文本输入与确认对话框"""

from PyQt5.QtWidgets import QDialog

from qfluentwidgets import (
    LineEdit,
    MessageBox,
    MessageBoxBase,
    SubtitleLabel,
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
