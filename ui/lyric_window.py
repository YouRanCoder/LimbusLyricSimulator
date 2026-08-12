from PyQt5.QtWidgets import QMainWindow, QApplication
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter, QColor, QFont, QFontMetrics, QPen, QPainterPath, QTransform
import random, time, math
from .fading_line import FadingLine
from core.parser import parse_lrc
class LyricWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("歌词悬浮窗")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self.font = QFont("Microsoft YaHei", 28, QFont.Bold)
        self.text_color = QColor("#fffeef"); self.stroke_color = QColor("#d8a523")
        self.stroke_width = 0.5; self.angle_min = -10; self.angle_max = 10
        self.margin_time = 4000; self.max_interval = 16000; self.max_duration = 5000
        self.mode = 'chinese'; self.spacing = 5.0
        self.shake_intensity = 2; self.shake_speed = 143
        self.fade_speed = 12; self.rise_speed = 1
        self.glow = True; self.glow_color = QColor("#d8a523")
        self.glow_size = 4; self.glow_alpha = 82
        self.loop = True; self.song_duration = 0; self.start_delay = 0
        self.full_text = ""; self.char_index = 0
        self.x = 500; self.y = 300; self.angle = 0
        self.char_timer = QTimer(self); self.char_timer.timeout.connect(self.show_next_char)
        self.shake_timer = QTimer(self); self.shake_timer.timeout.connect(self.update_shake)
        self.lyric_timeline = []; self.current_line = 0
        self.line_timer = QTimer(self); self.line_timer.timeout.connect(self.check_lyric_time)
        self.start_time = 0; self.char_shakes = []
        self.fading_lines = []
        self.fade_timer = QTimer(self); self.fade_timer.timeout.connect(self.update_fading)
        self.fade_timer.start(30)
        self.perspective_enabled = True
        self.persp_x_strength = 0.00005
        self.persp_y_strength = 0.0003
        self.persp_compensation = 0.03
        self.persp_transform = QTransform()
        self.screen_w = screen.width()
        self.screen_h = screen.height()
        # 歌词起始位置范围（百分比，0~100），由控制面板实时调整
        self.pos_x_min = 5
        self.pos_x_max = 85
        self.pos_y_min = 5
        self.pos_y_max = 75

    def init_char_shakes(self):
        self.char_shakes = [{'x': 0, 'y': 0, 'target_x': 0, 'target_y': 0} for _ in self.full_text]

    def start_lyric(self, text, font, color, stroke_color, stroke_width,
                    angle_min, angle_max, margin_time, max_interval, max_duration,
                    mode, spacing, shake_intensity, shake_speed,
                    fade_speed, rise_speed, glow, glow_color, glow_size, glow_alpha,
                    start_delay=0):
        self.start_delay = start_delay
        if self.start_delay > 0:
            self.full_text = ""; self.char_index = 0
            self.lyric_timeline = []; self.update()
            QTimer.singleShot(int(self.start_delay * 1000),
                lambda: self._actually_start(text, font, color, stroke_color, stroke_width,
                    angle_min, angle_max, margin_time, max_interval, max_duration,
                    mode, spacing, shake_intensity, shake_speed,
                    fade_speed, rise_speed, glow, glow_color, glow_size, glow_alpha))
            return
        self._actually_start(text, font, color, stroke_color, stroke_width,
            angle_min, angle_max, margin_time, max_interval, max_duration,
            mode, spacing, shake_intensity, shake_speed,
            fade_speed, rise_speed, glow, glow_color, glow_size, glow_alpha)

    def _actually_start(self, text, font, color, stroke_color, stroke_width,
                        angle_min, angle_max, margin_time, max_interval, max_duration,
                        mode, spacing, shake_intensity, shake_speed,
                        fade_speed, rise_speed, glow, glow_color, glow_size, glow_alpha):
        self.font = font; self.text_color = color; self.stroke_color = stroke_color
        self.stroke_width = stroke_width; self.angle_min = angle_min; self.angle_max = angle_max
        self.margin_time = margin_time; self.max_interval = max_interval; self.max_duration = max_duration
        self.mode = mode; self.spacing = spacing
        self.shake_intensity = shake_intensity; self.shake_speed = shake_speed
        self.fade_speed = fade_speed; self.rise_speed = rise_speed
        self.glow = glow; self.glow_color = glow_color
        self.glow_size = glow_size; self.glow_alpha = glow_alpha
        self.lyric_timeline = parse_lrc(text); self.fading_lines = []
        if not self.lyric_timeline:
            self.full_text = text; self.char_index = 0
            self.init_char_shakes(); self.place_randomly()
            self.char_timer.start(50); self.shake_timer.start(self.shake_speed)
            return
        self.current_line = 0; self.char_index = 0; self.full_text = ""
        self.update(); self.start_time = 0; self.line_timer.start(50)
    def compute_perspective(self):
        if not self.perspective_enabled:
            self.persp_transform = QTransform()
            return
        rel_x = (self.x - self.screen_w / 2) / (self.screen_w / 2)
        rel_y = (self.y - self.screen_h / 2) / (self.screen_h / 2)
        persp_x = self.persp_x_strength * rel_x
        persp_y = self.persp_y_strength * rel_y
        scale_x = 1.0 + self.persp_compensation * max(0, rel_x)
        self.persp_transform = QTransform()
        self.persp_transform.setMatrix(scale_x, 0, persp_x,
                                       0, 1, persp_y,
                                       0, 0, 1)
    def place_randomly(self):
        sw = self.width()
        sh = self.height()
        
        # 计算当前歌词的实际渲染宽度
        fm = QFontMetrics(self.font)
        text_width = 0
        for ch in self.full_text:
            text_width += fm.horizontalAdvance(ch) + self.spacing
        
        # 增加安全边距，防止发光/阴影被裁切
        safe_margin_x = int(200 + text_width)
        safe_margin_y = 150
        
        # 用户设置的起始位置范围（百分比 → 像素），并与安全边距取交集
        x_min = max(int(sw * self.pos_x_min / 100), safe_margin_x)
        x_max = min(int(sw * self.pos_x_max / 100), sw - safe_margin_x)
        y_min = max(int(sh * self.pos_y_min / 100), safe_margin_y)
        y_max = min(int(sh * self.pos_y_max / 100), sh - safe_margin_y)
        
        # 范围被安全边距压缩到无效时，回退到安全边距范围，避免随机失败
        if x_max <= x_min:
            x_min = safe_margin_x
            x_max = max(safe_margin_x + 1, sw - safe_margin_x)
        if y_max <= y_min:
            y_min = safe_margin_y
            y_max = max(safe_margin_y + 1, sh - safe_margin_y)
        
        self.x = random.randint(x_min, x_max)
        self.y = random.randint(y_min, y_max)
        self.angle = random.randint(self.angle_min, self.angle_max)
        self.compute_perspective()

    def check_lyric_time(self):
        if self.start_time == 0: self.start_time = time.time() * 1000
        elapsed = time.time() * 1000 - self.start_time
        while (self.current_line < len(self.lyric_timeline) and
               self.lyric_timeline[self.current_line][0] <= elapsed):
            if self.full_text and self.char_index > 0:
                fading = FadingLine(self.full_text, self.font, self.x, self.y, self.angle,
                    self.text_color, self.stroke_color, self.stroke_width,
                    self.mode, self.spacing, self.shake_intensity,
                    self.fade_speed, self.rise_speed,
                    self.glow, self.glow_color, self.glow_size, self.glow_alpha,
    self.persp_transform)
                self.fading_lines.append(fading)
            line_text = self.lyric_timeline[self.current_line][1]
            self.full_text = line_text; self.char_index = 0
            self.init_char_shakes(); self.place_randomly()
            if self.current_line + 1 < len(self.lyric_timeline):
                next_time = self.lyric_timeline[self.current_line + 1][0]
                current_time = self.lyric_timeline[self.current_line][0]
                interval = next_time - current_time
                if interval > self.max_interval:
                    char_count = len(line_text)
                    calc_speed = max(30, int(self.max_duration / char_count)) if char_count > 0 else 50
                else:
                    interval -= self.margin_time
                    char_count = len(line_text)
                    calc_speed = max(30, int(interval / char_count)) if char_count > 0 else 50
            else:
                calc_speed = 50
            self.char_timer.start(calc_speed)
            self.shake_timer.start(self.shake_speed)
            self.current_line += 1
        if self.current_line >= len(self.lyric_timeline):
            if self.loop and self.song_duration > 0:
                elapsed_total = time.time() * 1000 - self.start_time
                if elapsed_total >= self.song_duration:
                    self.current_line = 0; self.char_index = 0; self.full_text = ""
                    self.start_time = time.time() * 1000
                    self.fading_lines = []; self.update()
            else:
                self.line_timer.stop()

    def show_next_char(self):
        if self.char_index < len(self.full_text):
            self.char_index += 1; self.update()
        else:
            self.char_timer.stop()

    def update_shake(self):
        if not self.full_text or self.char_index == 0: return
        for s in self.char_shakes:
            s['target_x'] = random.randint(-self.shake_intensity, self.shake_intensity)
            s['target_y'] = random.randint(-self.shake_intensity, self.shake_intensity)
            s['x'] += (s['target_x'] - s['x']) * 0.3
            s['y'] += (s['target_y'] - s['y']) * 0.3
        self.update()

    def update_fading(self):
        if not self.fading_lines: return
        self.fading_lines = [f for f in self.fading_lines if f.update()]
        self.update()

    def stop_lyric(self):
        self.char_timer.stop(); self.shake_timer.stop(); self.line_timer.stop()
        self.full_text = ""; self.char_index = 0
        self.lyric_timeline = []; self.current_line = 0
        self.fading_lines = []; self.char_shakes = []
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.Antialiasing)
        for f in self.fading_lines: f.draw(painter)
        if self.char_index == 0 or not self.full_text: return
        draw_text = self.full_text[:self.char_index]
        font = QFont(self.font); fm = QFontMetrics(font)
        th = fm.height(); angle_rad = math.radians(self.angle)
        painter.save()
        if self.perspective_enabled:
            painter.setTransform(self.persp_transform, True)
        painter.translate(self.x, self.y)
        if self.mode == 'chinese':
            shadow_c = QColor(self.stroke_color); text_c = QColor(self.text_color)
        else:
            stroke_c = QColor(self.stroke_color); fill_c = QColor(self.text_color)
        cursor = 0
        for i, ch in enumerate(draw_text):
            sx = self.char_shakes[i]['x'] if i < len(self.char_shakes) else 0
            sy = self.char_shakes[i]['y'] if i < len(self.char_shakes) else 0
            cw = fm.horizontalAdvance(ch)
            ox = cursor * math.cos(angle_rad); oy = cursor * math.sin(angle_rad)
            if self.glow:
                glow_c = QColor(self.glow_color); gs = self.glow_size
                gc = QColor(glow_c); gc.setAlpha(self.glow_alpha)
                path_glow = QPainterPath()
                path_glow.addText(ox + sx, oy + sy + th/3, font, ch)
                pen_g = QPen(QColor(gc), gs)
                painter.setPen(pen_g); painter.setBrush(Qt.NoBrush)
                painter.drawPath(path_glow)
            if self.mode == 'chinese':
                path_shadow = QPainterPath()
                path_shadow.addText(ox + sx + 3, oy + sy + 3 + th/3, font, ch)
                painter.setPen(Qt.NoPen); painter.setBrush(shadow_c)
                painter.drawPath(path_shadow)
                path_text = QPainterPath()
                path_text.addText(ox + sx, oy + sy + th/3, font, ch)
                painter.setPen(Qt.NoPen); painter.setBrush(text_c)
                painter.drawPath(path_text)
            else:
                path = QPainterPath()
                path.addText(ox + sx, oy + sy + th/3, font, ch)
                pen = QPen(stroke_c, self.stroke_width * 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
                painter.setPen(pen); painter.setBrush(fill_c)
                painter.drawPath(path)
            cursor += cw + self.spacing
        painter.restore()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape: QApplication.quit()