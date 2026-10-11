"""Fluent 风格对话框：文本输入、播放器配置、更新日志与确认对话框"""

import logging

from PyQt5.QtGui import QDesktopServices
from PyQt5.QtCore import QUrl
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
    TextBrowser,
)

logger = logging.getLogger(__name__)


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


class UpdateDialog(MessageBoxBase):
    """发现新版本对话框：展示版本号、更新日志，引导前往 Release 页自行下载"""

    def __init__(self, current_version: str, latest_version: str,
                 changelog: str = "", release_url: str = "", parent=None):
        super().__init__(parent)
        self.release_url = release_url
        self.titleLabel = SubtitleLabel(f"发现新版本 v{latest_version}", self)
        self.versionLabel = CaptionLabel(f"当前版本 v{current_version} → 最新版本 v{latest_version}")
        self.versionLabel.setStyleSheet("color: rgba(128, 128, 128, 0.9);")

        # 更新日志（只读展示，无日志时给出兜底文案）
        self.logBrowser = TextBrowser(self)
        self.logBrowser.setReadOnly(True)
        self.logBrowser.setPlainText(
            changelog if changelog else "本次更新暂未填写更新日志，详见 Release 页面。")
        self.logBrowser.setMinimumSize(460, 220)

        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.versionLabel)
        self.viewLayout.addWidget(self.logBrowser)

        self.yesButton.setText("前往下载")
        self.cancelButton.setText("以后再说")
        self.widget.setMinimumWidth(500)

    def accept(self) -> None:
        """点击「前往下载」：打开 Release 页面让用户自行下载"""
        if self.release_url:
            logger.info("打开下载页面：%s", self.release_url)
            QDesktopServices.openUrl(QUrl(self.release_url))
        super().accept()


def confirm(parent, title: str, content: str) -> bool:
    """弹出确认对话框，返回是否确认"""
    box = MessageBox(title, content, parent)
    box.yesButton.setText("确定")
    box.cancelButton.setText("取消")
    return box.exec() == QDialog.Accepted


def info(parent, title: str, content: str) -> None:
    """弹出信息对话框（只有一个确定按钮）"""
    box = MessageBox(title, content, parent)
    box.yesButton.setText("确定")
    box.cancelButton.hide()
    box.exec()


def warn(parent, title: str, content: str) -> None:
    """弹出警告对话框（只有一个确定按钮）"""
    box = MessageBox(title, content, parent)
    box.yesButton.setText("确定")
    box.cancelButton.hide()
    box.exec()
