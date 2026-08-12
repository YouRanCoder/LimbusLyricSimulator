from PyQt5.QtWidgets import (
    QApplication, QMainWindow
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import (
    QPainter, QColor, QFont, QFontMetrics, QPen, QPainterPath, QTransform
)
import random,math
class FadingLine:
    def __init__(self, lines, font, x, y, angle, color, stroke_color,
                 stroke_width, mode, spacing, shake_intensity, fade_speed, rise_speed,
                 glow, glow_color, glow_size, glow_alpha, persp_transform=None):
        # lines 可以是字符串列表（多行）或单个字符串（兼容旧调用）
        if isinstance(lines, str):
            self.lines = [lines]
        else:
            self.lines = list(lines)
        self.font = font
        self.x = x
        self.y = y
        self.angle = angle
        self.color = QColor(color)
        self.stroke_color = QColor(stroke_color)
        self.stroke_width = stroke_width
        self.mode = mode
        self.spacing = spacing
        self.shake_intensity = shake_intensity
        self.fade_speed = fade_speed
        self.rise_speed = rise_speed
        self.glow = glow
        self.glow_color = QColor(glow_color)
        self.glow_size = glow_size
        self.glow_alpha = glow_alpha
        if persp_transform is None or isinstance(persp_transform, int):
            self.persp_transform = QTransform()
        else:
            self.persp_transform = persp_transform
        self.alpha = 255
        total_chars = sum(len(line) for line in self.lines)
        self.char_shakes = [{'x': 0, 'y': 0, 'target_x': 0, 'target_y': 0} for _ in range(total_chars)]

    def update(self):
        self.alpha = max(0, self.alpha - self.fade_speed)
        self.y -= self.rise_speed
        for s in self.char_shakes:
            s['target_x'] = random.randint(-self.shake_intensity, self.shake_intensity)
            s['target_y'] = random.randint(-self.shake_intensity, self.shake_intensity)
            s['x'] += (s['target_x'] - s['x']) * 0.3
            s['y'] += (s['target_y'] - s['y']) * 0.3
        return self.alpha > 0

    def draw(self, painter):
        if self.alpha <= 0:
            return
        painter.save()
        if self.persp_transform and not self.persp_transform.isIdentity():
            painter.setTransform(self.persp_transform, True)
        painter.translate(self.x, self.y)
        fm = QFontMetrics(self.font)
        th = fm.height()
        line_spacing = th * 0.3
        angle_rad = math.radians(self.angle)
        shadow_c = QColor(self.stroke_color)
        shadow_c.setAlpha(self.alpha)
        text_c = QColor(self.color)
        text_c.setAlpha(self.alpha)

        shake_idx = 0
        for line_idx, line_text in enumerate(self.lines):
            line_y_offset = line_idx * (th + line_spacing)
            cursor = 0
            for ch in line_text:
                cw = fm.horizontalAdvance(ch)
                ox = cursor * math.cos(angle_rad)
                oy = cursor * math.sin(angle_rad) + line_y_offset

                # 发光
                if self.glow:
                    glow_c = QColor(self.glow_color)
                    glow_c.setAlpha(int(self.alpha * self.glow_alpha / 255))
                    path_glow = QPainterPath()
                    path_glow.addText(ox, oy + th/3, self.font, ch)
                    pen = QPen()
                    pen.setColor(glow_c)
                    pen.setWidthF(self.glow_size)
                    painter.setPen(pen)
                    painter.setBrush(Qt.NoBrush)
                    painter.drawPath(path_glow)

                # 阴影
                if self.mode == 'chinese':
                    # 中文阴影
                    path = QPainterPath()
                    path.addText(ox + 3, oy + 3 + th/3, self.font, ch)
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(shadow_c)
                    painter.drawPath(path)
                    path = QPainterPath()
                    path.addText(ox, oy + th/3, self.font, ch)
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(text_c)
                    painter.drawPath(path)
                else:
                    # 英文描边淡出：描边保持，填充变透明
                    fill_c = QColor(text_c)
                    fill_c.setAlpha(max(0, self.alpha - 100))
                    path = QPainterPath()
                    path.addText(ox, oy + th/3, self.font, ch)
                    pen = QPen()
                    pen.setColor(shadow_c)
                    pen.setWidthF(self.stroke_width * 2)
                    painter.setPen(pen)
                    painter.setBrush(fill_c)
                    painter.drawPath(path)
                cursor += cw + self.spacing
            shake_idx += len(line_text)
        painter.restore()
