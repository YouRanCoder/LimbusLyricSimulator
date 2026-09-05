"""全屏区域选择覆盖层：用户框选歌词演出区域"""

from PyQt5.QtCore import Qt, QRect, QPoint, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QPen, QFont
from PyQt5.QtWidgets import QWidget, QApplication, QPushButton, QHBoxLayout


class RegionSelectOverlay(QWidget):
    """全屏半透明覆盖层，用户拖拽框选一个矩形区域

    选区确认后发射 region_selected(rect) 信号，rect 为像素坐标。
    按 Esc 或点击取消则关闭，不发射信号。
    """

    region_selected = pyqtSignal(QRect)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setCursor(Qt.CrossCursor)
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self._origin = QPoint()
        self._selection = QRect()
        self._dragging = False
        self._init_buttons()

    def _init_buttons(self):
        """底部确认/取消按钮"""
        bar = QWidget(self)
        bar.setFixedSize(280, 40)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self._btn_bar = bar

        self._btn_ok = QPushButton("确认选区", bar)
        self._btn_ok.setFixedSize(120, 36)
        self._btn_ok.setStyleSheet(
            "QPushButton{background:#4CAF50;color:#fff;border:none;border-radius:4px;font-size:14px}"
            "QPushButton:hover{background:#43A047}")
        self._btn_ok.clicked.connect(self._confirm)
        self._btn_ok.setEnabled(False)
        layout.addWidget(self._btn_ok)

        self._btn_cancel = QPushButton("取消", bar)
        self._btn_cancel.setFixedSize(100, 36)
        self._btn_cancel.setStyleSheet(
            "QPushButton{background:#666;color:#fff;border:none;border-radius:4px;font-size:14px}"
            "QPushButton:hover{background:#888}")
        self._btn_cancel.clicked.connect(self.close)
        layout.addWidget(self._btn_cancel)

    def showEvent(self, event):
        super().showEvent(event)
        self._selection = QRect()
        self._dragging = False
        self._btn_ok.setEnabled(False)
        self._center_buttons()
        self.activateWindow()

    def _center_buttons(self):
        x = (self.width() - self._btn_bar.width()) // 2
        y = self.height() - 70
        self._btn_bar.move(x, y)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._origin = event.pos()
            self._selection = QRect(self._origin, self._origin)
            self._dragging = True

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._selection = QRect(self._origin, event.pos()).normalized()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self._btn_ok.setEnabled(self._selection.width() > 5 and self._selection.height() > 5)
            self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()

    def _confirm(self):
        self.region_selected.emit(self._selection)
        self.close()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80))
        if not self._selection.isNull():
            painter.setPen(QPen(QColor(76, 175, 80), 2, Qt.DashLine))
            painter.setBrush(QColor(76, 175, 80, 40))
            painter.drawRect(self._selection)
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Microsoft YaHei", 10))
            label = f"歌词演出区域  {self._selection.width()} x {self._selection.height()}"
            painter.drawText(self._selection.x() + 4, self._selection.y() - 6, label)
