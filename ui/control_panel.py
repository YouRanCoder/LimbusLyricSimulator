"""
控制面板 - 纯 UI 层（PyQt-Fluent-Widgets 重构版）

职责：
1. 构建和显示界面控件（FluentWindow + 侧边导航分页）
2. 接收用户输入
3. 通过 Controller 触发业务逻辑
4. 监听 Controller 信号更新界面

不直接调用业务逻辑，不管理配置，不操作播放器。
"""

import logging

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QColor, QFont, QFontDatabase
from PyQt5.QtWidgets import QApplication, QDialog, QMenu, QSystemTrayIcon

from qfluentwidgets import (
    FluentIcon,
    FluentWindow,
    setThemeColor,
)

import qasync
from core.app_controller import AppController, LyricSettings
from core.autostart import is_autostart_enabled, set_autostart
from core.fetcher import is_pure_music
from ui.dialogs import PlayerConfigDialog, ask_text, confirm, warn
from ui.pages import AnimationPage, AppearancePage, PlaybackPage, TimelinePage


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ControlPanel(FluentWindow):
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

        # 纯音乐/伴奏规则（来自 lyric_config.json，None 表示用内置默认）
        self.inst_patterns = None

        # 应用品牌主题色（金色）
        setThemeColor(QColor("#d8a523"))

        # 构建分页
        self._playback = PlaybackPage()
        self._appearance = AppearancePage()
        self._animation = AnimationPage()
        self._timeline = TimelinePage()

        self.addSubInterface(self._playback.page, FluentIcon.MUSIC, "播放")
        self.addSubInterface(self._appearance.page, FluentIcon.PALETTE, "外观")
        self.addSubInterface(self._animation.page, FluentIcon.MOVE, "动画")
        self.addSubInterface(self._timeline.page, FluentIcon.STOP_WATCH, "时间")

        self.setWindowTitle("歌词字幕器 - 控制面板")
        # 窗口尺寸按屏幕分辨率自适应
        screen = QApplication.primaryScreen().geometry()
        win_w = max(880, min(int(screen.width() * 0.46), 1280))
        win_h = max(640, min(int(screen.height() * 0.55), 960))
        self.resize(win_w, win_h)
        self.setStayOnTop(True)

        # 从 Controller 获取配置
        settings = self.controller.get_settings()

        self._refresh_player_list()
        self._refresh_preset_list()

        self._load_settings(settings)
        self._connect_controller_signals()
        self._connect_ui_events()

        # 初始化播放器
        player_name = settings.get_setting('player', '网易云音乐')
        self.controller.switch_player(player_name)
        # 同步 UI 下拉框
        idx = self._playback.player_combo.findText(player_name)
        if idx >= 0:
            self._playback.player_combo.setCurrentIndex(idx)

        # 开机自启动配置与注册表同步（注册表被手动清理时自动补上）
        if self._playback.autostart_check.isChecked() and not is_autostart_enabled():
            set_autostart(True)

        # 系统托盘（最小化到托盘）
        self._init_tray()

        # 启动播放器监听（延迟到事件循环运行后）
        QTimer.singleShot(0, self.controller.start_player_listener)

    # ---- 设置加载/收集 ----

    def _load_settings(self, settings) -> None:
        """从配置管理器加载设置到 UI 控件"""
        p, a, n, t = self._playback, self._appearance, self._animation, self._timeline
        try:
            a.color_btn.setColor(QColor(settings.get_setting('text_color', '#fffeef')))
            a.stroke_btn.setColor(QColor(settings.get_setting('stroke_color', '#d8a523')))
            n.glow_color_btn.setColor(QColor(settings.get_setting('glow_color', '#d8a523')))
            n.glow_check.setChecked(settings.get_setting('glow_enabled', True))
            n.glow_size_slider.setValue(settings.get_setting('glow_size', 4))
            n.glow_alpha_slider.setValue(settings.get_setting('glow_alpha', 82))
            n.perspective_check.setChecked(settings.get_setting('perspective_enabled', True))
            n.persp_x_slider.setValue(settings.get_setting('persp_x_strength', 5))
            n.persp_y_slider.setValue(settings.get_setting('persp_y_strength', 30))
            n.persp_comp_slider.setValue(settings.get_setting('persp_compensation', 3))
            p.trans_check.setChecked(settings.get_setting('trans_only', False))
            p.bilingual_check.setChecked(settings.get_setting('bilingual_mode', False))
            p.autostart_check.setChecked(settings.get_setting('autostart_enabled', False))
            close_idx = p.close_behavior_combo.findData(settings.get_setting('close_behavior', 'quit'))
            if close_idx >= 0:
                p.close_behavior_combo.setCurrentIndex(close_idx)
            p.netease_adapter_check.setChecked(settings.get_setting('netease_adapter_enabled', True))
            p.exclude_capture_check.setChecked(settings.get_setting('exclude_from_capture', False))
            p.filter_pure_music_check.setChecked(settings.get_setting('filter_pure_music', True))
            p.filter_credits_check.setChecked(settings.get_setting('filter_credits', True))
            self.inst_patterns = settings.get_setting('inst_patterns', None)
            idx = a.mode_combo.findData(settings.get_setting('mode', 'auto'))
            if idx >= 0:
                a.mode_combo.setCurrentIndex(idx)
            a.font_combo.setCurrentText(settings.get_setting('font_family', 'Microsoft YaHei'))
            a.font_size.setValue(settings.get_setting('font_size', 28))
            a.stroke_spin.setValue(settings.get_setting('stroke_width', 0.5))
            a.spacing_spin.setValue(settings.get_setting('spacing', 5.0))
            n.shake_intensity_slider.setValue(settings.get_setting('shake_intensity', 2))
            n.shake_speed_slider.setValue(settings.get_setting('shake_speed', 143))
            n.fade_speed_slider.setValue(settings.get_setting('fade_speed', 12))
            n.rise_speed_slider.setValue(settings.get_setting('rise_speed', 1))
            t.margin_spin.setValue(settings.get_setting('margin_time', 4000))
            t.max_interval_spin.setValue(settings.get_setting('max_interval', 16000))
            t.max_duration_spin.setValue(settings.get_setting('max_duration', 5000))
            t.offset_spin.setValue(settings.get_setting('lyric_offset', 0.0))
            t.preview_combo.setCurrentIndex(settings.get_setting('preview_lines', 0))
            t.preview_dim_check.setChecked(settings.get_setting('preview_keep_dim', True))
            # 双语开启时（已保存）在其余控件加载完成后统一同步跟读预点亮 UI
            if settings.get_setting('bilingual_mode', False):
                self._sync_bilingual_controls(True)
            n.angle_min.setValue(settings.get_setting('angle_min', -10))
            n.angle_max.setValue(settings.get_setting('angle_max', 10))
            t.pos_x_min_s.setValue(settings.get_setting('pos_x_min', 5))
            t.pos_x_max_s.setValue(settings.get_setting('pos_x_max', 85))
            t.pos_y_min_s.setValue(settings.get_setting('pos_y_min', 5))
            t.pos_y_max_s.setValue(settings.get_setting('pos_y_max', 75))
            a.opacity_slider.setValue(settings.get_setting('opacity', 100))
            source_name = settings.get_setting('source', '网易云')
            idx = p.source_combo.findText(source_name)
            if idx >= 0:
                p.source_combo.setCurrentIndex(idx)
        except Exception:
            logger.warning("加载设置失败，部分控件使用默认值", exc_info=True)

    def _collect_ui_settings(self) -> dict:
        """从 UI 控件收集当前设置（供保存配置使用）"""
        p, a, n, t = self._playback, self._appearance, self._animation, self._timeline
        return {
            'text_color': a.color_btn.color.name(),
            'stroke_color': a.stroke_btn.color.name(),
            'glow_color': n.glow_color_btn.color.name(),
            'glow_enabled': n.glow_check.isChecked(),
            'glow_size': n.glow_size_slider.value(),
            'glow_alpha': n.glow_alpha_slider.value(),
            'trans_only': p.trans_check.isChecked(),
            'bilingual_mode': p.bilingual_check.isChecked(),
            'autostart_enabled': p.autostart_check.isChecked(),
            'close_behavior': p.close_behavior_combo.currentData(),
            'netease_adapter_enabled': p.netease_adapter_check.isChecked(),
            'exclude_from_capture': p.exclude_capture_check.isChecked(),
            'filter_pure_music': p.filter_pure_music_check.isChecked(),
            'filter_credits': p.filter_credits_check.isChecked(),
            'mode': a.mode_combo.currentData(),
            'font_family': a.font_combo.currentText(),
            'font_size': a.font_size.value(),
            'stroke_width': a.stroke_spin.value(),
            'spacing': a.spacing_spin.value(),
            'shake_intensity': n.shake_intensity_slider.value(),
            'shake_speed': n.shake_speed_slider.value(),
            'fade_speed': n.fade_speed_slider.value(),
            'rise_speed': n.rise_speed_slider.value(),
            'margin_time': t.margin_spin.value(),
            'max_interval': t.max_interval_spin.value(),
            'max_duration': t.max_duration_spin.value(),
            'lyric_offset': t.offset_spin.value(),
            'preview_lines': t.preview_combo.currentIndex(),
            'preview_keep_dim': t.preview_dim_check.isChecked(),
            'angle_min': n.angle_min.value(),
            'angle_max': n.angle_max.value(),
            'pos_x_min': t.pos_x_min_s.value(),
            'pos_x_max': t.pos_x_max_s.value(),
            'pos_y_min': t.pos_y_min_s.value(),
            'pos_y_max': t.pos_y_max_s.value(),
            'opacity': a.opacity_slider.value(),
            'player': p.player_combo.currentText(),
            'source': p.source_combo.currentText(),
            'perspective_enabled': n.perspective_check.isChecked(),
            'persp_x_strength': n.persp_x_slider.value(),
            'persp_y_strength': n.persp_y_slider.value(),
            'persp_compensation': n.persp_comp_slider.value(),
        }

    # ---- Controller 信号 ----

    def _connect_controller_signals(self) -> None:
        """连接 Controller 的输出信号到 UI 更新方法"""
        p = self._playback
        self.controller.status_changed.connect(p.status.setText)
        self.controller.lyric_fetched.connect(self._on_lyric_fetched)
        self.controller.lyric_fetch_failed.connect(
            lambda msg: p.status.setText(f"状态：{msg}")
        )
        self.controller.player_list_updated.connect(self._on_player_list_updated)
        self.controller.preset_list_updated.connect(self._on_preset_list_updated)
        self.controller.song_updated.connect(self._on_song_updated)
        self.controller.playback_status_updated.connect(self._on_playback_status_updated)
        self.controller.progress_unsupported_warning.connect(self._on_progress_unsupported_warning)
        self.controller.netease_log_init_failed.connect(self._on_netease_log_init_failed)

    def _connect_ui_events(self) -> None:
        """连接 UI 控件事件到 Controller 方法"""
        p, a, n, t = self._playback, self._appearance, self._animation, self._timeline

        # 播放器切换
        p.player_combo.currentTextChanged.connect(self.controller.switch_player)
        p.btn_add_p.clicked.connect(self._on_add_player)
        p.btn_edit_p.clicked.connect(self._on_edit_player)
        p.btn_del_p.clicked.connect(self._on_delete_player)

        # 开始停止 / 重新获取
        p.refetch_btn.clicked.connect(self._on_refetch)
        p.start_btn.clicked.connect(self._on_start)
        p.stop_btn.clicked.connect(self._on_stop)

        # 开机自启动
        p.autostart_check.checkedChanged.connect(self._on_autostart_changed)

        # 切换歌词源/仅翻译时重新获取歌词（不自动重启）
        p.source_combo.currentTextChanged.connect(self._on_source_changed)
        p.trans_check.checkedChanged.connect(self._on_trans_only_changed)

        # 中英双语同时演出：切换时自动管理跟读预点亮并重新获取歌词
        p.bilingual_check.checkedChanged.connect(self._on_bilingual_changed)

        # 网易云适配方式
        p.netease_adapter_check.checkedChanged.connect(self._on_netease_adapter_changed)

        # 防捕获模式（独立 Overlay）：切换时立即套用到歌词窗口
        p.exclude_capture_check.checkedChanged.connect(
            self.controller.set_exclude_from_capture)

        # 编曲作词过滤开关：切换时保存并更新已获取歌词的显示
        p.filter_credits_check.checkedChanged.connect(self._on_filter_credits_changed)

        # 预设
        a.preset_combo.currentTextChanged.connect(self._on_load_preset)
        a.btn_new.clicked.connect(self._on_new_preset)
        a.btn_del.clicked.connect(self._on_delete_preset)
        a.btn_auto_font.clicked.connect(self.auto_select_font)

        # 3D 透视
        n.perspective_check.checkedChanged.connect(
            lambda checked: self.controller.set_perspective_enabled(checked)
        )
        n.persp_x_slider.valueChanged.connect(
            lambda v: (self.controller.set_perspective_x(v / 1000000),
                       n.persp_x_label.setText(f"{v / 1000000:.6f}"))
        )
        n.persp_y_slider.valueChanged.connect(
            lambda v: (self.controller.set_perspective_y(v / 100000),
                       n.persp_y_label.setText(f"{v / 100000:.5f}"))
        )
        n.persp_comp_slider.valueChanged.connect(
            lambda v: (self.controller.set_perspective_compensation(v / 100),
                       n.persp_comp_label.setText(f"{v / 100:.2f}"))
        )

        # 光晕/颤动/淡出/上升数值标签
        n.glow_size_slider.valueChanged.connect(
            lambda v: n.glow_size_label.setText(str(v)))
        n.glow_alpha_slider.valueChanged.connect(
            lambda v: n.glow_alpha_label.setText(str(v)))
        n.shake_intensity_slider.valueChanged.connect(
            lambda v: n.shake_intensity_label.setText(str(v)))
        n.shake_speed_slider.valueChanged.connect(
            lambda v: n.shake_speed_label.setText(f"{v} ms"))
        n.fade_speed_slider.valueChanged.connect(
            lambda v: n.fade_speed_label.setText(str(v)))
        n.rise_speed_slider.valueChanged.connect(
            lambda v: n.rise_speed_label.setText(str(v)))

        # 歌词演出延迟：调整时实时生效并持久化
        t.offset_spin.valueChanged.connect(self.controller.set_lyric_offset)

        # 跟读预点亮：切换时实时生效并持久化（下拉框索引即后续句数）
        t.preview_combo.currentIndexChanged.connect(self.controller.set_preview_lines)

        # 未播放歌词保持暗态：切换时实时生效并持久化
        t.preview_dim_check.checkedChanged.connect(self.controller.set_preview_keep_dim)

        # 起始位置范围
        t.pos_x_min_s.valueChanged.connect(
            lambda v: (self.controller.set_pos_x_min(v),
                       t.pos_x_lbl.setText(f"{v}%"))
        )
        t.pos_x_max_s.valueChanged.connect(
            lambda v: (self.controller.set_pos_x_max(v),
                       t.pos_x_max_lbl.setText(f"{v}%"))
        )
        t.pos_y_min_s.valueChanged.connect(
            lambda v: (self.controller.set_pos_y_min(v),
                       t.pos_y_lbl.setText(f"{v}%"))
        )
        t.pos_y_max_s.valueChanged.connect(
            lambda v: (self.controller.set_pos_y_max(v),
                       t.pos_y_max_lbl.setText(f"{v}%"))
        )

        # 歌词透明度：调整时实时生效
        a.opacity_slider.valueChanged.connect(
            lambda v: (self.controller.set_opacity(v),
                       a.opacity_label.setText(f"{v}%"))
        )

        # 同步所有滑块标签（加载配置后标签可能未更新）
        self._sync_slider_labels()

    def _sync_slider_labels(self) -> None:
        """同步滑块数值标签与当前值一致"""
        a, n, t = self._appearance, self._animation, self._timeline
        n.glow_size_label.setText(str(n.glow_size_slider.value()))
        n.glow_alpha_label.setText(str(n.glow_alpha_slider.value()))
        n.shake_intensity_label.setText(str(n.shake_intensity_slider.value()))
        n.shake_speed_label.setText(f"{n.shake_speed_slider.value()} ms")
        n.fade_speed_label.setText(str(n.fade_speed_slider.value()))
        n.rise_speed_label.setText(str(n.rise_speed_slider.value()))
        n.persp_x_label.setText(f"{n.persp_x_slider.value() / 1000000:.6f}")
        n.persp_y_label.setText(f"{n.persp_y_slider.value() / 100000:.5f}")
        n.persp_comp_label.setText(f"{n.persp_comp_slider.value() / 100:.2f}")
        t.pos_x_lbl.setText(f"{t.pos_x_min_s.value()}%")
        t.pos_x_max_lbl.setText(f"{t.pos_x_max_s.value()}%")
        t.pos_y_lbl.setText(f"{t.pos_y_min_s.value()}%")
        t.pos_y_max_lbl.setText(f"{t.pos_y_max_s.value()}%")
        a.opacity_label.setText(f"{a.opacity_slider.value()}%")

    def _refresh_player_list(self) -> None:
        """刷新播放器下拉列表"""
        p = self._playback
        p.player_combo.blockSignals(True)
        p.player_combo.clear()
        p.player_combo.addItems(self.controller.get_player_names())
        p.player_combo.blockSignals(False)

    def _refresh_preset_list(self) -> None:
        """刷新预设下拉列表"""
        a = self._appearance
        a.preset_combo.blockSignals(True)
        a.preset_combo.clear()
        a.preset_combo.addItems(self.controller.get_preset_names())
        a.preset_combo.blockSignals(False)

    # ---- UI 事件处理（调用 Controller） ----

    def _make_manual_input(self):
        """构造手动输入歌名回调（供主动触发获取歌词时使用）"""
        def manual_input():
            text = ask_text(
                self, "手动输入",
                "未能自动获取歌曲信息，请输入 歌名 - 歌手",
                default="歌名 - 歌手",
            )
            if text:
                parts = text.split(' - ', 1)
                if len(parts) == 2:
                    return parts[0].strip(), parts[1].strip()
                return parts[0].strip(), ""
            return None
        return manual_input

    async def _fetch_lyric_to_box(self, manual_input=None) -> str:
        """获取歌词并填充输入框（供开始播放/重新获取/切歌/切换源共用）

        Returns:
            'ok':   歌词已填充到输入框
            'pure': 命中纯音乐过滤，已清空输入框并更新状态
            'fail': 未获取到歌词
        """
        p = self._playback
        # 纯音乐/伴奏过滤：命中则跳过获取，清空输入框
        if p.filter_pure_music_check.isChecked():
            media = self.controller.get_current_media()
            if is_pure_music(media.song, media.artist, self.inst_patterns):
                logger.info("检测到纯音乐/伴奏：%s - %s，不显示歌词", media.song, media.artist)
                self._on_stop()
                p.text_input.clear()
                p.status.setText("状态：纯音乐/伴奏，不显示歌词")
                return 'pure'
        source = p.source_combo.currentText()
        trans_only = p.trans_check.isChecked()
        success = await self.controller.fetch_lyric(source, trans_only, manual_input)
        return 'ok' if success else 'fail'

    async def _fetch_and_restart(self, manual_input) -> None:
        """获取歌词并自动重新开始歌词表演（切歌/切源/仅翻译切换共用）"""
        result = await self._fetch_lyric_to_box(manual_input)
        if result == 'ok':
            # 获取到歌词：先停止上一首再自动播放
            self._on_stop()
            await self._on_start()
        elif result == 'fail':
            # 没有歌词，停止显示，避免沿用之前的歌词
            self._on_stop()
            self._playback.status.setText("状态：当前歌曲无歌词，不自动播放")
        # 'pure' 已在 _fetch_lyric_to_box 内停止并更新状态，无需处理

    async def _refetch_lyric(self) -> None:
        """获取歌词填充输入框，失败时提示（不自动播放，供用户核对）"""
        result = await self._fetch_lyric_to_box(self._make_manual_input())
        if result == 'fail':
            self._playback.status.setText("状态：未获取到歌词，请尝试换源")

    @qasync.asyncSlot()
    async def _on_refetch(self) -> None:
        """重新获取歌词填充输入框（不自动播放，供用户核对）"""
        logger.info("用户点击重新获取歌词")
        await self._refetch_lyric()

    @qasync.asyncSlot()
    async def _on_source_changed(self) -> None:
        """切换歌词源：重新获取并自动重新开始歌词表演"""
        if not self.controller.get_current_media().has_track:
            return
        logger.info("切换歌词源，重新获取并播放")
        await self._fetch_and_restart(self._make_manual_input())

    @qasync.asyncSlot()
    async def _on_trans_only_changed(self) -> None:
        """切换仅获取翻译歌词：重新获取并自动重新开始歌词表演"""
        if not self.controller.get_current_media().has_track:
            return
        logger.info("切换仅获取翻译歌词，重新获取并播放")
        await self._fetch_and_restart(self._make_manual_input())

    @qasync.asyncSlot()
    async def _on_bilingual_changed(self) -> None:
        """切换中英双语同时演出：自动管理跟读预点亮并重新获取歌词"""
        enabled = self._playback.bilingual_check.isChecked()
        logger.info("切换中英双语同时演出：%s", enabled)
        self.controller.set_bilingual_mode(enabled)
        self._sync_bilingual_controls(enabled)
        if not self.controller.get_current_media().has_track:
            return
        logger.info("中英双语设置变更，重新获取并播放")
        await self._fetch_and_restart(self._make_manual_input())

    def _sync_bilingual_controls(self, enabled: bool) -> None:
        """双语开启时同步跟读预点亮 UI 并禁用其控件，关闭时恢复（以配置为准）"""
        t = self._timeline
        if enabled:
            t.preview_combo.blockSignals(True)
            t.preview_combo.setCurrentIndex(0)
            t.preview_combo.blockSignals(False)
            t.preview_combo.setEnabled(False)
            t.preview_dim_check.setEnabled(False)
        else:
            # controller.set_bilingual_mode(False) 已把 preview_lines 恢复为原值，
            # 这里以配置为唯一事实来源同步 UI
            restore = int(self.controller.settings.get_setting('preview_lines', 0))
            t.preview_combo.blockSignals(True)
            t.preview_combo.setCurrentIndex(restore)
            t.preview_combo.blockSignals(False)
            t.preview_combo.setEnabled(True)
            t.preview_dim_check.setEnabled(True)

    @qasync.asyncSlot()
    async def _on_add_player(self) -> None:
        """从当前 SMTC 会话中选择添加播放器（已配置的播放器不会出现）"""
        logger.info("用户点击添加播放器")
        sessions = await self.controller.list_smtc_sessions()
        if not sessions:
            warn(self, "没有可用的播放器",
                 "未检测到正在播放的 SMTC 会话。\n请先打开目标音乐软件并开始播放，再重试。")
            return
        dialog = PlayerConfigDialog("添加播放器", sessions, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        cfg = dialog.values()
        if not cfg["name"] or not cfg["process"]:
            return
        logger.info("添加播放器：%s（SMTC %s，进度支持 %s）",
                    cfg["name"], cfg["process"], cfg["support_progress"])
        self.controller.add_player(cfg["name"], cfg["process"], cfg["support_progress"])
        self._refresh_player_list()
        self._playback.player_combo.setCurrentText(cfg["name"])

    @qasync.asyncSlot()
    async def _on_edit_player(self) -> None:
        """修改播放器配置：重新筛选 SMTC 会话、调整是否支持同步进度"""
        name = self._playback.player_combo.currentText()
        if not name:
            return
        cfg = self.controller.get_players_config().get(name)
        if not cfg:
            return
        logger.info("用户点击修改播放器：%s", name)
        sessions = await self.controller.list_all_smtc_sessions()
        dialog = PlayerConfigDialog(
            "修改播放器配置", sessions,
            default_name=name,
            default_process=cfg.get("process", ""),
            support_progress=cfg.get("support_progress", True),
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        values = dialog.values()
        new_name = values["name"] or name
        if not values["process"]:
            return
        logger.info("修改播放器：%s -> %s（SMTC %s，进度支持 %s）",
                    name, new_name, values["process"], values["support_progress"])
        self.controller.update_player(
            name, new_name, values["process"], values["support_progress"])
        self._refresh_player_list()
        self._playback.player_combo.setCurrentText(new_name)

    def _on_delete_player(self) -> None:
        """删除播放器"""
        name = self._playback.player_combo.currentText()
        if not name:
            return
        if confirm(self, "删除播放器", f"确定删除「{name}」吗？"):
            logger.info("删除播放器：%s", name)
            self.controller.delete_player(name)
            self._refresh_player_list()

    def _on_new_preset(self) -> None:
        """新建预设"""
        name = ask_text(self, "新建预设", "输入预设名称：")
        if not name:
            return
        preset_data = {
            'text': self._appearance.color_btn.color.name(),
            'stroke': self._appearance.stroke_btn.color.name(),
            'glow': self._animation.glow_color_btn.color.name(),
        }
        logger.info("新建预设：%s", name)
        self.controller.add_preset(name, preset_data)
        self._refresh_preset_list()
        self._appearance.preset_combo.setCurrentText(name)

    def _on_delete_preset(self) -> None:
        """删除预设"""
        name = self._appearance.preset_combo.currentText()
        if not name:
            return
        if confirm(self, "删除预设", f"确定删除「{name}」吗？"):
            logger.info("删除预设：%s", name)
            self.controller.delete_preset(name)
            self._refresh_preset_list()

    def _on_load_preset(self, name: str) -> None:
        """加载预设"""
        presets = self.controller.get_presets()
        if name in presets:
            c = presets[name]
            self._appearance.color_btn.setColor(QColor(c['text']))
            self._appearance.stroke_btn.setColor(QColor(c['stroke']))
            self._animation.glow_color_btn.setColor(QColor(c.get('glow', '#ffffff')))

    @qasync.asyncSlot()
    async def _on_start(self) -> None:
        """开始播放：输入框有内容直接播放，为空则自动获取歌词"""
        p, a, n, t = self._playback, self._appearance, self._animation, self._timeline
        text = p.text_input.toPlainText().strip()
        # 手动粘贴的歌词也应用编曲作词过滤
        if text and p.filter_credits_check.isChecked():
            filtered = self.controller.filter_credit_lines(text)
            if filtered != text:
                p.text_input.setPlainText(filtered)
                text = filtered
        if not text:
            # 无歌词文本：有歌曲在播放则自动获取，否则提示输入
            media = self.controller.get_current_media()
            if not media.has_track:
                logger.warning("用户点击开始，但未输入歌词且无歌曲在播放")
                p.status.setText("状态：请先输入歌词！")
                return
            logger.info("歌词框为空，自动获取歌词")
            result = await self._fetch_lyric_to_box(self._make_manual_input())
            if result != 'ok':
                if result == 'fail':
                    p.status.setText("状态：未获取到歌词，请尝试换源")
                return
            text = p.text_input.toPlainText().strip()
            if not text:
                p.status.setText("状态：未获取到歌词，请尝试换源")
                return
        logger.info("用户点击开始播放：%d 字符，模式=%s",
                    len(text), a.mode_combo.currentData())

        font = QFont(a.font_combo.currentText(), a.font_size.value(), QFont.Bold)
        mode = a.mode_combo.currentData()

        lyric_settings = LyricSettings(
            text=text,
            font=font,
            text_color=a.color_btn.color,
            stroke_color=a.stroke_btn.color,
            stroke_width=a.stroke_spin.value(),
            angle_min=n.angle_min.value(),
            angle_max=n.angle_max.value(),
            margin_time=t.margin_spin.value(),
            max_interval=t.max_interval_spin.value(),
            max_duration=t.max_duration_spin.value(),
            mode=mode,
            spacing=a.spacing_spin.value(),
            shake_intensity=n.shake_intensity_slider.value(),
            shake_speed=n.shake_speed_slider.value(),
            fade_speed=n.fade_speed_slider.value(),
            rise_speed=n.rise_speed_slider.value(),
            glow=n.glow_check.isChecked(),
            glow_color=n.glow_color_btn.color,
            glow_size=n.glow_size_slider.value(),
            glow_alpha=n.glow_alpha_slider.value(),
            pos_x_min=t.pos_x_min_s.value(),
            pos_x_max=t.pos_x_max_s.value(),
            pos_y_min=t.pos_y_min_s.value(),
            pos_y_max=t.pos_y_max_s.value(),
            opacity=a.opacity_slider.value(),
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

        # 自动播放时不弹窗，直接记录失败原因
        def manual_input():
            logger.error("自动播放时未能获取歌曲信息")
            return None

        await self._fetch_and_restart(manual_input)

    def _on_playback_status_updated(self, status: bool) -> None:
        """播放状态变化时自动暂停/恢复（不销毁歌词窗口）"""
        logger.debug("播放状态变化：%s", status)
        if status:
            self._on_resume()
        else:
            self._on_pause()

    def _on_netease_adapter_changed(self, enabled: bool) -> None:
        """网易云适配方式切换：取消勾选时弹窗提醒"""
        if not enabled:
            warn(
                self, "确定你在做什么",
                "如果您使用inflink-rs等第三方网易云插件不能正常运行时请取消勾选，否则如果能正常运行请保持默认设置"
            )
        self.controller.set_netease_adapter(enabled)

    def _on_filter_credits_changed(self, enabled: bool) -> None:
        """编曲作词过滤开关：重新过滤当前歌词框中的内容"""
        logger.info("编曲作词过滤已%s", "开启" if enabled else "关闭")
        self.controller.settings.set_setting('filter_credits', enabled)
        text = self._playback.text_input.toPlainText()
        if text:
            filtered = self.controller.filter_credit_lines(text)
            self._playback.text_input.setPlainText(filtered)

    def _on_autostart_changed(self, enabled: bool) -> None:
        """开机自启动开关：写入/移除注册表启动项"""
        if set_autostart(enabled):
            logger.info("开机自启动已%s", "开启" if enabled else "关闭")
            return
        # 设置失败：回滚开关并提示
        p = self._playback
        p.autostart_check.blockSignals(True)
        p.autostart_check.setChecked(not enabled)
        p.autostart_check.blockSignals(False)
        warn(self, "开机自启动", "设置开机自启动失败，请稍后重试")

    # ---- 系统托盘 ----

    def _init_tray(self) -> None:
        """创建系统托盘图标（支持最小化到托盘）"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.info("当前系统不支持托盘，跳过托盘初始化")
            return
        self._tray = QSystemTrayIcon(FluentIcon.MUSIC.icon(), self)
        self._tray.setToolTip("歌词字幕器")
        menu = QMenu()
        show_action = menu.addAction("显示主面板")
        show_action.triggered.connect(self._show_from_tray)
        menu.addSeparator()
        quit_action = menu.addAction("退出")
        quit_action.triggered.connect(self._quit_from_tray)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()
        # 有托盘后，关闭窗口不再自动退出，由托盘菜单控制
        QApplication.setQuitOnLastWindowClosed(False)

    def _on_tray_activated(self, reason) -> None:
        """单击/双击托盘图标恢复显示主面板"""
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._show_from_tray()

    def _show_from_tray(self) -> None:
        """从托盘恢复显示主面板"""
        self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    def _quit_from_tray(self) -> None:
        """从托盘退出程序"""
        self._quit_app()

    def _quit_app(self) -> None:
        """保存配置并退出程序"""
        settings = self.controller.get_settings()
        settings.update_settings(self._collect_ui_settings())
        logger.info("退出程序，保存配置")
        self.controller.save_and_close()
        QApplication.quit()

    # ---- Controller 信号处理 ----

    def _on_lyric_fetched(self, lyric: str, duration_ms: int, song: str, artist: str) -> None:
        """歌词获取成功"""
        logger.info("歌词已填充到输入框：%s - %s，时长 %dms", song, artist, duration_ms)
        self._playback.text_input.setPlainText(lyric)

    def _on_player_list_updated(self, player_names: list) -> None:
        """播放器列表更新"""
        self._refresh_player_list()

    def _on_progress_unsupported_warning(self, player_name: str) -> None:
        """播放器不支持进度同步时弹出警告框"""
        logger.warning("播放器 %s 不支持进度同步，只能从头播放", player_name)
        warn(self, "不支持进度同步", f"「{player_name}」不支持进度同步，歌词只能从头播放")

    def _on_netease_log_init_failed(self, reason: str) -> None:
        """网易云日志适配器初始化失败时弹出警告框"""
        logger.warning("网易云日志适配器初始化失败：%s", reason)
        warn(
            self,
            "网易云日志读取失败",
            f"无法读取网易云日志（{reason}），歌词无法通过日志同步。\n"
            "请切换为 SMTC 适配方式，或检查网易云客户端是否在运行。",
        )

    def _on_preset_list_updated(self, preset_names: list) -> None:
        """预设列表更新"""
        self._refresh_preset_list()

    # ---- 其他 UI 方法 ----

    def auto_select_font(self) -> None:
        """自动选择推荐字体"""
        a, p = self._appearance, self._playback
        recommended = ["Mikodacs", "思源黑体 Bold"]
        available = [f for f in recommended if f in QFontDatabase().families()]
        if not available:
            p.status.setText("状态：未找到推荐字体")
            return
        current = a.font_combo.currentText()
        try:
            idx = available.index(current)
            next_idx = (idx + 1) % len(available)
        except ValueError:
            next_idx = 0
        chosen = available[next_idx]
        a.font_combo.setCurrentText(chosen)
        p.status.setText(f"状态：已切换字体 {chosen}")

    def closeEvent(self, event) -> None:
        """窗口关闭：按「关闭按钮行为」设置决定最小化到托盘或退出"""
        if hasattr(self, '_tray') and self._playback.close_behavior_combo.currentData() == "tray":
            logger.info("关闭按钮行为为最小化到托盘，隐藏主面板")
            event.ignore()
            self.hide()
            return
        self._quit_app()
        super().closeEvent(event)
