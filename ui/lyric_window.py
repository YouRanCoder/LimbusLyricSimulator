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
        self._paused_at = None; self._pause_requested = False
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

    def _text_width(self, s):
        """精确测量一行文本的渲染宽度

        与 paintEvent 的渲染方式完全一致：逐字符累加 + 字符间距。
        不能用整串 horizontalAdvance（含 kerning，比实际渲染窄），
        否则会低估宽度导致折叠判断失误。
        """
        if not s:
            return 0
        fm = QFontMetrics(self.font)
        total = sum(fm.horizontalAdvance(ch) for ch in s)
        return total + max(0, len(s) - 1) * self.spacing

    def _compute_place_constraints(self):
        """计算文本放置相关的所有约束，供 wrap_text 和 place_randomly 共用

        保证折叠后的行宽一定能被 place_randomly 放下，避免两处计算不一致。
        """
        sw = self.width()
        sh = self.height()
        fm = QFontMetrics(self.font)
        text_height = fm.height()

        # 发光/阴影额外扩展
        glow_margin = (self.glow_size + 4) if self.glow else 4
        shadow_margin = 6  # 中文模式阴影偏移

        # 分辨率自适应基础边距（屏幕对角线的 3%，最小 30px）
        diagonal = math.sqrt(sw * sw + sh * sh)
        base_margin = max(30, int(diagonal * 0.03))

        # 透视变换额外偏移
        persp_extra_x = 0
        persp_extra_y = 0
        if self.perspective_enabled:
            persp_extra_x = int(sw * max(abs(self.persp_x_strength), 0.001) * 2)
            persp_extra_y = int(sh * max(abs(self.persp_y_strength), 0.001) * 2)

        # 用户设置的起始位置范围（百分比 → 像素）
        user_x_min = int(sw * self.pos_x_min / 100)
        user_x_max = int(sw * self.pos_x_max / 100)
        user_y_min = int(sh * self.pos_y_min / 100)
        user_y_max = int(sh * self.pos_y_max / 100)

        # 旋转角度影响（取最大可能角度）
        max_angle_rad = math.radians(max(abs(self.angle_min), abs(self.angle_max), 1))
        cos_a = abs(math.cos(max_angle_rad)) or 0.01
        sin_a = abs(math.sin(max_angle_rad))

        return {
            'sw': sw, 'sh': sh,
            'text_height': text_height,
            'line_spacing': text_height * 0.3,
            'glow_margin': glow_margin,
            'shadow_margin': shadow_margin,
            'base_margin': base_margin,
            'persp_extra_x': persp_extra_x,
            'persp_extra_y': persp_extra_y,
            'user_x_min': user_x_min, 'user_x_max': user_x_max,
            'user_y_min': user_y_min, 'user_y_max': user_y_max,
            'cos_a': cos_a, 'sin_a': sin_a,
            'max_angle_rad': max_angle_rad,
        }

    def wrap_text(self, text, max_width):
        """将长文本按可用宽度自动折叠为多行

        使用逐字符测量（与渲染一致）确保精确；边界保守，避免溢出 1-2 个字符。
        """
        if not text:
            return []
        if max_width <= 0:
            return [text]

        # 整行放得下就直接返回
        if self._text_width(text) <= max_width:
            return [text]

        has_spaces = ' ' in text.strip()

        if has_spaces:
            # 英文/空格模式：按单词分割，整行测量
            words = text.split(' ')
            lines = []
            current = ""
            for word in words:
                candidate = word if not current else current + ' ' + word
                if self._text_width(candidate) <= max_width:
                    current = candidate
                else:
                    if current:
                        lines.append(current)
                    # 单个单词超长时按字符拆分
                    if self._text_width(word) > max_width:
                        sub = ""
                        for ch in word:
                            if self._text_width(sub + ch) > max_width and sub:
                                lines.append(sub)
                                sub = ch
                            else:
                                sub += ch
                        current = sub
                    else:
                        current = word
            if current:
                lines.append(current)
            return lines
        else:
            # 中文/日文模式：按字符分割，整行测量
            lines = []
            current = ""
            for ch in text:
                if self._text_width(current + ch) > max_width and current:
                    lines.append(current)
                    current = ch
                else:
                    current += ch
            if current:
                lines.append(current)
            return lines

    def init_char_shakes(self):
        total_chars = sum(len(line) for line in self.wrapped_lines)
        self.char_shakes = [{'x': 0, 'y': 0, 'target_x': 0, 'target_y': 0} for _ in range(total_chars)]

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
            self.wrapped_lines = self.wrap_text(text, self._get_max_text_width())
            self.full_text = text; self.char_index = 0
            self.init_char_shakes(); self.place_randomly()
            self.char_timer.start(50); self.shake_timer.start(self.shake_speed)
            return
        self.current_line = 0; self.char_index = 0; self.full_text = ""
        self.wrapped_lines = []
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
    def _get_max_text_width(self):
        """计算单行文本的最大可用宽度（基于屏幕可用宽度，含保守余量）

        折叠后的每行宽度不超过该值，配合 place_randomly 的回退逻辑保证
        无论歌词落在哪里都不会溢出屏幕，且不会极限贴近屏幕边缘。
        注意：这里不限制用户范围——用户范围只控制歌词出现的位置，
        行宽过窄反而会导致歌词被拆得过碎。
        """
        c = self._compute_place_constraints()
        sw = c['sw']

        # 横向可用像素：以屏幕宽度为基准（全屏 - 左右边距 - 透视偏移）
        margins = c['base_margin'] + c['glow_margin'] + c['shadow_margin']
        avail = sw - 2 * (margins + c['persp_extra_x'])

        # 旋转放大还原：旋转后包围盒宽 = text_width*cos + text_height*sin
        # 预留多行高度（按最多 3 行估算）带来的 sin 方向影响
        avail = (avail - 3 * c['text_height'] * c['sin_a']) / c['cos_a']

        # 透视缩放补偿：右侧文字会被放大（scale_x = 1.0 + persp_compensation）
        # 测量宽度是未缩放的，实际渲染时会被放大，所以要除以最大缩放比例
        if self.perspective_enabled:
            max_scale_x = 1.0 + self.persp_compensation  # 最坏情况：rel_x = 1.0
            avail = avail / max_scale_x

        # 保守余量（"别玩那么极限"）：留 5% + 半个字符宽度，
        # 避免 kerning 测量误差、发光描边导致溢出 1-2 个字母
        safety = int(avail * 0.05) + c['text_height'] // 2
        avail -= safety

        # 上限保护，防止异常大值（也要考虑透视缩放）
        cap = int(sw * 0.78)
        if self.perspective_enabled:
            cap = int(cap / (1.0 + self.persp_compensation))
        return max(min(int(avail), cap), 120)

    def place_randomly(self):
        c = self._compute_place_constraints()
        sw = c['sw']
        sh = c['sh']

        # 计算最宽行的宽度（逐字符测量，与 wrap_text 一致）
        max_line_width = max((self._text_width(line) for line in self.wrapped_lines), default=0)

        text_width = max_line_width
        total_height = len(self.wrapped_lines) * c['text_height'] + \
                       max(0, len(self.wrapped_lines) - 1) * c['line_spacing']

        # 计算旋转后的包围盒宽度
        rotated_w = text_width * c['cos_a'] + total_height * c['sin_a']

        # 安全边距（基础边距 + 发光 + 阴影）
        base = c['base_margin'] + c['glow_margin'] + c['shadow_margin']
        left_margin = int(base)
        right_margin = int(rotated_w + base)
        top_margin = int(base)
        bottom_margin = int(total_height + base)

        # 与用户设置的起始位置范围取交集，确保文本不溢出
        x_min = max(c['user_x_min'], left_margin + c['persp_extra_x'])
        x_max = min(c['user_x_max'], sw - right_margin - c['persp_extra_x'])
        y_min = max(c['user_y_min'], top_margin + c['persp_extra_y'])
        y_max = min(c['user_y_max'], sh - bottom_margin - c['persp_extra_y'])

        # 范围无效时，回退到安全范围内
        if x_max <= x_min:
            x_min = left_margin + c['persp_extra_x']
            x_max = max(x_min + 1, sw - right_margin - c['persp_extra_x'])
        if y_max <= y_min:
            y_min = top_margin + c['persp_extra_y']
            y_max = max(y_min + 1, sh - bottom_margin - c['persp_extra_y'])

        # self.x 是文本左边缘，self.y 是文本基线位置
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
                fading = FadingLine(self.wrapped_lines, self.font, self.x, self.y, self.angle,
                    self.text_color, self.stroke_color, self.stroke_width,
                    self.mode, self.spacing, self.shake_intensity,
                    self.fade_speed, self.rise_speed,
                    self.glow, self.glow_color, self.glow_size, self.glow_alpha,
                    self.persp_transform)
                self.fading_lines.append(fading)
            line_text = self.lyric_timeline[self.current_line][1]
            self.full_text = line_text; self.char_index = 0
            self.wrapped_lines = self.wrap_text(line_text, self._get_max_text_width())
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
                    self.wrapped_lines = []
                    self.start_time = time.time() * 1000
                    self.fading_lines = []; self.update()
            else:
                self.line_timer.stop()

    def show_next_char(self):
        total_chars = sum(len(line) for line in self.wrapped_lines)
        if self.char_index < total_chars:
            self.char_index += 1; self.update()
        else:
            self.char_timer.stop()
            if self._pause_requested:
                # 暂停中且当前句已完整显示：记录暂停时刻（颤动动画继续播放）
                self._paused_at = time.time() * 1000

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
        self.wrapped_lines = []
        self._paused_at = None; self._pause_requested = False
        self.update()

    def pause_lyric(self):
        """暂停歌词播放：不再显示下一句，但保留颤动等动画效果持续播放。"""
        if not self.full_text and not self.lyric_timeline:
            return
        self._pause_requested = True
        # 立即停止行推进，不再显示下一句
        self.line_timer.stop()
        # 颤动动画（shake_timer）保持运行，暂停期间歌词仍在颤动
        # 逐字显示（char_timer）：若正在逐字显示则继续播完当前句，之后由
        # show_next_char 记录暂停时刻；若未显示或已显示完则无需处理
        if self._paused_at is None and (not self.full_text or not self.char_timer.isActive()):
            # 当前句已完整显示（或尚未开始）：立即记录暂停时刻
            self._paused_at = time.time() * 1000

    def resume_lyric(self):
        """恢复歌词播放：从暂停位置继续，不跳歌。"""
        if self._paused_at is not None:
            # 把暂停时长补偿进 start_time，避免恢复后歌词时间瞬间跳变
            self.start_time += time.time() * 1000 - self._paused_at
            self._paused_at = None
        self._pause_requested = False
        if self.lyric_timeline:
            self.line_timer.start(50)
        if self.full_text:
            self.char_timer.start()
            self.shake_timer.start(self.shake_speed)

    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.Antialiasing)
        for f in self.fading_lines: f.draw(painter)
        if self.char_index == 0 or not self.wrapped_lines: return
        fm = QFontMetrics(self.font)
        th = fm.height(); angle_rad = math.radians(self.angle)
        line_spacing = th * 0.3
        
        painter.save()
        if self.perspective_enabled:
            painter.setTransform(self.persp_transform, True)
        painter.translate(self.x, self.y)
        if self.mode == 'chinese':
            shadow_c = QColor(self.stroke_color); text_c = QColor(self.text_color)
        else:
            stroke_c = QColor(self.stroke_color); fill_c = QColor(self.text_color)
        
        # 计算每行要显示多少字符
        chars_remaining = self.char_index
        shake_idx = 0
        for line_idx, line_text in enumerate(self.wrapped_lines):
            if chars_remaining <= 0:
                break
            show_count = min(chars_remaining, len(line_text))
            draw_text = line_text[:show_count]
            chars_remaining -= show_count
            
            # 每行的 Y 偏移
            line_y_offset = line_idx * (th + line_spacing)
            
            cursor = 0
            for i, ch in enumerate(draw_text):
                si = shake_idx + i
                sx = self.char_shakes[si]['x'] if si < len(self.char_shakes) else 0
                sy = self.char_shakes[si]['y'] if si < len(self.char_shakes) else 0
                cw = fm.horizontalAdvance(ch)
                ox = cursor * math.cos(angle_rad)
                oy = cursor * math.sin(angle_rad) + line_y_offset
                if self.glow:
                    gc = QColor(self.glow_color)
                    gc.setAlpha(self.glow_alpha)
                    path_glow = QPainterPath()
                    path_glow.addText(ox + sx, oy + sy + th/3, self.font, ch)
                    pen_g = QPen(gc, self.glow_size)
                    painter.setPen(pen_g); painter.setBrush(Qt.NoBrush)
                    painter.drawPath(path_glow)
                if self.mode == 'chinese':
                    path_shadow = QPainterPath()
                    path_shadow.addText(ox + sx + 3, oy + sy + 3 + th/3, self.font, ch)
                    painter.setPen(Qt.NoPen); painter.setBrush(shadow_c)
                    painter.drawPath(path_shadow)
                    path_text = QPainterPath()
                    path_text.addText(ox + sx, oy + sy + th/3, self.font, ch)
                    painter.setPen(Qt.NoPen); painter.setBrush(text_c)
                    painter.drawPath(path_text)
                else:
                    path = QPainterPath()
                    path.addText(ox + sx, oy + sy + th/3, self.font, ch)
                    pen = QPen(stroke_c, self.stroke_width * 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
                    painter.setPen(pen); painter.setBrush(fill_c)
                    painter.drawPath(path)
                cursor += cw + self.spacing
            shake_idx += len(line_text)
        painter.restore()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape: QApplication.quit()