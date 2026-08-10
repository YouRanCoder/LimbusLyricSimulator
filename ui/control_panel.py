from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QLabel, QSlider, QColorDialog, QSpinBox,
    QFontComboBox, QComboBox, QCheckBox, QInputDialog, QMessageBox,
    QDoubleSpinBox, QScrollArea,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont
from config.manage import load_all_config, save_all_config, DEFAULT_PLAYERS
from ui.lyric_window import LyricWindow
from core.fetcher import create_fetcher
from core.search_engine import LyricSearchEngine
import asyncio
import logging


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
class ControlPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("歌词字幕器 - 控制面板")
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        self.current_color = QColor("#fffeef"); self.current_stroke_color = QColor("#d8a523")
        self.current_glow_color = QColor("#d8a523")
        all_data = load_all_config()
        self.presets = all_data['presets']; self.players = all_data.get('players', dict(DEFAULT_PLAYERS))
        settings = all_data['settings']
        self.lyric_window = LyricWindow(); self.lyric_window.show()
        outer_layout = QVBoxLayout(self); outer_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content); layout.setSpacing(6)

        # 缩放
        zoom_layout = QHBoxLayout()
        zoom_layout.addWidget(QLabel("界面缩放："))
        self.zoom_slider = QSlider(Qt.Horizontal); self.zoom_slider.setRange(70, 150)
        self.zoom_slider.setValue(100); self.zoom_label = QLabel("100%")
        self.zoom_slider.valueChanged.connect(lambda v: self.zoom_label.setText(f"{v}%"))
        self.zoom_slider.sliderReleased.connect(self.apply_zoom)
        zoom_layout.addWidget(self.zoom_slider); zoom_layout.addWidget(self.zoom_label)
        layout.addLayout(zoom_layout)

        # 播放器选择
        player_layout = QHBoxLayout()
        player_layout.addWidget(QLabel("播放器："))
        self.player_combo = QComboBox(); self.refresh_player_list()
        player_layout.addWidget(self.player_combo)
        btn_add_p = QPushButton("+"); btn_add_p.setMaximumWidth(30)
        btn_add_p.clicked.connect(self.add_custom_player); player_layout.addWidget(btn_add_p)
        btn_del_p = QPushButton("-"); btn_del_p.setMaximumWidth(30)
        btn_del_p.clicked.connect(self.delete_player); player_layout.addWidget(btn_del_p)
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

        layout.addWidget(QLabel("歌词（粘贴LRC格式）："))
        self.text_input = QTextEdit(); self.text_input.setMinimumHeight(120)
        layout.addWidget(self.text_input)

        fetch_btn = QPushButton("🎵 从播放器获取当前歌词")
        fetch_btn.clicked.connect(self.fetch_lyric); layout.addWidget(fetch_btn)
        # 3D透视开关
        self.perspective_check = QCheckBox("3D透视(测试)")
        self.perspective_check.setChecked(True)
        self.perspective_check.stateChanged.connect(
            lambda state: setattr(self.lyric_window, 'perspective_enabled', state == Qt.Checked))
        layout.addWidget(self.perspective_check)

        # 透视X
        px_layout = QHBoxLayout()
        px_layout.addWidget(QLabel("透视X："))
        self.persp_x_slider = QSlider(Qt.Horizontal)
        self.persp_x_slider.setRange(0, 100)
        self.persp_x_slider.setValue(5)
        self.persp_x_label = QLabel("0.00005")
        self.persp_x_slider.valueChanged.connect(
            lambda v: (setattr(self.lyric_window, 'persp_x_strength', v/1000000),
                       self.persp_x_label.setText(f"{v/1000000:.6f}")))
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
        self.persp_y_slider.valueChanged.connect(
            lambda v: (setattr(self.lyric_window, 'persp_y_strength', v/100000),
                       self.persp_y_label.setText(f"{v/100000:.5f}")))
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
        self.persp_comp_slider.valueChanged.connect(
            lambda v: (setattr(self.lyric_window, 'persp_compensation', v/100),
                       self.persp_comp_label.setText(f"{v/100:.2f}")))
        comp_layout.addWidget(self.persp_comp_slider)
        comp_layout.addWidget(self.persp_comp_label)
        layout.addLayout(comp_layout)
        # 选项行
        options_row = QHBoxLayout()
        self.trans_check = QCheckBox("仅获取翻译歌词"); self.trans_check.setChecked(False)
        options_row.addWidget(self.trans_check)
        self.loop_check = QCheckBox("单曲循环"); self.loop_check.setChecked(True)
        self.loop_check.stateChanged.connect(lambda state: setattr(self.lyric_window, 'loop', state == Qt.Checked))
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
        self.preset_combo = QComboBox(); self.preset_combo.setMinimumWidth(80)
        self.refresh_preset_list(); self.preset_combo.currentTextChanged.connect(self.load_preset)
        top_row.addWidget(self.preset_combo)
        btn_new = QPushButton("+"); btn_new.setMaximumWidth(30); btn_new.clicked.connect(self.new_preset)
        top_row.addWidget(btn_new)
        btn_del = QPushButton("-"); btn_del.setMaximumWidth(30); btn_del.clicked.connect(self.delete_preset)
        top_row.addWidget(btn_del); top_row.addStretch()
        top_row.addWidget(QLabel("模式："))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("中文", "chinese"); self.mode_combo.addItem("英文", "english")
        self.mode_combo.setMaximumWidth(80); top_row.addWidget(self.mode_combo)
        layout.addLayout(top_row)

        # 发光
        glow_layout = QHBoxLayout()
        self.glow_check = QCheckBox("发光"); self.glow_check.setChecked(True)
        glow_layout.addWidget(self.glow_check)
        glow_layout.addWidget(QLabel("光色："))
        self.glow_color_btn = QPushButton(); self.glow_color_btn.setFixedSize(30, 30)
        self.glow_color_btn.setStyleSheet(f"background-color:{self.current_glow_color.name()};")
        self.glow_color_btn.clicked.connect(self.pick_glow_color)
        glow_layout.addWidget(self.glow_color_btn); glow_layout.addStretch()
        layout.addLayout(glow_layout)

        gsl = QHBoxLayout(); gsl.addWidget(QLabel("光晕粗细："))
        self.glow_size_slider = QSlider(Qt.Horizontal); self.glow_size_slider.setRange(4, 30)
        self.glow_size_slider.setValue(4); self.glow_size_label = QLabel("4")
        self.glow_size_slider.valueChanged.connect(lambda v: self.glow_size_label.setText(str(v)))
        gsl.addWidget(self.glow_size_slider); gsl.addWidget(self.glow_size_label)
        layout.addLayout(gsl)

        gal = QHBoxLayout(); gal.addWidget(QLabel("光晕透明度："))
        self.glow_alpha_slider = QSlider(Qt.Horizontal); self.glow_alpha_slider.setRange(10, 120)
        self.glow_alpha_slider.setValue(82); self.glow_alpha_label = QLabel("82")
        self.glow_alpha_slider.valueChanged.connect(lambda v: self.glow_alpha_label.setText(str(v)))
        gal.addWidget(self.glow_alpha_slider); gal.addWidget(self.glow_alpha_label)
        layout.addLayout(gal)

        fl = QHBoxLayout(); fl.addWidget(QLabel("字体："))
        self.font_combo = QFontComboBox(); self.font_combo.setCurrentFont(QFont("Microsoft YaHei"))
        fl.addWidget(self.font_combo); fl.addWidget(QLabel("大小："))
        self.font_size = QSpinBox(); self.font_size.setRange(10, 100); self.font_size.setValue(28)
        fl.addWidget(self.font_size); layout.addLayout(fl)
                # 推荐字体按钮
        fl_auto = QHBoxLayout()
        btn_auto_font = QPushButton("推荐字体")
        btn_auto_font.clicked.connect(self.auto_select_font)
        fl_auto.addWidget(btn_auto_font)
        fl_auto.addStretch()
        layout.addLayout(fl_auto)

        cl = QHBoxLayout(); cl.addWidget(QLabel("文字："))
        self.color_btn = QPushButton(); self.color_btn.setFixedSize(30, 30)
        self.color_btn.setStyleSheet(f"background-color:{self.current_color.name()};")
        self.color_btn.clicked.connect(self.pick_color); cl.addWidget(self.color_btn)
        cl.addWidget(QLabel("阴影："))
        self.stroke_btn = QPushButton(); self.stroke_btn.setFixedSize(30, 30)
        self.stroke_btn.setStyleSheet(f"background-color:{self.current_stroke_color.name()};")
        self.stroke_btn.clicked.connect(self.pick_stroke); cl.addWidget(self.stroke_btn)
        cl.addStretch(); layout.addLayout(cl)

        swl = QHBoxLayout(); swl.addWidget(QLabel("描边粗细："))
        self.stroke_spin = QDoubleSpinBox(); self.stroke_spin.setRange(0.0, 10.0)
        self.stroke_spin.setSingleStep(0.1); self.stroke_spin.setDecimals(1); self.stroke_spin.setValue(0.5)
        swl.addWidget(self.stroke_spin); swl.addWidget(QLabel("px")); layout.addLayout(swl)

        ssl = QHBoxLayout(); ssl.addWidget(QLabel("字间距："))
        self.spacing_spin = QDoubleSpinBox(); self.spacing_spin.setRange(-10.0, 30.0)
        self.spacing_spin.setSingleStep(0.5); self.spacing_spin.setDecimals(1); self.spacing_spin.setValue(5.0)
        ssl.addWidget(self.spacing_spin); ssl.addWidget(QLabel("px")); layout.addLayout(ssl)

        shl = QHBoxLayout(); shl.addWidget(QLabel("颤强："))
        self.shake_intensity_slider = QSlider(Qt.Horizontal); self.shake_intensity_slider.setRange(0, 10)
        self.shake_intensity_slider.setValue(2); self.shake_intensity_label = QLabel("2")
        self.shake_intensity_slider.valueChanged.connect(lambda v: self.shake_intensity_label.setText(str(v)))
        shl.addWidget(self.shake_intensity_slider); shl.addWidget(self.shake_intensity_label)
        layout.addLayout(shl)

        shvl = QHBoxLayout(); shvl.addWidget(QLabel("颤速："))
        self.shake_speed_slider = QSlider(Qt.Horizontal); self.shake_speed_slider.setRange(10, 200)
        self.shake_speed_slider.setValue(143); self.shake_speed_label = QLabel("143 ms")
        self.shake_speed_slider.valueChanged.connect(lambda v: self.shake_speed_label.setText(f"{v} ms"))
        shvl.addWidget(self.shake_speed_slider); shvl.addWidget(self.shake_speed_label)
        layout.addLayout(shvl)

        fsl = QHBoxLayout(); fsl.addWidget(QLabel("淡出速度："))
        self.fade_speed_slider = QSlider(Qt.Horizontal); self.fade_speed_slider.setRange(1, 15)
        self.fade_speed_slider.setValue(12); self.fade_speed_label = QLabel("12")
        self.fade_speed_slider.valueChanged.connect(lambda v: self.fade_speed_label.setText(str(v)))
        fsl.addWidget(self.fade_speed_slider); fsl.addWidget(self.fade_speed_label)
        layout.addLayout(fsl)

        rsl = QHBoxLayout(); rsl.addWidget(QLabel("上升速度："))
        self.rise_speed_slider = QSlider(Qt.Horizontal); self.rise_speed_slider.setRange(0, 5)
        self.rise_speed_slider.setValue(1); self.rise_speed_label = QLabel("1")
        self.rise_speed_slider.valueChanged.connect(lambda v: self.rise_speed_label.setText(str(v)))
        rsl.addWidget(self.rise_speed_slider); rsl.addWidget(self.rise_speed_label)
        layout.addLayout(rsl)

        ml = QHBoxLayout(); ml.addWidget(QLabel("留白："))
        self.margin_spin = QSpinBox(); self.margin_spin.setRange(0, 5000)
        self.margin_spin.setValue(4000); self.margin_spin.setSingleStep(100)
        ml.addWidget(self.margin_spin); ml.addWidget(QLabel("ms")); ml.addStretch()
        layout.addLayout(ml)

        mil = QHBoxLayout(); mil.addWidget(QLabel("长间隔阈值："))
        self.max_interval_spin = QSpinBox(); self.max_interval_spin.setRange(1000, 30000)
        self.max_interval_spin.setValue(16000); self.max_interval_spin.setSingleStep(1000)
        mil.addWidget(self.max_interval_spin); mil.addWidget(QLabel("ms")); mil.addStretch()
        layout.addLayout(mil)

        mdl = QHBoxLayout(); mdl.addWidget(QLabel("长间隔时长："))
        self.max_duration_spin = QSpinBox(); self.max_duration_spin.setRange(500, 10000)
        self.max_duration_spin.setValue(5000); self.max_duration_spin.setSingleStep(500)
        mdl.addWidget(self.max_duration_spin); mdl.addWidget(QLabel("ms")); mdl.addStretch()
        layout.addLayout(mdl)

        al = QHBoxLayout(); al.addWidget(QLabel("角度："))
        self.angle_min = QSpinBox(); self.angle_min.setRange(-90, 90); self.angle_min.setValue(-10)
        al.addWidget(self.angle_min); al.addWidget(QLabel("~"))
        self.angle_max = QSpinBox(); self.angle_max.setRange(-90, 90); self.angle_max.setValue(10)
        al.addWidget(self.angle_max); al.addStretch(); layout.addLayout(al)

        bl = QHBoxLayout()
        self.start_btn = QPushButton("开始"); self.start_btn.clicked.connect(self.start)
        self.start_btn.setStyleSheet("background:#4CAF50;color:white;padding:10px;font-size:14px;")
        bl.addWidget(self.start_btn)
        self.stop_btn = QPushButton("停止"); self.stop_btn.clicked.connect(self.stop)
        self.stop_btn.setStyleSheet("background:#f44336;color:white;padding:10px;font-size:14px;")
        bl.addWidget(self.stop_btn); layout.addLayout(bl)

        self.status = QLabel("状态：就绪"); self.status.setAlignment(Qt.AlignCenter)
        self.status.setMaximumWidth(450)
        layout.addWidget(self.status)
        layout.addWidget(QLabel("按 Esc 退出程序"))

        scroll.setWidget(content); outer_layout.addWidget(scroll)

        screen = QApplication.primaryScreen().geometry()
        screen_h = screen.height()
        self.setFixedSize(500, 700) if screen_h <= 1080 else self.setFixedSize(520, 900)

        # 加载设置
        if settings:
            try:
                self.current_color = QColor(settings.get('text_color', '#fffeef'))
                self.current_stroke_color = QColor(settings.get('stroke_color', '#d8a523'))
                self.current_glow_color = QColor(settings.get('glow_color', '#d8a523'))
                self.glow_check.setChecked(settings.get('glow_enabled', True))
                self.glow_size_slider.setValue(settings.get('glow_size', 4))
                self.glow_alpha_slider.setValue(settings.get('glow_alpha', 82))
                self.loop_check.setChecked(settings.get('loop', True))
                self.perspective_check.setChecked(settings.get('perspective_enabled', True))
                self.persp_x_slider.setValue(settings.get('persp_x_strength', 5))
                self.persp_y_slider.setValue(settings.get('persp_y_strength', 30))
                self.persp_comp_slider.setValue(settings.get('persp_compensation', 3))
                self.trans_check.setChecked(settings.get('trans_only', False))
                idx = self.mode_combo.findData(settings.get('mode', 'chinese'))
                if idx >= 0: self.mode_combo.setCurrentIndex(idx)
                self.font_combo.setCurrentFont(QFont(settings.get('font_family', 'Microsoft YaHei')))
                self.font_size.setValue(settings.get('font_size', 28))
                self.stroke_spin.setValue(settings.get('stroke_width', 0.5))
                self.spacing_spin.setValue(settings.get('spacing', 5.0))
                self.shake_intensity_slider.setValue(settings.get('shake_intensity', 2))
                self.shake_speed_slider.setValue(settings.get('shake_speed', 143))
                self.fade_speed_slider.setValue(settings.get('fade_speed', 12))
                self.rise_speed_slider.setValue(settings.get('rise_speed', 1))
                self.margin_spin.setValue(settings.get('margin_time', 4000))
                self.max_interval_spin.setValue(settings.get('max_interval', 16000))
                self.max_duration_spin.setValue(settings.get('max_duration', 5000))
                self.angle_min.setValue(settings.get('angle_min', -10))
                self.angle_max.setValue(settings.get('angle_max', 10))
                player_name = settings.get('player', '网易云音乐')
                idx = self.player_combo.findText(player_name)
                if idx >= 0: self.player_combo.setCurrentIndex(idx)
                source_name = settings.get('source', '网易云')
                idx = self.source_combo.findText(source_name)
                if idx >= 0: self.source_combo.setCurrentIndex(idx)
                delay_idx = settings.get('delay', 0)
                self.delay_combo.setCurrentIndex(delay_idx)
                self.color_btn.setStyleSheet(f"background-color:{self.current_color.name()};")
                self.stroke_btn.setStyleSheet(f"background-color:{self.current_stroke_color.name()};")
                self.glow_color_btn.setStyleSheet(f"background-color:{self.current_glow_color.name()};")
            except: pass
        # 通过工厂创建当前播放器对应的 Fetcher（UI 不关心具体实现）
        self.fetcher = create_fetcher(
            player_name=self.player_combo.currentText(),
            callback=self.song_changed,
            players=self.players,
        )
        # 播放器下拉框变化时切换 Fetcher
        self.player_combo.currentTextChanged.connect(self.on_player_changed)
        # 必须等主事件循环运行后再启动监听，
        # 用 asyncio.run() 会创建一次性临时循环，事件监听会立即失效
        QTimer.singleShot(0, self.fetcher.start)
    def song_changed(self, song, artist):
        self.fetch_lyric()
        # TODO: 后续接入播放进度同步，避免切歌后整首重播
        self.stop()
        self.start()
    def on_player_changed(self, player_name):
        """切换播放器时重建 Fetcher。"""
        if not hasattr(self, "fetcher"):
            return
        self.fetcher.stop()
        self.fetcher = create_fetcher(
            player_name=player_name,
            callback=self.song_changed,
            players=self.players,
        )
        QTimer.singleShot(0, self.fetcher.start)
        self.status.setText(f"状态：已切换到播放器 {player_name}")
    def refresh_player_list(self):
        self.player_combo.blockSignals(True); self.player_combo.clear()
        self.player_combo.addItems(list(self.players.keys()))
        self.player_combo.blockSignals(False)

    def add_custom_player(self):
        name, ok = QInputDialog.getText(self, "自定义播放器", "输入播放器名称：")
        if ok and name.strip():
            name = name.strip()
            if name in self.players: QMessageBox.warning(self, "重复", "该播放器已存在！"); return
            proc, ok2 = QInputDialog.getText(self, "进程名", "输入进程名（如 qqmusic.exe）：")
            if ok2 and proc.strip():
                pattern, ok3 = QInputDialog.getText(
                    self, "标题正则", "输入标题匹配正则：", text=r'^(.+?)\s*-\s*(.+)$')
                if ok3 and pattern.strip():
                    self.players[name] = {"process": proc.strip(), "pattern": pattern.strip()}
                    self.refresh_player_list(); self.player_combo.setCurrentText(name)
                    self.status.setText(f"状态：已添加播放器 {name}")

    def delete_player(self):
        name = self.player_combo.currentText()
        if not name: return
        if len(self.players) <= 1: QMessageBox.warning(self, "不能删除", "至少保留一个播放器！"); return
        if QMessageBox.question(self, "删除播放器", f"确定删除「{name}」吗？") == QMessageBox.Yes:
            del self.players[name]; self.refresh_player_list()
            self.status.setText(f"状态：已删除播放器 {name}")

    def apply_zoom(self):
        scale = self.zoom_slider.value() / 100.0
        screen = QApplication.primaryScreen().geometry()
        base_h = 700 if screen.height() <= 1080 else 900
        self.setFixedSize(int(500 * scale), int(base_h * scale))

    def fetch_lyric(self):
        """
        获取当前播放的歌词,并且显示在歌词窗口中
        """
        self.status.setText("状态：正在获取当前播放...")
        QApplication.processEvents()
        info = self.fetcher.get_current_media()
        song, artist = info.song, info.artist
        if not info.has_track:
            text, ok = QInputDialog.getText(
                self,
                "手动输入",
                "未能自动获取歌曲信息\n请输入 歌名 - 歌手：",
                text="歌名 - 歌手"
            )
            if ok and text.strip():
                parts = text.strip().split(' - ', 1)
                if len(parts) == 2:
                    song, artist = parts[0].strip(), parts[1].strip()
                else:
                    song = parts[0].strip()
                    artist = ""
            else:
                self.status.setText("状态：已取消")
                return

        source = self.source_combo.currentText()
        trans_only = self.trans_check.isChecked()
        self.status.setText(f"状态：从{source}搜索「{song}」...")
        QApplication.processEvents()

        lyric, duration = LyricSearchEngine.search(song, artist, source, trans_only)
        if lyric:
            self.text_input.setPlainText(lyric)
            # 优先使用播放器上报的真实时长（秒），否则用搜索接口返回的时长
            self.lyric_window.song_duration = info.duration_ms if info.duration > 0 else duration
            self.status.setText(f"状态：已获取「{song}」的歌词")
        else:
            self.status.setText("状态：未找到歌词，请尝试换源")
    def refresh_preset_list(self):
        self.preset_combo.blockSignals(True); self.preset_combo.clear()
        self.preset_combo.addItems(list(self.presets.keys()))
        self.preset_combo.blockSignals(False)

    def new_preset(self):
        name, ok = QInputDialog.getText(self, "新建预设", "输入预设名称：")
        if ok and name.strip():
            name = name.strip()
            if name in self.presets: QMessageBox.warning(self, "重复", "该预设名称已存在！"); return
            self.presets[name] = {'text': self.current_color.name(), 'stroke': self.current_stroke_color.name(), 'glow': self.current_glow_color.name()}
            self.refresh_preset_list(); self.preset_combo.setCurrentText(name)
            self.status.setText(f"状态：已创建预设 {name}")

    def delete_preset(self):
        name = self.preset_combo.currentText()
        if not name: return
        if len(self.presets) <= 1: QMessageBox.warning(self, "不能删除", "至少保留一个预设！"); return
        if QMessageBox.question(self, "删除预设", f"确定删除「{name}」吗？") == QMessageBox.Yes:
            del self.presets[name]; self.refresh_preset_list()
            self.status.setText(f"状态：已删除预设 {name}")

    def pick_glow_color(self):
        c = QColorDialog.getColor(self.current_glow_color, self, "发光颜色")
        if c.isValid(): self.current_glow_color = c; self.glow_color_btn.setStyleSheet(f"background-color:{c.name()};")

    def load_preset(self, name):
        if name in self.presets:
            c = self.presets[name]
            self.current_color = QColor(c['text']); self.current_stroke_color = QColor(c['stroke'])
            self.current_glow_color = QColor(c.get('glow', '#ffffff'))
            self.color_btn.setStyleSheet(f"background-color:{self.current_color.name()};")
            self.stroke_btn.setStyleSheet(f"background-color:{self.current_stroke_color.name()};")
            self.glow_color_btn.setStyleSheet(f"background-color:{self.current_glow_color.name()};")
            self.status.setText(f"状态：已加载 {name}")
    def auto_select_font(self):
        from PyQt5.QtGui import QFontDatabase
        recommended = ["Mikodacs", "思源黑体 Bold"]
        available = [f for f in recommended if f in QFontDatabase().families()]
        if not available:
            self.status.setText("状态：未找到推荐字体")
            return
        current = self.font_combo.currentFont().family()
        # 找当前字体在列表里的位置，选下一个
        try:
            idx = available.index(current)
            next_idx = (idx + 1) % len(available)
        except ValueError:
            next_idx = 0
        chosen = available[next_idx]
        self.font_combo.setCurrentFont(QFont(chosen))
        self.status.setText(f"状态：已切换字体 {chosen}")
    def pick_color(self):
        c = QColorDialog.getColor(self.current_color, self, "文字颜色")
        if c.isValid(): self.current_color = c; self.color_btn.setStyleSheet(f"background-color:{c.name()};")

    def pick_stroke(self):
        c = QColorDialog.getColor(self.current_stroke_color, self, "阴影/描边颜色")
        if c.isValid(): self.current_stroke_color = c; self.stroke_btn.setStyleSheet(f"background-color:{c.name()};")

    def start(self):
        text = self.text_input.toPlainText().strip()
        if not text: self.status.setText("状态：请先输入歌词！"); return
        font = QFont(self.font_combo.currentFont().family(), self.font_size.value(), QFont.Bold)
        mode = self.mode_combo.currentData()
        self.lyric_window.loop = self.loop_check.isChecked()
        delay = int(self.delay_combo.currentText().replace('s', ''))
        self.lyric_window.start_lyric(
            text, font, self.current_color, self.current_stroke_color,
            self.stroke_spin.value(), self.angle_min.value(), self.angle_max.value(),
            self.margin_spin.value(), self.max_interval_spin.value(), self.max_duration_spin.value(),
            mode, self.spacing_spin.value(), self.shake_intensity_slider.value(),
            self.shake_speed_slider.value(), self.fade_speed_slider.value(),
            self.rise_speed_slider.value(), self.glow_check.isChecked(),
            self.current_glow_color, self.glow_size_slider.value(),
            self.glow_alpha_slider.value(), start_delay=delay
        )
        self.status.setText(f"状态：正在播放... 模式：{mode}")

    def stop(self): self.lyric_window.stop_lyric(); self.status.setText("状态：已停止")
    def _collect_settings(self):
        """从 UI 控件提取设置字典，供配置保存使用。"""
        return {
            'text_color': self.current_color.name(),
            'stroke_color': self.current_stroke_color.name(),
            'glow_color': self.current_glow_color.name(),
            'glow_enabled': self.glow_check.isChecked(),
            'glow_size': self.glow_size_slider.value(),
            'glow_alpha': self.glow_alpha_slider.value(),
            'loop': self.loop_check.isChecked(),
            'trans_only': self.trans_check.isChecked(),
            'mode': self.mode_combo.currentData(),
            'font_family': self.font_combo.currentFont().family(),
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
            'player': self.player_combo.currentText(),
            'source': self.source_combo.currentText(),
            'delay': self.delay_combo.currentIndex(),
            'perspective_enabled': self.perspective_check.isChecked(),
            'persp_x_strength': self.persp_x_slider.value(),
            'persp_y_strength': self.persp_y_slider.value(),
            'persp_compensation': self.persp_comp_slider.value(),
        }

    def closeEvent(self, event):
        save_all_config(self._collect_settings(), self.presets, self.players)
        self.lyric_window.close(); event.accept()