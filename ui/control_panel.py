"""
控制面板 - 纯 UI 层

职责：
1. 构建和显示界面控件
2. 接收用户输入
3. 通过 Controller 触发业务逻辑
4. 监听 Controller 信号更新界面

不直接调用业务逻辑，不管理配置，不操作播放器。
"""

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QLabel, QSlider, QColorDialog, QSpinBox,
    QComboBox, QCheckBox, QInputDialog, QMessageBox,
    QDoubleSpinBox, QScrollArea,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QFontDatabase
import qasync
from core.app_controller import AppController, LyricSettings
from core.fetcher import is_pure_music
import logging


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ControlPanel(QWidget):
    """
    控制面板 - 纯 UI 层
    
    通过 AppController 与业务层交互，不直接调用任何业务逻辑。
    """
    
    def __init__(self, controller: AppController):
        """
        初始化控制面板
        
        Args:
            controller: 应用控制器实例
        """
        super().__init__()
        self.controller = controller
        
        # UI 状态
        self.current_color = QColor("#fffeef")
        self.current_stroke_color = QColor("#d8a523")
        self.current_glow_color = QColor("#d8a523")
        # 纯音乐/伴奏规则（来自 lyric_config.json，None 表示用内置默认）
        self.inst_patterns = None
        
        self.setWindowTitle("歌词字幕器 - 控制面板")
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        
        # 从 Controller 获取配置
        settings = self.controller.get_settings()
        
        self._build_ui()
        self._load_settings(settings)
        self._connect_controller_signals()
        self._connect_ui_events()
        
        # 初始化播放器
        player_name = settings.get_setting('player', '网易云音乐')
        self.controller.switch_player(player_name)
        # 同步 UI 下拉框
        idx = self.player_combo.findText(player_name)
        if idx >= 0:
            self.player_combo.setCurrentIndex(idx)
        
        # 启动播放器监听（延迟到事件循环运行后）
        QTimer.singleShot(0, self.controller.start_player_listener)
    
    def _build_ui(self) -> None:
        """构建界面布局"""
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(6)

        # 缩放
        zoom_layout = QHBoxLayout()
        zoom_layout.addWidget(QLabel("界面缩放："))
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(70, 150)
        self.zoom_slider.setValue(100)
        self.zoom_label = QLabel("100%")
        self.zoom_slider.valueChanged.connect(lambda v: self.zoom_label.setText(f"{v}%"))
        self.zoom_slider.sliderReleased.connect(self.apply_zoom)
        zoom_layout.addWidget(self.zoom_slider)
        zoom_layout.addWidget(self.zoom_label)
        layout.addLayout(zoom_layout)

        # 播放器选择
        player_layout = QHBoxLayout()
        player_layout.addWidget(QLabel("播放器："))
        self.player_combo = QComboBox()
        self._refresh_player_list()
        player_layout.addWidget(self.player_combo)
        btn_add_p = QPushButton("+")
        btn_add_p.setMaximumWidth(30)
        btn_add_p.clicked.connect(self._on_add_player)
        player_layout.addWidget(btn_add_p)
        btn_del_p = QPushButton("-")
        btn_del_p.setMaximumWidth(30)
        btn_del_p.clicked.connect(self._on_delete_player)
        player_layout.addWidget(btn_del_p)
        player_layout.addStretch()
        layout.addLayout(player_layout)

        # 歌词源选择
        source_layout = QHBoxLayout()
        source_layout.addWidget(QLabel("歌词源："))
        self.source_combo = QComboBox()
        self.source_combo.addItems(["网易云", "QQ音乐", "酷狗"])
        source_layout.addWidget(self.source_combo)
        source_layout.addStretch()
        layout.addLayout(source_layout)

        # 网易云适配方式（勾选=网易云日志适配器，取消=SMTC，适用于 inflink-rs 等第三方插件）
        adapter_layout = QHBoxLayout()
        self.netease_adapter_check = QCheckBox("使用网易云适配")
        adapter_layout.addWidget(self.netease_adapter_check)
        adapter_layout.addStretch()
        layout.addLayout(adapter_layout)

        # 纯音乐/伴奏过滤（自动播放时按歌名特征识别，不显示歌词）
        pure_music_layout = QHBoxLayout()
        self.filter_pure_music_check = QCheckBox("过滤纯音乐/伴奏（不显示歌词）")
        pure_music_layout.addWidget(self.filter_pure_music_check)
        pure_music_layout.addStretch()
        layout.addLayout(pure_music_layout)

        layout.addWidget(QLabel("歌词（粘贴LRC格式）："))
        self.text_input = QTextEdit()
        self.text_input.setMinimumHeight(120)
        layout.addWidget(self.text_input)

        fetch_btn = QPushButton("🎵 从播放器获取当前歌词")
        fetch_btn.clicked.connect(self._on_fetch_lyric)
        layout.addWidget(fetch_btn)
        
        # 3D透视开关
        self.perspective_check = QCheckBox("3D透视(测试)")
        self.perspective_check.setChecked(True)
        layout.addWidget(self.perspective_check)

        # 透视X
        px_layout = QHBoxLayout()
        px_layout.addWidget(QLabel("透视X："))
        self.persp_x_slider = QSlider(Qt.Horizontal)
        self.persp_x_slider.setRange(0, 100)
        self.persp_x_slider.setValue(5)
        self.persp_x_label = QLabel("0.00005")
        px_layout.addWidget(self.persp_x_slider)
        px_layout.addWidget(self.persp_x_label)
        layout.addLayout(px_layout)

        # 透视Y
        py_layout = QHBoxLayout()
        py_layout.addWidget(QLabel("透视Y："))
        self.persp_y_slider = QSlider(Qt.Horizontal)
        self.persp_y_slider.setRange(0, 100)
        self.persp_y_slider.setValue(30)
        self.persp_y_label = QLabel("0.00030")
        py_layout.addWidget(self.persp_y_slider)
        py_layout.addWidget(self.persp_y_label)
        layout.addLayout(py_layout)

        # 补偿
        comp_layout = QHBoxLayout()
        comp_layout.addWidget(QLabel("水平补偿："))
        self.persp_comp_slider = QSlider(Qt.Horizontal)
        self.persp_comp_slider.setRange(0, 100)
        self.persp_comp_slider.setValue(3)
        self.persp_comp_label = QLabel("0.03")
        comp_layout.addWidget(self.persp_comp_slider)
        comp_layout.addWidget(self.persp_comp_label)
        layout.addLayout(comp_layout)
        
        # 选项行
        options_row = QHBoxLayout()
        self.trans_check = QCheckBox("仅获取翻译歌词")
        self.trans_check.setChecked(False)
        options_row.addWidget(self.trans_check)
        self.loop_check = QCheckBox("单曲循环")
        self.loop_check.setChecked(True)
        options_row.addWidget(self.loop_check)
        options_row.addStretch()
        layout.addLayout(options_row)

        # 启动延时
        delay_layout = QHBoxLayout()
        delay_layout.addWidget(QLabel("启动延时："))
        self.delay_combo = QComboBox()
        self.delay_combo.addItems(["0s", "1s", "2s", "3s", "5s"])
        delay_layout.addWidget(self.delay_combo)
        delay_layout.addStretch()
        layout.addLayout(delay_layout)

        # 预设 + 模式
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("预设："))
        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumWidth(80)
        self._refresh_preset_list()
        top_row.addWidget(self.preset_combo)
        btn_new = QPushButton("+")
        btn_new.setMaximumWidth(30)
        btn_new.clicked.connect(self._on_new_preset)
        top_row.addWidget(btn_new)
        btn_del = QPushButton("-")
        btn_del.setMaximumWidth(30)
        btn_del.clicked.connect(self._on_delete_preset)
        top_row.addWidget(btn_del)
        top_row.addStretch()
        top_row.addWidget(QLabel("模式："))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("中文", "chinese")
        self.mode_combo.addItem("英文", "english")
        self.mode_combo.setMaximumWidth(80)
        top_row.addWidget(self.mode_combo)
        layout.addLayout(top_row)

        # 发光
        glow_layout = QHBoxLayout()
        self.glow_check = QCheckBox("发光")
        self.glow_check.setChecked(True)
        glow_layout.addWidget(self.glow_check)
        glow_layout.addWidget(QLabel("光色："))
        self.glow_color_btn = QPushButton()
        self.glow_color_btn.setFixedSize(30, 30)
        self.glow_color_btn.setStyleSheet(f"background-color:{self.current_glow_color.name()};")
        self.glow_color_btn.clicked.connect(self.pick_glow_color)
        glow_layout.addWidget(self.glow_color_btn)
        glow_layout.addStretch()
        layout.addLayout(glow_layout)

        gsl = QHBoxLayout()
        gsl.addWidget(QLabel("光晕粗细："))
        self.glow_size_slider = QSlider(Qt.Horizontal)
        self.glow_size_slider.setRange(4, 30)
        self.glow_size_slider.setValue(4)
        self.glow_size_label = QLabel("4")
        gsl.addWidget(self.glow_size_slider)
        gsl.addWidget(self.glow_size_label)
        layout.addLayout(gsl)

        gal = QHBoxLayout()
        gal.addWidget(QLabel("光晕透明度："))
        self.glow_alpha_slider = QSlider(Qt.Horizontal)
        self.glow_alpha_slider.setRange(10, 120)
        self.glow_alpha_slider.setValue(82)
        self.glow_alpha_label = QLabel("82")
        gal.addWidget(self.glow_alpha_slider)
        gal.addWidget(self.glow_alpha_label)
        layout.addLayout(gal)

        fl = QHBoxLayout()
        fl.addWidget(QLabel("字体："))
        # QFontComboBox 构造时会枚举并加载系统全部字体（312 个字体约 520ms，
        # 直接拖慢启动出现白屏），改用普通 QComboBox 填充字体家族名（仅 ~2ms）
        self.font_combo = QComboBox()
        self.font_combo.addItems(QFontDatabase().families())
        self.font_combo.setCurrentText("Microsoft YaHei")
        fl.addWidget(self.font_combo)
        fl.addWidget(QLabel("大小："))
        self.font_size = QSpinBox()
        self.font_size.setRange(10, 100)
        self.font_size.setValue(28)
        fl.addWidget(self.font_size)
        layout.addLayout(fl)
        
        fl_auto = QHBoxLayout()
        btn_auto_font = QPushButton("推荐字体")
        btn_auto_font.clicked.connect(self.auto_select_font)
        fl_auto.addWidget(btn_auto_font)
        fl_auto.addStretch()
        layout.addLayout(fl_auto)

        cl = QHBoxLayout()
        cl.addWidget(QLabel("文字："))
        self.color_btn = QPushButton()
        self.color_btn.setFixedSize(30, 30)
        self.color_btn.setStyleSheet(f"background-color:{self.current_color.name()};")
        self.color_btn.clicked.connect(self.pick_color)
        cl.addWidget(self.color_btn)
        cl.addWidget(QLabel("阴影："))
        self.stroke_btn = QPushButton()
        self.stroke_btn.setFixedSize(30, 30)
        self.stroke_btn.setStyleSheet(f"background-color:{self.current_stroke_color.name()};")
        self.stroke_btn.clicked.connect(self.pick_stroke)
        cl.addWidget(self.stroke_btn)
        cl.addStretch()
        layout.addLayout(cl)

        swl = QHBoxLayout()
        swl.addWidget(QLabel("描边粗细："))
        self.stroke_spin = QDoubleSpinBox()
        self.stroke_spin.setRange(0.0, 10.0)
        self.stroke_spin.setSingleStep(0.1)
        self.stroke_spin.setDecimals(1)
        self.stroke_spin.setValue(0.5)
        swl.addWidget(self.stroke_spin)
        swl.addWidget(QLabel("px"))
        layout.addLayout(swl)

        ssl = QHBoxLayout()
        ssl.addWidget(QLabel("字间距："))
        self.spacing_spin = QDoubleSpinBox()
        self.spacing_spin.setRange(-10.0, 30.0)
        self.spacing_spin.setSingleStep(0.5)
        self.spacing_spin.setDecimals(1)
        self.spacing_spin.setValue(5.0)
        ssl.addWidget(self.spacing_spin)
        ssl.addWidget(QLabel("px"))
        layout.addLayout(ssl)

        shl = QHBoxLayout()
        shl.addWidget(QLabel("颤强："))
        self.shake_intensity_slider = QSlider(Qt.Horizontal)
        self.shake_intensity_slider.setRange(0, 10)
        self.shake_intensity_slider.setValue(2)
        self.shake_intensity_label = QLabel("2")
        shl.addWidget(self.shake_intensity_slider)
        shl.addWidget(self.shake_intensity_label)
        layout.addLayout(shl)

        shvl = QHBoxLayout()
        shvl.addWidget(QLabel("颤速："))
        self.shake_speed_slider = QSlider(Qt.Horizontal)
        self.shake_speed_slider.setRange(10, 200)
        self.shake_speed_slider.setValue(143)
        self.shake_speed_label = QLabel("143 ms")
        shvl.addWidget(self.shake_speed_slider)
        shvl.addWidget(self.shake_speed_label)
        layout.addLayout(shvl)

        fsl = QHBoxLayout()
        fsl.addWidget(QLabel("淡出速度："))
        self.fade_speed_slider = QSlider(Qt.Horizontal)
        self.fade_speed_slider.setRange(1, 15)
        self.fade_speed_slider.setValue(12)
        self.fade_speed_label = QLabel("12")
        fsl.addWidget(self.fade_speed_slider)
        fsl.addWidget(self.fade_speed_label)
        layout.addLayout(fsl)

        rsl = QHBoxLayout()
        rsl.addWidget(QLabel("上升速度："))
        self.rise_speed_slider = QSlider(Qt.Horizontal)
        self.rise_speed_slider.setRange(0, 5)
        self.rise_speed_slider.setValue(1)
        self.rise_speed_label = QLabel("1")
        rsl.addWidget(self.rise_speed_slider)
        rsl.addWidget(self.rise_speed_label)
        layout.addLayout(rsl)

        ml = QHBoxLayout()
        ml.addWidget(QLabel("留白："))
        self.margin_spin = QSpinBox()
        self.margin_spin.setRange(0, 5000)
        self.margin_spin.setValue(4000)
        self.margin_spin.setSingleStep(100)
        ml.addWidget(self.margin_spin)
        ml.addWidget(QLabel("ms"))
        ml.addStretch()
        layout.addLayout(ml)

        mil = QHBoxLayout()
        mil.addWidget(QLabel("长间隔阈值："))
        self.max_interval_spin = QSpinBox()
        self.max_interval_spin.setRange(1000, 30000)
        self.max_interval_spin.setValue(16000)
        self.max_interval_spin.setSingleStep(1000)
        mil.addWidget(self.max_interval_spin)
        mil.addWidget(QLabel("ms"))
        mil.addStretch()
        layout.addLayout(mil)

        mdl = QHBoxLayout()
        mdl.addWidget(QLabel("长间隔时长："))
        self.max_duration_spin = QSpinBox()
        self.max_duration_spin.setRange(500, 10000)
        self.max_duration_spin.setValue(5000)
        self.max_duration_spin.setSingleStep(500)
        mdl.addWidget(self.max_duration_spin)
        mdl.addWidget(QLabel("ms"))
        mdl.addStretch()
        layout.addLayout(mdl)

        # 起始位置范围（百分比）
        pos_layout = QHBoxLayout()
        pos_layout.addWidget(QLabel("X范围："))
        self.pos_x_min_s = QSlider(Qt.Horizontal)
        self.pos_x_min_s.setRange(0, 50)
        self.pos_x_min_s.setValue(5)
        self.pos_x_lbl = QLabel("5%")
        pos_layout.addWidget(self.pos_x_min_s)
        pos_layout.addWidget(self.pos_x_lbl)
        pos_layout.addWidget(QLabel("~"))
        self.pos_x_max_s = QSlider(Qt.Horizontal)
        self.pos_x_max_s.setRange(50, 100)
        self.pos_x_max_s.setValue(85)
        self.pos_x_max_lbl = QLabel("85%")
        pos_layout.addWidget(self.pos_x_max_s)
        pos_layout.addWidget(self.pos_x_max_lbl)
        layout.addLayout(pos_layout)

        pos_y_layout = QHBoxLayout()
        pos_y_layout.addWidget(QLabel("Y范围："))
        self.pos_y_min_s = QSlider(Qt.Horizontal)
        self.pos_y_min_s.setRange(0, 50)
        self.pos_y_min_s.setValue(5)
        self.pos_y_lbl = QLabel("5%")
        pos_y_layout.addWidget(self.pos_y_min_s)
        pos_y_layout.addWidget(self.pos_y_lbl)
        pos_y_layout.addWidget(QLabel("~"))
        self.pos_y_max_s = QSlider(Qt.Horizontal)
        self.pos_y_max_s.setRange(50, 100)
        self.pos_y_max_s.setValue(75)
        self.pos_y_max_lbl = QLabel("75%")
        pos_y_layout.addWidget(self.pos_y_max_s)
        pos_y_layout.addWidget(self.pos_y_max_lbl)
        layout.addLayout(pos_y_layout)

        al = QHBoxLayout()
        al.addWidget(QLabel("角度："))
        self.angle_min = QSpinBox()
        self.angle_min.setRange(-90, 90)
        self.angle_min.setValue(-10)
        al.addWidget(self.angle_min)
        al.addWidget(QLabel("~"))
        self.angle_max = QSpinBox()
        self.angle_max.setRange(-90, 90)
        self.angle_max.setValue(10)
        al.addWidget(self.angle_max)
        al.addStretch()
        layout.addLayout(al)

        bl = QHBoxLayout()
        self.start_btn = QPushButton("开始")
        self.start_btn.setStyleSheet("background:#4CAF50;color:white;padding:10px;font-size:14px;")
        bl.addWidget(self.start_btn)
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setStyleSheet("background:#f44336;color:white;padding:10px;font-size:14px;")
        bl.addWidget(self.stop_btn)
        layout.addLayout(bl)

        self.status = QLabel("状态：就绪")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setMaximumWidth(450)
        layout.addWidget(self.status)
        layout.addWidget(QLabel("按 Esc 退出程序"))

        scroll.setWidget(content)
        outer_layout.addWidget(scroll)

        screen = QApplication.primaryScreen().geometry()
        screen_h = screen.height()
        self.setFixedSize(500, 700) if screen_h <= 1080 else self.setFixedSize(520, 900)
    
    def _load_settings(self, settings) -> None:
        """从配置管理器加载设置到 UI 控件"""
        try:
            self.current_color = QColor(settings.get_setting('text_color', '#fffeef'))
            self.current_stroke_color = QColor(settings.get_setting('stroke_color', '#d8a523'))
            self.current_glow_color = QColor(settings.get_setting('glow_color', '#d8a523'))
            self.glow_check.setChecked(settings.get_setting('glow_enabled', True))
            self.glow_size_slider.setValue(settings.get_setting('glow_size', 4))
            self.glow_alpha_slider.setValue(settings.get_setting('glow_alpha', 82))
            self.loop_check.setChecked(settings.get_setting('loop', True))
            self.perspective_check.setChecked(settings.get_setting('perspective_enabled', True))
            self.persp_x_slider.setValue(settings.get_setting('persp_x_strength', 5))
            self.persp_y_slider.setValue(settings.get_setting('persp_y_strength', 30))
            self.persp_comp_slider.setValue(settings.get_setting('persp_compensation', 3))
            self.trans_check.setChecked(settings.get_setting('trans_only', False))
            self.netease_adapter_check.setChecked(settings.get_setting('netease_adapter_enabled', True))
            self.filter_pure_music_check.setChecked(settings.get_setting('filter_pure_music', True))
            self.inst_patterns = settings.get_setting('inst_patterns', None)
            idx = self.mode_combo.findData(settings.get_setting('mode', 'chinese'))
            if idx >= 0:
                self.mode_combo.setCurrentIndex(idx)
            self.font_combo.setCurrentText(settings.get_setting('font_family', 'Microsoft YaHei'))
            self.font_size.setValue(settings.get_setting('font_size', 28))
            self.stroke_spin.setValue(settings.get_setting('stroke_width', 0.5))
            self.spacing_spin.setValue(settings.get_setting('spacing', 5.0))
            self.shake_intensity_slider.setValue(settings.get_setting('shake_intensity', 2))
            self.shake_speed_slider.setValue(settings.get_setting('shake_speed', 143))
            self.fade_speed_slider.setValue(settings.get_setting('fade_speed', 12))
            self.rise_speed_slider.setValue(settings.get_setting('rise_speed', 1))
            self.margin_spin.setValue(settings.get_setting('margin_time', 4000))
            self.max_interval_spin.setValue(settings.get_setting('max_interval', 16000))
            self.max_duration_spin.setValue(settings.get_setting('max_duration', 5000))
            self.angle_min.setValue(settings.get_setting('angle_min', -10))
            self.angle_max.setValue(settings.get_setting('angle_max', 10))
            self.pos_x_min_s.setValue(settings.get_setting('pos_x_min', 5))
            self.pos_x_max_s.setValue(settings.get_setting('pos_x_max', 85))
            self.pos_y_min_s.setValue(settings.get_setting('pos_y_min', 5))
            self.pos_y_max_s.setValue(settings.get_setting('pos_y_max', 75))
            source_name = settings.get_setting('source', '网易云')
            idx = self.source_combo.findText(source_name)
            if idx >= 0:
                self.source_combo.setCurrentIndex(idx)
            delay_idx = settings.get_setting('delay', 0)
            self.delay_combo.setCurrentIndex(delay_idx)
            self.color_btn.setStyleSheet(f"background-color:{self.current_color.name()};")
            self.stroke_btn.setStyleSheet(f"background-color:{self.current_stroke_color.name()};")
            self.glow_color_btn.setStyleSheet(f"background-color:{self.current_glow_color.name()};")
        except Exception:
            pass
    
    def _connect_controller_signals(self) -> None:
        """连接 Controller 的输出信号到 UI 更新方法"""
        self.controller.status_changed.connect(self.status.setText)
        self.controller.lyric_fetched.connect(self._on_lyric_fetched)
        self.controller.lyric_fetch_failed.connect(
            lambda msg: self.status.setText(f"状态：{msg}")
        )
        self.controller.player_list_updated.connect(self._on_player_list_updated)
        self.controller.preset_list_updated.connect(self._on_preset_list_updated)
        self.controller.song_updated.connect(self._on_song_updated)
        self.controller.playback_status_updated.connect(self._on_playback_status_updated)
    
    def _connect_ui_events(self) -> None:
        """连接 UI 控件事件到 Controller 方法"""
        # 播放器切换
        self.player_combo.currentTextChanged.connect(self.controller.switch_player)
        
        # 预设加载
        self.preset_combo.currentTextChanged.connect(self._on_load_preset)
        
        # 开始/停止
        self.start_btn.clicked.connect(self._on_start)
        self.stop_btn.clicked.connect(self._on_stop)
        
        # 透视开关 → 通过 Controller 控制歌词窗口
        self.perspective_check.stateChanged.connect(
            lambda state: self.controller.set_perspective_enabled(state == Qt.Checked)
        )
        
        # 透视X
        self.persp_x_slider.valueChanged.connect(
            lambda v: (self.controller.set_perspective_x(v / 1000000),
                       self.persp_x_label.setText(f"{v / 1000000:.6f}"))
        )
        
        # 透视Y
        self.persp_y_slider.valueChanged.connect(
            lambda v: (self.controller.set_perspective_y(v / 100000),
                       self.persp_y_label.setText(f"{v / 100000:.5f}"))
        )
        
        # 补偿
        self.persp_comp_slider.valueChanged.connect(
            lambda v: (self.controller.set_perspective_compensation(v / 100),
                       self.persp_comp_label.setText(f"{v / 100:.2f}"))
        )
        
        # 循环
        self.loop_check.stateChanged.connect(
            lambda state: self.controller.set_loop(state == Qt.Checked)
        )
        
        # 网易云适配方式 → 通过 Controller 切换（取消勾选时弹窗提醒）
        self.netease_adapter_check.stateChanged.connect(self._on_netease_adapter_changed)
        
        # 起始位置范围 → 通过 Controller 控制歌词窗口
        self.pos_x_min_s.valueChanged.connect(
            lambda v: (self.controller.set_pos_x_min(v),
                       self.pos_x_lbl.setText(f"{v}%"))
        )
        self.pos_x_max_s.valueChanged.connect(
            lambda v: (self.controller.set_pos_x_max(v),
                       self.pos_x_max_lbl.setText(f"{v}%"))
        )
        self.pos_y_min_s.valueChanged.connect(
            lambda v: (self.controller.set_pos_y_min(v),
                       self.pos_y_lbl.setText(f"{v}%"))
        )
        self.pos_y_max_s.valueChanged.connect(
            lambda v: (self.controller.set_pos_y_max(v),
                       self.pos_y_max_lbl.setText(f"{v}%"))
        )
        
        # 光晕粗细
        self.glow_size_slider.valueChanged.connect(
            lambda v: self.glow_size_label.setText(str(v))
        )
        
        # 光晕透明度
        self.glow_alpha_slider.valueChanged.connect(
            lambda v: self.glow_alpha_label.setText(str(v))
        )
        
        # 颤强
        self.shake_intensity_slider.valueChanged.connect(
            lambda v: self.shake_intensity_label.setText(str(v))
        )
        
        # 颤速
        self.shake_speed_slider.valueChanged.connect(
            lambda v: self.shake_speed_label.setText(f"{v} ms")
        )
        
        # 淡出速度
        self.fade_speed_slider.valueChanged.connect(
            lambda v: self.fade_speed_label.setText(str(v))
        )
        
        # 上升速度
        self.rise_speed_slider.valueChanged.connect(
            lambda v: self.rise_speed_label.setText(str(v))
        )
        
        # 同步所有滑块标签（加载配置后标签可能未更新）
        self._sync_slider_labels()
    
    def _sync_slider_labels(self) -> None:
        """同步滑块数值标签与当前值一致"""
        self.glow_size_label.setText(str(self.glow_size_slider.value()))
        self.glow_alpha_label.setText(str(self.glow_alpha_slider.value()))
        self.shake_intensity_label.setText(str(self.shake_intensity_slider.value()))
        self.shake_speed_label.setText(f"{self.shake_speed_slider.value()} ms")
        self.fade_speed_label.setText(str(self.fade_speed_slider.value()))
        self.rise_speed_label.setText(str(self.rise_speed_slider.value()))
    
    def _refresh_player_list(self) -> None:
        """刷新播放器下拉列表"""
        self.player_combo.blockSignals(True)
        self.player_combo.clear()
        self.player_combo.addItems(self.controller.get_player_names())
        self.player_combo.blockSignals(False)
    
    def _refresh_preset_list(self) -> None:
        """刷新预设下拉列表"""
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItems(self.controller.get_preset_names())
        self.preset_combo.blockSignals(False)
    
    # ---- UI 事件处理（调用 Controller） ----
    
    def _on_fetch_lyric(self) -> None:
        """获取歌词按钮点击"""
        source = self.source_combo.currentText()
        trans_only = self.trans_check.isChecked()
        logger.info("用户点击获取歌词：来源=%s，仅翻译=%s", source, trans_only)

        # 纯音乐/伴奏过滤：命中则跳过获取，不显示歌词
        if self.filter_pure_music_check.isChecked():
            media = self.controller.get_current_media()
            if is_pure_music(media.song, media.artist, self.inst_patterns):
                logger.info("检测到纯音乐/伴奏：%s - %s，不显示歌词", media.song, media.artist)
                self._on_stop()
                self.status.setText("状态：纯音乐/伴奏，不显示歌词")
                return

        def manual_input():
            text, ok = QInputDialog.getText(
                self, "手动输入",
                "未能自动获取歌曲信息\n请输入 歌名 - 歌手：",
                text="歌名 - 歌手"
            )
            if ok and text.strip():
                parts = text.strip().split(' - ', 1)
                if len(parts) == 2:
                    return parts[0].strip(), parts[1].strip()
                return parts[0].strip(), ""
            return None
        
        source = self.source_combo.currentText()
        trans_only = self.trans_check.isChecked()
        self.controller.fetch_lyric(source, trans_only, manual_input)
    
    def _on_add_player(self) -> None:
        """添加播放器"""
        name, ok = QInputDialog.getText(self, "自定义播放器", "输入播放器名称：")
        if not ok or not name.strip():
            return
        name = name.strip()
        proc, ok2 = QInputDialog.getText(self, "进程名", "输入进程名（如 qqmusic.exe）：")
        if not ok2 or not proc.strip():
            return
        pattern, ok3 = QInputDialog.getText(
            self, "标题正则", "输入标题匹配正则：", text=r'^(.+?)\s*-\s*(.+)$')
        if ok3 and pattern.strip():
            logger.info("添加播放器：%s（进程 %s）", name, proc.strip())
            self.controller.add_player(name, proc.strip(), pattern.strip())
            self._refresh_player_list()
            self.player_combo.setCurrentText(name)
    
    def _on_delete_player(self) -> None:
        """删除播放器"""
        name = self.player_combo.currentText()
        if not name:
            return
        if QMessageBox.question(self, "删除播放器", f"确定删除「{name}」吗？") == QMessageBox.Yes:
            logger.info("删除播放器：%s", name)
            self.controller.delete_player(name)
            self._refresh_player_list()
    
    def _on_new_preset(self) -> None:
        """新建预设"""
        name, ok = QInputDialog.getText(self, "新建预设", "输入预设名称：")
        if ok and name.strip():
            name = name.strip()
            preset_data = {
                'text': self.current_color.name(),
                'stroke': self.current_stroke_color.name(),
                'glow': self.current_glow_color.name()
            }
            logger.info("新建预设：%s", name)
            self.controller.add_preset(name, preset_data)
            self._refresh_preset_list()
            self.preset_combo.setCurrentText(name)
    
    def _on_delete_preset(self) -> None:
        """删除预设"""
        name = self.preset_combo.currentText()
        if not name:
            return
        if QMessageBox.question(self, "删除预设", f"确定删除「{name}」吗？") == QMessageBox.Yes:
            logger.info("删除预设：%s", name)
            self.controller.delete_preset(name)
            self._refresh_preset_list()
    
    def _on_load_preset(self, name: str) -> None:
        """加载预设"""
        presets = self.controller.get_presets()
        if name in presets:
            c = presets[name]
            self.current_color = QColor(c['text'])
            self.current_stroke_color = QColor(c['stroke'])
            self.current_glow_color = QColor(c.get('glow', '#ffffff'))
            self.color_btn.setStyleSheet(f"background-color:{self.current_color.name()};")
            self.stroke_btn.setStyleSheet(f"background-color:{self.current_stroke_color.name()};")
            self.glow_color_btn.setStyleSheet(f"background-color:{self.current_glow_color.name()};")
    
    def _on_start(self) -> None:
        """开始播放"""
        text = self.text_input.toPlainText().strip()
        if not text:
            # 无歌词文本：当前有歌曲在播放则按纯音乐处理（状态栏提示），否则提示输入歌词
            media = self.controller.get_current_media()
            if media.has_track:
                logger.info("当前歌曲无歌词（%s - %s），按纯音乐处理", media.song, media.artist)
                self.status.setText("状态：纯音乐，无歌词显示")
                return
            logger.warning("用户点击开始，但未输入歌词")
            self.status.setText("状态：请先输入歌词！")
            return
        logger.info("用户点击开始播放：%d 字符，模式=%s",
                    len(text), self.mode_combo.currentData())
        
        font = QFont(self.font_combo.currentText(), self.font_size.value(), QFont.Bold)
        mode = self.mode_combo.currentData()
        delay = int(self.delay_combo.currentText().replace('s', ''))
        
        lyric_settings = LyricSettings(
            text=text,
            font=font,
            text_color=self.current_color,
            stroke_color=self.current_stroke_color,
            stroke_width=self.stroke_spin.value(),
            angle_min=self.angle_min.value(),
            angle_max=self.angle_max.value(),
            margin_time=self.margin_spin.value(),
            max_interval=self.max_interval_spin.value(),
            max_duration=self.max_duration_spin.value(),
            mode=mode,
            spacing=self.spacing_spin.value(),
            shake_intensity=self.shake_intensity_slider.value(),
            shake_speed=self.shake_speed_slider.value(),
            fade_speed=self.fade_speed_slider.value(),
            rise_speed=self.rise_speed_slider.value(),
            glow=self.glow_check.isChecked(),
            glow_color=self.current_glow_color,
            glow_size=self.glow_size_slider.value(),
            glow_alpha=self.glow_alpha_slider.value(),
            start_delay=delay,
            loop=self.loop_check.isChecked(),
            pos_x_min=self.pos_x_min_s.value(),
            pos_x_max=self.pos_x_max_s.value(),
            pos_y_min=self.pos_y_min_s.value(),
            pos_y_max=self.pos_y_max_s.value(),
        )
        self.controller.start_playback(lyric_settings)
    
    def _on_stop(self) -> None:
        """停止播放"""
        logger.info("用户点击停止播放")
        self.controller.stop_playback()
    
    def _on_pause(self) -> None:
        """暂停播放：定格当前画面，不销毁歌词窗口"""
        self.controller.pause_playback()
    
    def _on_resume(self) -> None:
        """恢复播放：从暂停位置继续"""
        self.controller.resume_playback()
    
    @qasync.asyncSlot()
    async def _on_song_updated(self) -> None:
        """切歌后自动重新播放"""
        logger.debug("自动播放触发，重新开始")
        source = self.source_combo.currentText()
        trans_only = self.trans_check.isChecked()
        # 纯音乐/伴奏过滤：命中则跳过获取，不显示歌词
        if self.filter_pure_music_check.isChecked():
            media = self.controller.get_current_media()
            if is_pure_music(media.song, media.artist, self.inst_patterns):
                logger.info("检测到纯音乐/伴奏：%s - %s，不显示歌词", media.song, media.artist)
                self._on_stop()
                self.status.setText("状态：纯音乐/伴奏，不显示歌词")
                return
        #ToDo:这里以后也应该是一个弹窗的
        def manual_input():
            logger.error("自动播放时未能获取歌曲信息")
            return None
        success = await self.controller.fetch_lyric(source, trans_only, manual_input)
        # 无论成功与否都先停止上一首歌的歌词显示
        self._on_stop()
        if success:
            # 新歌曲获取到歌词才自动播放
            self._on_start()
        else:
            # 新歌曲没有歌词（如纯音乐），停止显示，避免沿用上一首的歌词
            logger.info("新歌曲未获取到歌词（可能为纯音乐），不自动播放")
            self.status.setText("状态：当前歌曲无歌词，不自动播放")
    def _on_playback_status_updated(self, status: bool) -> None:
        """播放状态变化时自动暂停/恢复（不销毁歌词窗口）"""
        logger.debug(f"播放状态变化：{status}")
        if status:
            self._on_resume()
        else:
            self._on_pause()
    
    def _on_netease_adapter_changed(self, state) -> None:
        """网易云适配方式切换：取消勾选时弹窗提醒"""
        enabled = (state == Qt.Checked)
        if not enabled:
            QMessageBox.warning(
                self, "确定你在做什么",
                "如果您使用inflink-rs等第三方网易云插件不能正常运行时请取消勾选，否则如果能正常运行请保持默认设置"
            )
        self.controller.set_netease_adapter(enabled)
    # ---- Controller 信号处理 ----
    
    def _on_lyric_fetched(self, lyric: str, duration_ms: int, song: str, artist: str) -> None:
        """歌词获取成功"""
        logger.info("歌词已填充到输入框：%s - %s，时长 %dms", song, artist, duration_ms)
        self.text_input.setPlainText(lyric)
        self.controller.set_song_duration(duration_ms)
    
    def _on_player_list_updated(self, player_names: list) -> None:
        """播放器列表更新"""
        self._refresh_player_list()
    
    def _on_preset_list_updated(self, preset_names: list) -> None:
        """预设列表更新"""
        self._refresh_preset_list()
    
    # ---- 其他 UI 方法 ----
    
    def apply_zoom(self) -> None:
        """应用界面缩放"""
        scale = self.zoom_slider.value() / 100.0
        screen = QApplication.primaryScreen().geometry()
        base_h = 700 if screen.height() <= 1080 else 900
        self.setFixedSize(int(500 * scale), int(base_h * scale))
    
    def pick_glow_color(self) -> None:
        """选择发光颜色"""
        c = QColorDialog.getColor(self.current_glow_color, self, "发光颜色")
        if c.isValid():
            self.current_glow_color = c
            self.glow_color_btn.setStyleSheet(f"background-color:{c.name()};")
    
    def pick_color(self) -> None:
        """选择文字颜色"""
        c = QColorDialog.getColor(self.current_color, self, "文字颜色")
        if c.isValid():
            self.current_color = c
            self.color_btn.setStyleSheet(f"background-color:{c.name()};")
    
    def pick_stroke(self) -> None:
        """选择描边颜色"""
        c = QColorDialog.getColor(self.current_stroke_color, self, "阴影/描边颜色")
        if c.isValid():
            self.current_stroke_color = c
            self.stroke_btn.setStyleSheet(f"background-color:{c.name()};")
    
    def auto_select_font(self) -> None:
        """自动选择推荐字体"""
        from PyQt5.QtGui import QFontDatabase
        recommended = ["Mikodacs", "思源黑体 Bold"]
        available = [f for f in recommended if f in QFontDatabase().families()]
        if not available:
            self.status.setText("状态：未找到推荐字体")
            return
        current = self.font_combo.currentText()
        try:
            idx = available.index(current)
            next_idx = (idx + 1) % len(available)
        except ValueError:
            next_idx = 0
        chosen = available[next_idx]
        self.font_combo.setCurrentText(chosen)
        self.status.setText(f"状态：已切换字体 {chosen}")
    
    def _collect_ui_settings(self) -> dict:
        """从 UI 控件收集当前设置（供保存配置使用）"""
        return {
            'text_color': self.current_color.name(),
            'stroke_color': self.current_stroke_color.name(),
            'glow_color': self.current_glow_color.name(),
            'glow_enabled': self.glow_check.isChecked(),
            'glow_size': self.glow_size_slider.value(),
            'glow_alpha': self.glow_alpha_slider.value(),
            'loop': self.loop_check.isChecked(),
            'trans_only': self.trans_check.isChecked(),
            'netease_adapter_enabled': self.netease_adapter_check.isChecked(),
            'filter_pure_music': self.filter_pure_music_check.isChecked(),
            'mode': self.mode_combo.currentData(),
            'font_family': self.font_combo.currentText(),
            'font_size': self.font_size.value(),
            'stroke_width': self.stroke_spin.value(),
            'spacing': self.spacing_spin.value(),
            'shake_intensity': self.shake_intensity_slider.value(),
            'shake_speed': self.shake_speed_slider.value(),
            'fade_speed': self.fade_speed_slider.value(),
            'rise_speed': self.rise_speed_slider.value(),
            'margin_time': self.margin_spin.value(),
            'max_interval': self.max_interval_spin.value(),
            'max_duration': self.max_duration_spin.value(),
            'angle_min': self.angle_min.value(),
            'angle_max': self.angle_max.value(),
            'pos_x_min': self.pos_x_min_s.value(),
            'pos_x_max': self.pos_x_max_s.value(),
            'pos_y_min': self.pos_y_min_s.value(),
            'pos_y_max': self.pos_y_max_s.value(),
            'player': self.player_combo.currentText(),
            'source': self.source_combo.currentText(),
            'delay': self.delay_combo.currentIndex(),
            'perspective_enabled': self.perspective_check.isChecked(),
            'persp_x_strength': self.persp_x_slider.value(),
            'persp_y_strength': self.persp_y_slider.value(),
            'persp_compensation': self.persp_comp_slider.value(),
        }
    
    def closeEvent(self, event) -> None:
        """窗口关闭时保存配置"""
        # 将 UI 设置同步到 SettingsManager
        settings = self.controller.get_settings()
        settings.update_settings(self._collect_ui_settings())
        # 保存并关闭
        logger.info("关闭控制面板，保存配置")
        self.controller.save_and_close()
        event.accept()