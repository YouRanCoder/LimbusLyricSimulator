from PyQt5.QtWidgets import QMainWindow, QApplication
from PyQt5.QtCore import Qt, QTimer, QRect
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
# 预点亮槽位渐入动画时长（秒，暗态模式）
_SLOT_FADE_IN = 0.4
# 预点亮亮态模式下未播放句的逐字显示间隔（毫秒/字，与播放时逐字效果一致）
_SLOT_REVEAL_MS = 50


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
        # mode 为用户全局选择：'chinese'/'english' 强制统一，'auto' 按句判定；
        # _line_mode 为当前句实际生效的模式（恒为 'chinese'/'english'）
        self.mode = 'auto'; self._line_mode = 'chinese'; self.spacing = 5.0
        self.shake_intensity = 2; self.shake_speed = 143
        self.fade_speed = 12; self.rise_speed = 1
        self.glow = True; self.glow_color = QColor("#d8a523")
        self.glow_size = 4; self.glow_alpha = 82
        # 播放器真实进度（毫秒，None 表示内部计时）
        # _applied_external_time: 已应用到时间轴的进度（消费过的值），
        #                         用于回落检测的基准，避免 200ms 轮询的中间采样把回退吞掉
        self.external_time = None
        self._applied_external_time = 0
        # 歌词演出延迟（毫秒）：正值延后显示，负值提前显示，作用于时间基准
        self.lyric_offset_ms = 0
        # 跟读预点亮：当前句之后保持暗态显示的后续句数（0=关闭，1/2=同屏 2~3 句）
        # preview_slots 为暗态槽位列表，每项：
        #   {idx: 时间轴行索引, rows: 折行结果, x, y, angle: 独立位置与角度,
        #    transform: 该位置的透视变换}
        # 槽位按行索引左右分区（idx 偶数在左、奇数在右），放置时做碰撞规避
        # 保证互不重叠；唱到时原地"点亮"（沿用槽位的位置与折行，不重新随机）
        self.preview_count = 0
        self.preview_slots = []
        # 未播放歌词是否保持暗态（True=暗态预点亮；False=亮态常驻，
        # 唱到时跳过逐字动画直接整句呈现，唱完走现有残影淡出）
        self.preview_keep_dim = True
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
        # 歌词整体透明度（百分比，0=全透明，100=全不透明）
        self.opacity = 100
        # 歌词禁止区域（QRect 像素坐标，None=无禁止区域）
        self.exclude_region = None
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

    @staticmethod
    def _detect_line_mode(text):
        """按句判定中英文渲染模式：含 CJK 文字 → 中文样式，否则英文样式

        CJK 含汉字、日文假名、韩文谚文（笔画密集，阴影式更合适）。
        中文歌词夹杂英文单词（极常见）仍归中文样式；
        整句没有任何 CJK（纯英文/拼音）才用描边式。
        无有效文字（纯符号/空串）返回 None，表示沿用全局模式。
        每句仅在切句时调用一次，O(n) 字符扫描开销可忽略。
        """
        has_cjk = has_latin = False
        for ch in text:
            if ch.isspace():
                continue
            o = ord(ch)
            if (0x2E80 <= o <= 0x9FFF or      # CJK 部首扩展/汉字/假名/注音
                    0xAC00 <= o <= 0xD7AF or   # 谚文
                    0xF900 <= o <= 0xFAFF):    # CJK 兼容表意文字
                has_cjk = True
            elif ch.isascii() and ch.isalpha():
                has_latin = True
        if has_cjk:
            return 'chinese'
        return 'english' if has_latin else None

    def _apply_mode_for_line(self, text):
        """确定当前句生效的渲染模式并写入 _line_mode

        mode='auto' 时按句判定（无有效文字则兜底中文式）；
        否则强制使用全局模式。
        """
        if self.mode == 'auto':
            self._line_mode = self._detect_line_mode(text) or 'chinese'
        else:
            self._line_mode = self.mode

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
        中英双语配对的文本以 \n 分隔原文与译文，先按段拆分再逐段折叠，
        保证原文与译文各自独立折行显示。
        """
        if not text:
            return []
        if max_width <= 0:
            return [text]

        # 双语配对文本：按换行符分段，各自独立折行
        if '\n' in text:
            lines = []
            for part in text.split('\n'):
                lines.extend(self.wrap_text(part, max_width))
            return lines

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
                    fade_speed, rise_speed, glow, glow_color, glow_size, glow_alpha):
        logger.info("开始显示歌词：字符数=%d，模式=%s",
                    len(text), mode)
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
        # 全局模式变化后先同步到当前句（后续逐句由 _activate_line 刷新）
        self._apply_mode_for_line(text)
        self.shake_intensity = shake_intensity; self.shake_speed = shake_speed
        self.fade_speed = fade_speed; self.rise_speed = rise_speed
        self.glow = glow; self.glow_color = glow_color
        self.glow_size = glow_size; self.glow_alpha = glow_alpha
        self.lyric_timeline = parse_lrc(text); self.fading_lines = []
        if not self.lyric_timeline:
            logger.info("未解析到时间轴，按纯文本逐字播放")
            self._apply_mode_for_line(text)
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
        self.persp_transform = self._persp_transform_at(self.x, self.y)

    def _persp_transform_at(self, x, y):
        """计算任意锚点位置的透视变换（供当前句与暗态预览槽位共用）"""
        if not self.perspective_enabled:
            return QTransform()
        rel_x = (x - self.screen_w / 2) / (self.screen_w / 2)
        rel_y = (y - self.screen_h / 2) / (self.screen_h / 2)
        persp_x = self.persp_x_strength * rel_x
        persp_y = self.persp_y_strength * rel_y
        scale_x = 1.0 + self.persp_compensation * max(0, rel_x)
        t = QTransform()
        t.setMatrix(scale_x, 0, persp_x,
                    0, 1, persp_y,
                    0, 0, 1)
        return t
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

        # 有禁止区域时忽略百分比范围，用全屏作为可选区域；
        # 无禁止区域时用百分比范围约束
        if self.exclude_region is not None:
            x_min = left_margin + c['persp_extra_x']
            x_max = sw - right_margin - c['persp_extra_x']
            y_min = top_margin + c['persp_extra_y']
            y_max = sh - bottom_margin - c['persp_extra_y']
        else:
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
        self.angle = random.randint(self.angle_min, self.angle_max)
        placed = False
        for _ in range(20):
            self.x = random.randint(x_min, x_max)
            self.y = random.randint(y_min, y_max)
            if not self._overlaps_exclude_region(rotated_w, total_height, base):
                placed = True
                break
        # 随机采样全失败时，紧贴禁区边缘放置（保证不落在禁区内）
        if not placed and self.exclude_region is not None:
            self._place_adjacent_to_exclude(
                x_min, x_max, y_min, y_max, rotated_w, total_height, base)
        self.compute_perspective()

    def _overlaps_exclude_region(self, text_w, text_h, padding):
        """当前 (x, y) 位置的文本包围盒是否与禁止区域重叠"""
        r = self.exclude_region
        if r is None:
            return False
        # 文本包围盒（含发光/阴影边距）
        tx, ty = int(self.x - padding), int(self.y - text_h - padding)
        tw, th = int(text_w + 2 * padding), int(text_h + 2 * padding)
        return (tx < r.x() + r.width() and tx + tw > r.x() and
                ty < r.y() + r.height() and ty + th > r.y())

    def _place_adjacent_to_exclude(self, x_min, x_max, y_min, y_max,
                                   text_w, text_h, padding):
        """随机采样失败时，确定性地放在禁区旁边最大侧"""
        r = self.exclude_region
        rw = int(text_w + 2 * padding)
        rh = int(text_h + 2 * padding)
        # 四边可用空间
        candidates = []
        if r.x() - x_min >= rw:
            candidates.append(('left', r.x() - x_min))
        if x_max - (r.x() + r.width()) >= rw:
            candidates.append(('right', x_max - (r.x() + r.width())))
        if r.y() - y_min >= rh:
            candidates.append(('top', r.y() - y_min))
        if y_max - (r.y() + r.height()) >= rh:
            candidates.append(('bottom', y_max - (r.y() + r.height())))
        if not candidates:
            self.x, self.y = x_min, y_min + text_h
            return
        side, _ = max(candidates, key=lambda s: s[1])
        # 主轴紧贴禁区边缘，交叉轴对齐禁区顶/左
        if side == 'left':
            self.x = r.x() - rw
            self.y = r.y()
        elif side == 'right':
            self.x = r.x() + r.width()
            self.y = r.y()
        elif side == 'top':
            self.y = r.y() - rh + text_h
            self.x = r.x()
        else:
            self.y = r.y() + r.height() + rh + text_h
            self.x = r.x()
        # 验证并修正
        if self._overlaps_exclude_region(text_w, text_h, padding):
            if side in ('left', 'right'):
                self.y = r.y() + r.height() + rh + text_h
            else:
                self.x = r.x() + r.width() + rw

    # ---- 跟读预点亮：暗态槽位的左右分区放置与碰撞规避 ----

    def _rotated_aabb(self, x, y, rows, angle):
        """计算文本块的轴对齐包围盒 (x0, y0, w, h)，y 为首行基线

        已含发光/阴影余量；旋转按整块刚性旋转近似（与预览行绘制一致）。
        """
        c = self._compute_place_constraints()
        fm = QFontMetrics(self.font)
        th = fm.height()
        width = max((self._text_width(r) for r in rows), default=0)
        height = len(rows) * (th + c['line_spacing'])
        ar = math.radians(angle)
        rot_w = width * abs(math.cos(ar)) + height * abs(math.sin(ar))
        rot_h = width * abs(math.sin(ar)) + height * abs(math.cos(ar))
        pad = c['glow_margin'] + c['shadow_margin']
        return (x - pad, y - th - pad, rot_w + 2 * pad, rot_h + 2 * pad)

    def _slot_collides(self, rect):
        """包围盒是否与当前句或任何存活暗态槽位重叠"""
        if self.wrapped_lines and self.full_text:
            if self._rects_overlap(rect, self._rotated_aabb(self.x, self.y, self.wrapped_lines, self.angle)):
                return True
        for s in self.preview_slots:
            if self._rects_overlap(rect, self._rotated_aabb(s['x'], s['y'], s['rows'], s['angle'])):
                return True
        return False

    @staticmethod
    def _rects_overlap(a, b):
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah

    def _spawn_preview_slot(self, idx):
        """为第 idx 句创建暗态槽位：全屏随机放置 + 碰撞规避

        长句（折行后仍很宽）在常规范围放不下时，逐步放宽到屏幕居中兜底，
        保证任何句子都能生成槽位；碰撞多次失败才允许少量重叠（视觉上
        优于整句消失）。
        """
        rows = self.wrap_text(self.lyric_timeline[idx][1], self._get_max_text_width())
        if not rows:
            return
        c = self._compute_place_constraints()
        fm = QFontMetrics(self.font)
        th = fm.height()
        width = max(self._text_width(r) for r in rows)
        height = len(rows) * (th + c['line_spacing'])
        angle = random.randint(self.angle_min, self.angle_max)
        ar = math.radians(angle)
        rot_w = width * abs(math.cos(ar)) + height * abs(math.sin(ar))
        rot_h = width * abs(math.sin(ar)) + height * abs(math.cos(ar))

        sw, sh = c['sw'], c['sh']
        base = int(c['base_margin'])
        x_min = max(c['user_x_min'], base + c['persp_extra_x'])
        x_max = min(c['user_x_max'], sw - int(rot_w) - base - c['persp_extra_x'])
        y_min = max(c['user_y_min'], int(th) + c['persp_extra_y'])
        y_max = min(c['user_y_max'], sh - int(rot_h) - int(th) - c['persp_extra_y'])
        # 常规范围放不下（长句/小屏）：放宽到可用区居中，保证句子不消失
        if x_max <= x_min:
            x_min = x_max = max(base + c['persp_extra_x'], int((sw - rot_w) / 2))
        if y_max <= y_min:
            y_min = y_max = max(c['user_y_min'], int((sh - rot_h - th) / 2))

        fallback = None
        for _ in range(40):
            x = random.randint(x_min, x_max)
            y = random.randint(y_min, y_max)
            if fallback is None:
                fallback = (x, y)
            if not self._slot_collides(self._rotated_aabb(x, y, rows, angle)):
                self._add_preview_slot(idx, rows, x, y, angle)
                return
        # 全部尝试失败（屏幕拥挤）：用首个候选兜底
        self._add_preview_slot(idx, rows, fallback[0], fallback[1], angle)

    def _add_preview_slot(self, idx, rows, x, y, angle):
        self.preview_slots.append({
            'idx': idx, 'rows': rows, 'x': x, 'y': y, 'angle': angle,
            'transform': self._persp_transform_at(x, y),
            'born': time.time(),  # 渐入动画起点
        })

    def _ensure_preview_slots(self, current_idx):
        """确保后续 preview_count 句都有暗态槽位，缺失的按分区补齐"""
        if self.preview_count <= 0 or not self.lyric_timeline:
            self.preview_slots = []
            return
        want = set(range(current_idx + 1,
                         min(current_idx + 1 + self.preview_count, len(self.lyric_timeline))))
        self.preview_slots = [s for s in self.preview_slots if s['idx'] in want]
        for idx in sorted(want - {s['idx'] for s in self.preview_slots}):
            self._spawn_preview_slot(idx)

    def set_preview_count(self, count):
        """设置跟读预点亮句数（当前句之后暗态显示的后续句数，0=关闭），播放中立即重排"""
        self.preview_count = max(0, int(count))
        if self.full_text and self.lyric_timeline and self.line_timer.isActive():
            idx = max(0, self.current_line - 1)  # 当前句索引
            self._ensure_preview_slots(idx)
        else:
            self.preview_slots = []
        self.update()

    def check_lyric_time(self):
        # 时间基准：优先使用播放器真实进度（实时适配），否则回退到内部计时；
        # 统一叠加用户设定的演出延迟（正值延后/负值提前，故为减法：
        # 延迟 +1s 表示行点 1.0s 的歌词在歌曲进度 2.0s 时才激活）
        if self.external_time is not None:
            elapsed = self.external_time - self.lyric_offset_ms
        else:
            if self.start_time == 0: self.start_time = time.time() * 1000
            elapsed = time.time() * 1000 - self.start_time - self.lyric_offset_ms

        timeline = self.lyric_timeline
        if not timeline:
            return

        # 外部进度明显回落（seek 回退/单曲循环归零）的重定位在
        # set_external_time 中已直接处理（不依赖 line_timer 状态），
        # 这里不再重复 _seek_to。

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
                        self._line_mode, self.spacing, self.shake_intensity,
                        self.fade_speed, self.rise_speed,
                        self.glow, self.glow_color, self.glow_size, self.glow_alpha,
                        self.persp_transform)
                    self.fading_lines = [fading]  # 只保留跳转前一句，清掉更早残影
                self._activate_line(target)
                # 跳过同时间戳的配对翻译行（双语合并已由 _activate_line 处理）
                self.current_line = self._advance_past_pair(target)
            else:
                # 正常逐句推进（一次一行）
                while (self.current_line < len(timeline) and
                       timeline[self.current_line][0] <= elapsed):
                    if self.full_text and self.char_index > 0:
                        fading = FadingLine(self.wrapped_lines, self.font, self.x, self.y, self.angle,
                            self.text_color, self.stroke_color, self.stroke_width,
                            self._line_mode, self.spacing, self.shake_intensity,
                            self.fade_speed, self.rise_speed,
                            self.glow, self.glow_color, self.glow_size, self.glow_alpha,
                            self.persp_transform)
                        self.fading_lines.append(fading)
                    self._activate_line(self.current_line)
                    # 跳过同时间戳的配对翻译行（双语合并已由 _activate_line 处理）
                    self.current_line = self._advance_past_pair(self.current_line)
            # 同步已应用进度基准：本次消费的 external_time 已落到时间轴上
            if self.external_time is not None:
                self._applied_external_time = self.external_time

        # 播完处理
        if self.current_line >= len(timeline):
            # 末尾也要把已应用进度推到当前 external_time：
            # 之后若发生回拖（单曲循环归零 / 用户手动 seek 回前面），
            # 起点为真实末尾进度，差值判定才不会因基准过老而漏触发。
            if self.external_time is not None:
                self._applied_external_time = self.external_time
            self.line_timer.stop()

    def _seek_to(self, elapsed):
        """外部进度回落（seek 回退/单曲循环归零）后，重新定位到 elapsed 对应的行"""
        self.fading_lines = []
        self.full_text = ""; self.char_index = 0
        self.wrapped_lines = []
        self.preview_slots = []
        self.update()
        if elapsed < self.lyric_timeline[0][0]:
            self.current_line = 0
            return
        target = self._find_line_index(elapsed)
        self._activate_line(target)
        # 跳过同时间戳的配对翻译行（双语合并已由 _activate_line 处理）
        self.current_line = self._advance_past_pair(target)

    def _find_line_index(self, elapsed):
        """返回 elapsed 时刻应显示的行索引（最后一个 t <= elapsed 的行）"""
        target = 0
        for i, (t, _) in enumerate(self.lyric_timeline):
            if t <= elapsed:
                target = i
            else:
                break
        return target

    def _line_text_at(self, idx):
        """返回第 idx 行的显示文本

        双语配对（两行同时间戳）时按一对显示：若本行是配对翻译行
        （与上一行同时间戳）则以原文行（idx-1）为锚点；
        若下一行是配对翻译行，则拼接为两行一起返回。
        """
        if self._skip_paired_line(idx):
            idx = idx - 1
        text = self.lyric_timeline[idx][1]
        if (idx + 1 < len(self.lyric_timeline) and
                self.lyric_timeline[idx + 1][0] == self.lyric_timeline[idx][0]):
            text = text + '\n' + self.lyric_timeline[idx + 1][1]
        return text

    def _skip_paired_line(self, idx):
        """若 idx 是配对行（与上一行同时间戳），返回 True 并跳过"""
        return (idx > 0 and
                self.lyric_timeline[idx][0] == self.lyric_timeline[idx - 1][0])

    def _advance_past_pair(self, idx):
        """从 idx 前进到配对行之后（跳过同时间戳的后续行）"""
        while (idx + 1 < len(self.lyric_timeline) and
               self.lyric_timeline[idx + 1][0] == self.lyric_timeline[idx][0]):
            idx += 1
        return idx + 1

    def _activate_line(self, idx):
        """激活第 idx 行：设置文本、折叠、随机位置与逐字动画速度

        若本句已有暗态预点亮槽位，则原地"点亮"：沿用槽位的位置、角度与
        折行，不重新随机；否则按原有随机放置。
        若下一行时间戳相同（双语配对），自动合并为两行显示。
        """
        line_text = self._line_text_at(idx)
        self._apply_mode_for_line(line_text)
        self.full_text = line_text; self.char_index = 0
        slot = next((s for s in self.preview_slots if s['idx'] == idx), None)
        # 丢弃进度已跳过的过期槽位（保留的都在本句之后）
        self.preview_slots = [s for s in self.preview_slots if s['idx'] > idx]
        if slot is not None:
            self.wrapped_lines = slot['rows']
            self.x = slot['x']; self.y = slot['y']; self.angle = slot['angle']
            self.compute_perspective()
            self.init_char_shakes()
            if not self.preview_keep_dim:
                # 亮态常驻模式下句子早已完整显示：跳过逐字动画直接整句呈现，
                # 唱完后按现有残影机制正常淡出
                self.char_index = len(line_text)
        else:
            self.wrapped_lines = self.wrap_text(line_text, self._get_max_text_width())
            self.init_char_shakes(); self.place_randomly()
        # 点亮消耗了一个槽位，补齐后续句的暗态槽位
        self._ensure_preview_slots(idx)
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
        self.preview_slots = []
        # 重置已应用进度基准，配合外层下一帧的回退检测归零触发 _seek_to
        self._applied_external_time = 0
        if self.external_time is None:
            self.start_time = time.time() * 1000

    def set_lyric_offset_ms(self, ms):
        """设置歌词演出延迟（毫秒，正值延后/负值提前），播放中按新基准重新对齐当前行"""
        self.lyric_offset_ms = ms
        if self.lyric_timeline and self.line_timer.isActive():
            # 向后调整时行指针不会自动回退，直接按新基准重定位
            if self.external_time is not None:
                elapsed = self.external_time - ms
            elif self.start_time:
                elapsed = time.time() * 1000 - self.start_time - ms
            else:
                elapsed = -ms
            self._seek_to(elapsed)
            # 同步已应用进度基准：offset 调整会改 current_line，
            # 若不更新 _applied_external_time，下一次回退检测会拿错基准
            if self.external_time is not None:
                self._applied_external_time = self.external_time

    def set_external_time(self, ms):
        """设置播放器真实进度（毫秒），驱动歌词时间轴实时适配"""
        # 回落检测基准：已应用到时间轴的进度（_applied_external_time），
        # 用已应用值而不是上次轮询采样，避免 200ms 轮询的中间值把跨越大距离的
        # 回退（seek 回拖/单曲循环归零）吞掉，导致歌词停在末尾不动。
        rewound = ms < self._applied_external_time - 500
        if rewound:
            logger.debug("检测到外部进度回落：%dms -> %dms（seek/循环），重新定位",
                         self._applied_external_time, ms)
        # 立即执行重定位：不依赖 line_timer 状态。
        # 之前逻辑放在 if line_timer.isActive() 内部，但播完时 line_timer 会被
        # 自身 stop()，导致末尾回拖无法触发 _seek_to，歌词卡死在末句。
        # 移到这里后，line_timer 已停的尾部也能在回拖时立刻重新定位。
        if rewound and self.lyric_timeline:
            self.fading_lines = []
            self.external_time = ms
            elapsed = ms - self.lyric_offset_ms
            self._seek_to(elapsed)
            # 同步已应用进度基准，避免下一帧回退检测重复触发
            self._applied_external_time = ms
            # 播完自停的 line_timer 在重定位后必须重新启动，
            # 否则不会推进到重定位到的行（外部进度 timer 是 200ms 一次，但
            # 当前帧不会再被消费——check_lyric_time 需要 line_timer 驱动逐行推进）
            if not self.line_timer.isActive():
                self.line_timer.start(50)
            return
        self.external_time = ms
        if self.lyric_timeline and self.line_timer.isActive():
            self.check_lyric_time()

    def switch_to_internal_timing(self):
        """外部进度不可用（SMTC 停滞/读取失败）：切回内部计时并衔接当前进度

        把内部计时基准设为「基准时刻 - 最后有效外部进度」，使内部 elapsed
        从最后进度继续推进，而不是从 0 重新开始，避免歌词跳回第一句。
        暂停中以暂停时刻为基准，保证 resume 的暂停补偿不会重复计算。
        保留 _applied_external_time：回退期间若发生 seek 回退/单曲循环，
        恢复外部进度时仍能触发回落重定位。
        """
        if self.external_time is None:
            return
        logger.debug("切换回内部计时：从 %dms 衔接", self.external_time)
        base = self._paused_at if self._paused_at is not None else time.time() * 1000
        self.start_time = base - self.external_time
        self.external_time = None

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
        has_fading = bool(self.fading_lines)
        if has_fading:
            self.fading_lines = [f for f in self.fading_lines if f.update()]
        # 有槽位尚在渐入/逐字显现期间时保持重绘，驱动动画
        now = time.time()
        if self.preview_keep_dim:
            has_animating = any(now - s.get('born', 0.0) < _SLOT_FADE_IN
                                for s in self.preview_slots)
        else:
            has_animating = any(
                (now - s.get('born', 0.0)) * 1000 < sum(len(r) for r in s['rows']) * _SLOT_REVEAL_MS
                for s in self.preview_slots)
        if has_fading or has_animating:
            self.update()

    def stop_lyric(self):
        logger.info("停止歌词显示")
        self.char_timer.stop(); self.shake_timer.stop(); self.line_timer.stop()
        self.full_text = ""; self.char_index = 0
        self.lyric_timeline = []; self.current_line = 0
        self.fading_lines = []; self.char_shakes = []
        self.wrapped_lines = []
        self.preview_slots = []
        self.external_time = None
        self._applied_external_time = 0
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
        painter.setOpacity(self.opacity / 100.0)
        for f in self.fading_lines: f.draw(painter)
        # 暗态预点亮槽位画在最底层、且在早退返回之前：
        # 保证逐字间隙（char_index=0）期间未读句不闪断
        self._paint_preview_slots(painter)
        if self.char_index == 0 or not self.wrapped_lines: return
        fm = QFontMetrics(self.font)
        th = fm.height(); angle_rad = math.radians(self.angle)
        line_spacing = th * 0.3
        
        painter.save()
        if self.perspective_enabled:
            painter.setTransform(self.persp_transform, True)
        painter.translate(self.x, self.y)
        if self._line_mode == 'chinese':
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
                if self._line_mode == 'chinese':
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

    def _paint_preview_slots(self, painter):
        """绘制暗态预点亮槽位：后续句在各自分区位置的低亮度静态显示

        绘制方式与当前句/FadingLine 一致（逐字符沿角度排布），保证点亮
        瞬间渲染无缝切换；新槽位 0.4s 渐入，不逐字不颤动。
        """
        if not self.preview_slots:
            return
        now = time.time()
        fm = QFontMetrics(self.font)
        th = fm.height()
        line_spacing = th * 0.3
        for slot in self.preview_slots:
            if self.preview_keep_dim:
                # 暗态：整句渐入后保持低亮度
                fade_in = max(0.0, min(1.0, (now - slot.get('born', 0.0)) / _SLOT_FADE_IN))
                alpha_factor = 0.35 * fade_in
                reveal = None  # 显示全部字符
            else:
                # 亮态：按播放时的逐字方式显现，显完后常驻
                alpha_factor = 1.0
                reveal = int((now - slot.get('born', 0.0)) * 1000 / _SLOT_REVEAL_MS)
                if reveal <= 0:
                    continue
            painter.save()
            if self.perspective_enabled:
                painter.setTransform(slot['transform'], True)
            painter.translate(slot['x'], slot['y'])
            angle_rad = math.radians(slot['angle'])
            if self._line_mode == 'chinese':
                shadow_c = QColor(self.stroke_color); text_c = QColor(self.text_color)
            else:
                stroke_c = QColor(self.stroke_color); fill_c = QColor(self.text_color)
            for line_idx, row in enumerate(slot['rows']):
                if reveal is not None:
                    if reveal <= 0:
                        break
                    show_count = min(reveal, len(row))
                    draw_text = row[:show_count]
                    reveal -= show_count
                else:
                    draw_text = row
                line_y_offset = line_idx * (th + line_spacing)
                cursor = 0
                for ch in draw_text:
                    cw = fm.horizontalAdvance(ch)
                    ox = cursor * math.cos(angle_rad)
                    oy = cursor * math.sin(angle_rad) + line_y_offset
                    if self._line_mode == 'chinese':
                        shadow_p = QPainterPath()
                        shadow_p.addText(ox + 3, oy + 3 + th / 3, self.font, ch)
                        sc = QColor(shadow_c); sc.setAlpha(int(sc.alpha() * alpha_factor))
                        painter.setPen(Qt.NoPen); painter.setBrush(sc)
                        painter.drawPath(shadow_p)
                        text_p = QPainterPath()
                        text_p.addText(ox, oy + th / 3, self.font, ch)
                        tc = QColor(text_c); tc.setAlpha(int(tc.alpha() * alpha_factor))
                        painter.setPen(Qt.NoPen); painter.setBrush(tc)
                        painter.drawPath(text_p)
                    else:
                        stc = QColor(stroke_c); stc.setAlpha(int(stroke_c.alpha() * alpha_factor))
                        fcc = QColor(fill_c); fcc.setAlpha(int(fcc.alpha() * alpha_factor))
                        text_p = QPainterPath()
                        text_p.addText(ox, oy + th / 3, self.font, ch)
                        pen = QPen(stc, self.stroke_width * 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
                        painter.setPen(pen); painter.setBrush(fcc)
                        painter.drawPath(text_p)
                    cursor += cw + self.spacing
            painter.restore()