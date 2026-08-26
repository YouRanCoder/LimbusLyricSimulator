from PyQt5.QtWidgets import QMainWindow, QApplication
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter, QColor, QFont, QFontMetrics, QPen, QPainterPath, QTransform
import random, time, math
import ctypes
import logging
from .fading_line import FadingLine
from core.parser import parse_lrc

logger = logging.getLogger(__name__)

# Windows 窗口防捕获（独立 Overlay）：user32.SetWindowDisplayAffinity
# WDA_EXCLUDEFROMCAPTURE 使窗口对本机用户可见，但 DXGI 桌面复制/
# Windows.Graphics.Capture（OBS、Discord、录屏软件等）全部跳过它。
# 需要 Win10 2004（19041）及以上；旧系统调用会失败并回退为不防捕获。
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.SetWindowDisplayAffinity.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
_user32.SetWindowDisplayAffinity.restype = ctypes.c_bool
_user32.SetWindowPos.argtypes = [
    ctypes.c_void_p, ctypes.c_int,
    ctypes.c_long, ctypes.c_long, ctypes.c_long, ctypes.c_long, ctypes.c_uint]
_user32.SetWindowPos.restype = ctypes.c_bool
_WDA_NONE = 0x00000000
_WDA_EXCLUDEFROMCAPTURE = 0x00000011
_HWND_TOPMOST = -1
# SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE：只提升 z 序，不动位置/尺寸/焦点
_SWP_ZORDER_ONLY = 0x0001 | 0x0002 | 0x0010


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
        # 播放器真实进度（毫秒，None 表示内部计时）；_last_external_time 用于检测进度回落（seek/循环）
        self.external_time = None; self._last_external_time = None
        self._progress_rewound = False
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
        # 防捕获（独立 Overlay）状态：True 时录屏/直播软件捕获不到歌词层
        self._capture_excluded = False
        # 置顶保活：Lossless Scaling 等全屏输出窗口会抢占 z 序把歌词压下去，
        # 周期性重新置顶保证歌词始终浮在插帧画面之上（不影响其捕获与插帧）
        self._topmost_timer = QTimer(self)
        self._topmost_timer.timeout.connect(self._enforce_topmost)
        self._topmost_timer.start(1000)

    def _enforce_topmost(self):
        """把歌词窗重新钉回 topmost（只动 z 序，不抢焦点/位置/尺寸）"""
        try:
            hwnd = int(self.winId())
        except Exception:
            return
        _user32.SetWindowPos(hwnd, _HWND_TOPMOST, 0, 0, 0, 0, _SWP_ZORDER_ONLY)

    def set_exclude_from_capture(self, enabled):
        """启用/停用防捕获（独立 Overlay）：开启后录屏/直播软件看不到歌词层

        通过 SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE) 实现。
        Returns:
            bool: 是否设置成功（旧版 Windows 不支持时返回 False）
        """
        ok = self._apply_display_affinity(enabled)
        if ok:
            if enabled != self._capture_excluded:
                logger.info("歌词窗口防捕获已%s（WDA_EXCLUDEFROMCAPTURE）",
                            "开启" if enabled else "关闭")
            self._capture_excluded = enabled
        return ok

    def _apply_display_affinity(self, enabled):
        """对原生窗口套用/清除防捕获标记，返回是否成功"""
        try:
            # winId() 会按需创建原生句柄，未显示时调用同样有效
            hwnd = int(self.winId())
            affinity = _WDA_EXCLUDEFROMCAPTURE if enabled else _WDA_NONE
            if not _user32.SetWindowDisplayAffinity(hwnd, affinity):
                logger.warning("SetWindowDisplayAffinity 失败：affinity=0x%X，"
                               "GetLastError=%d（需要 Win10 2004+）",
                               affinity, ctypes.get_last_error())
                return False
            return True
        except Exception:
            logger.exception("应用窗口防捕获标记异常")
            return False

    def showEvent(self, event):
        """窗口显示时重新套用防捕获标记（Qt 可能重建了原生句柄）"""
        super().showEvent(event)
        if self._capture_excluded:
            self._apply_display_affinity(True)

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
        logger.info("开始显示歌词：字符数=%d，模式=%s，启动延时=%ds",
                    len(text), mode, start_delay)
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
            logger.info("未解析到时间轴，按纯文本逐字播放")
            self.wrapped_lines = self.wrap_text(text, self._get_max_text_width())
            self.full_text = text; self.char_index = 0
            self.init_char_shakes(); self.place_randomly()
            self.char_timer.start(50); self.shake_timer.start(self.shake_speed)
            return
        logger.info("歌词时间轴已就绪：共 %d 句", len(self.lyric_timeline))
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
        # 时间基准：优先使用播放器真实进度（实时适配），否则回退到内部计时
        if self.external_time is not None:
            elapsed = self.external_time
        else:
            if self.start_time == 0: self.start_time = time.time() * 1000
            elapsed = time.time() * 1000 - self.start_time

        timeline = self.lyric_timeline
        if not timeline:
            return

        # 外部进度明显回落（seek 回退/单曲循环归零）：一次性重新定位到对应行。
        # 只有回落超过阈值（set_external_time 中检测）才触发，避免播放器进度在
        # 行边界轻微抖动时反复重定位，导致歌词满屏随机跳位（乱飞）。
        if self.external_time is not None and self._progress_rewound:
            self._progress_rewound = False  # 只处理一次，防止 line_timer 重复触发
            self._seek_to(elapsed)
            return

        # 前进：推进到 elapsed 时刻应显示的行
        if (self.current_line < len(timeline) and
                timeline[self.current_line][0] <= elapsed):
            target = self._find_line_index(elapsed)
            if target > self.current_line:
                # 进度一次跨越多行（seek 前进）：直接定位到目标行，
                # 避免逐行激活产生多个随机位置的残影
                if self.full_text and self.char_index > 0:
                    fading = FadingLine(self.wrapped_lines, self.font, self.x, self.y, self.angle,
                        self.text_color, self.stroke_color, self.stroke_width,
                        self.mode, self.spacing, self.shake_intensity,
                        self.fade_speed, self.rise_speed,
                        self.glow, self.glow_color, self.glow_size, self.glow_alpha,
                        self.persp_transform)
                    self.fading_lines = [fading]  # 只保留跳转前一句，清掉更早残影
                self._activate_line(target)
                self.current_line = target + 1
            else:
                # 正常逐句推进（一次一行）
                while (self.current_line < len(timeline) and
                       timeline[self.current_line][0] <= elapsed):
                    if self.full_text and self.char_index > 0:
                        fading = FadingLine(self.wrapped_lines, self.font, self.x, self.y, self.angle,
                            self.text_color, self.stroke_color, self.stroke_width,
                            self.mode, self.spacing, self.shake_intensity,
                            self.fade_speed, self.rise_speed,
                            self.glow, self.glow_color, self.glow_size, self.glow_alpha,
                            self.persp_transform)
                        self.fading_lines.append(fading)
                    self._activate_line(self.current_line)
                    self.current_line += 1

        # 播完处理
        if self.current_line >= len(timeline):
            if self.loop and self.song_duration > 0:
                # 内部模式：内部计时走完一首歌后循环重播；
                # 外部模式靠回落检测（_progress_rewound）触发循环，这里不再处理
                if self.external_time is None and elapsed >= self.song_duration:
                    self._reset_playback()
            else:
                self.line_timer.stop()

    def _seek_to(self, elapsed):
        """外部进度回落（seek 回退/单曲循环归零）后，重新定位到 elapsed 对应的行"""
        self.fading_lines = []
        self.full_text = ""; self.char_index = 0
        self.wrapped_lines = []
        self.update()
        if elapsed < self.lyric_timeline[0][0]:
            self.current_line = 0
            return
        target = self._find_line_index(elapsed)
        self._activate_line(target)
        self.current_line = target + 1

    def _find_line_index(self, elapsed):
        """返回 elapsed 时刻应显示的行索引（最后一个 t <= elapsed 的行）"""
        target = 0
        for i, (t, _) in enumerate(self.lyric_timeline):
            if t <= elapsed:
                target = i
            else:
                break
        return target

    def _activate_line(self, idx):
        """激活第 idx 行：设置文本、折叠、随机位置与逐字动画速度"""
        line_text = self.lyric_timeline[idx][1]
        self.full_text = line_text; self.char_index = 0
        self.wrapped_lines = self.wrap_text(line_text, self._get_max_text_width())
        self.init_char_shakes(); self.place_randomly()
        if idx + 1 < len(self.lyric_timeline):
            next_time = self.lyric_timeline[idx + 1][0]
            current_time = self.lyric_timeline[idx][0]
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

    def _reset_playback(self):
        """循环重播：清空当前进度，回到歌曲开头"""
        self.current_line = 0; self.char_index = 0
        self.full_text = ""; self.wrapped_lines = []
        self.fading_lines = []; self.update()
        if self.external_time is None:
            self.start_time = time.time() * 1000

    def set_external_time(self, ms):
        """设置播放器真实进度（毫秒），驱动歌词时间轴实时适配"""
        # 在 _last_external_time 更新前检测回落（seek/单曲循环），旧值仍可用
        if (self._last_external_time is not None and
                ms < self._last_external_time - 500):
            logger.debug("检测到外部进度回落：%dms -> %dms（seek/循环），重新定位",
                         self._last_external_time, ms)
            self.fading_lines = []
            self._progress_rewound = True
        else:
            self._progress_rewound = False
        self._last_external_time = ms
        self.external_time = ms
        if self.lyric_timeline and self.line_timer.isActive():
            self.check_lyric_time()

    def switch_to_internal_timing(self):
        """外部进度不可用（SMTC 停滞/读取失败）：切回内部计时并衔接当前进度

        把内部计时基准设为「基准时刻 - 最后有效外部进度」，使内部 elapsed
        从最后进度继续推进，而不是从 0 重新开始，避免歌词跳回第一句。
        暂停中以暂停时刻为基准，保证 resume 的暂停补偿不会重复计算。
        保留 _last_external_time：回退期间若发生 seek 回退/单曲循环，
        恢复外部进度时仍能触发回落重定位。
        """
        if self.external_time is None:
            return
        logger.debug("切换回内部计时：从 %dms 衔接", self.external_time)
        base = self._paused_at if self._paused_at is not None else time.time() * 1000
        self.start_time = base - self.external_time
        self.external_time = None
        self._progress_rewound = False

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
        logger.info("停止歌词显示")
        self.char_timer.stop(); self.shake_timer.stop(); self.line_timer.stop()
        self.full_text = ""; self.char_index = 0
        self.lyric_timeline = []; self.current_line = 0
        self.fading_lines = []; self.char_shakes = []
        self.wrapped_lines = []
        self.external_time = None; self._last_external_time = None
        self._progress_rewound = False
        self._paused_at = None; self._pause_requested = False
        self.update()

    def pause_lyric(self):
        """暂停歌词播放：不再显示下一句，但保留颤动等动画效果持续播放。"""
        if not self.full_text and not self.lyric_timeline:
            return
        logger.debug("暂停歌词播放")
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
        logger.debug("恢复歌词播放")
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