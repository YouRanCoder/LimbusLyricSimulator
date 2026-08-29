"""
应用控制器模块

负责协调业务层和 UI 层，是唯一的"知道两边"的模块。
业务层不知道 UI，UI 层不知道业务，只有 Controller 知道两边。

调用链：
用户操作 UI → UI 发送信号 → Controller 接收 → 调用业务层 → Controller 更新 UI
"""

from dataclasses import dataclass
import re
from typing import Optional, Callable, Dict, Any
from PyQt5.QtCore import QObject, pyqtSignal, QTimer
from PyQt5.QtGui import QColor, QFont
import qasync
from core.player_manager import PlayerManager
from core.lyric_service import LyricService, LyricResult
from core.settings_manager import SettingsManager
from core.fetcher import Fetcher, FetcherEvent, MediaChange, MediaInfo
from config.settings import DEFAULT_CREDIT_PATTERNS
import logging

logger = logging.getLogger(__name__)


@dataclass
class LyricSettings:
    """歌词显示参数数据类，用于在 UI 和 Controller 之间传递歌词配置"""
    text: str = ""
    font: Optional[QFont] = None
    text_color: Optional[QColor] = None
    stroke_color: Optional[QColor] = None
    stroke_width: float = 0.5
    angle_min: int = -10
    angle_max: int = 10
    margin_time: int = 4000
    max_interval: int = 16000
    max_duration: int = 5000
    mode: str = "auto"
    spacing: float = 5.0
    shake_intensity: int = 2
    shake_speed: int = 143
    fade_speed: int = 12
    rise_speed: int = 1
    glow: bool = True
    glow_color: Optional[QColor] = None
    glow_size: int = 4
    glow_alpha: int = 82
    # 歌词起始位置范围（百分比，0~100）
    pos_x_min: int = 5
    pos_x_max: int = 85
    pos_y_min: int = 5
    pos_y_max: int = 75


class AppController(QObject):
    """
    应用控制器
    
    职责：
    1. 管理业务层（PlayerManager、LyricService、SettingsManager）
    2. 接收 UI 层的事件信号
    3. 调用业务层处理逻辑
    4. 将结果通过信号返回给 UI 层
    """
    
    # ---- 输出信号（UI 层监听这些信号来更新界面） ----
    
    # 状态文本更新
    status_changed = pyqtSignal(str)
    
    # 歌词获取结果
    lyric_fetched = pyqtSignal(str, int, str, str)  # (lyric_text, duration_ms, song, artist)
    
    # 歌词获取失败
    lyric_fetch_failed = pyqtSignal(str)  # (error_message)
    
    # 播放器列表更新
    player_list_updated = pyqtSignal(list)  # (player_names)
    
    # 预设列表更新
    preset_list_updated = pyqtSignal(list)  # (preset_names)
    
    # 歌曲更新通知
    song_updated = pyqtSignal()

    # 歌曲播放/暂停通知
    playback_status_updated = pyqtSignal(bool)  # (is_playing)

    # 播放器不支持进度同步的警告通知（UI 层据此弹出警告框）
    progress_unsupported_warning = pyqtSignal(str)  # (player_name)

    # 网易云日志适配器初始化失败通知（UI 层据此弹出警告框）
    netease_log_init_failed = pyqtSignal(str)  # (reason)
    def __init__(self, settings: Optional[SettingsManager] = None):
        super().__init__()
        
        # 初始化业务层
        self.settings = settings or SettingsManager()
        self.settings.load()
        
        # 播放器管理器（回调指向内部方法）
        self.player_manager = PlayerManager(
            players_config=self.settings.get_players(),
            media_changed_callback=self._on_media_changed_internal,
            error_callback=self._on_fetcher_init_error,
        )
        
        # 歌词服务（初始时 fetcher 为 None，切换播放器后更新）
        self.lyric_service: Optional[LyricService] = None
        
        # UI 层引用（通过 set_ui 注入）
        self._control_panel = None
        self._lyric_window = None
        
        # 播放器真实进度轮询（实时适配歌词时间轴）
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(200)
        self._progress_timer.timeout.connect(self._sync_playback_progress)

        # 歌词获取互斥守卫：防止重复点击/多路触发并发执行 fetch_lyric，
        # 避免 qasync 事件循环出现 "Cannot enter into task while another task is being executed" 卡死
        self._fetch_in_progress = False
    
    def set_ui(self, control_panel, lyric_window) -> None:
        """
        注入 UI 层引用
        
        Args:
            control_panel: 控制面板实例
            lyric_window: 歌词窗口实例
        """
        self._control_panel = control_panel
        self._lyric_window = lyric_window
        
        # 初始化歌词服务（此时 fetcher 已存在）
        self.lyric_service = LyricService(self.player_manager.current_fetcher)

        # 应用已保存的歌词演出延迟（0.1s 精度，正值延后/负值提前）
        self._lyric_window.lyric_offset_ms = int(round(
            self.settings.get_setting('lyric_offset', 0.0) * 1000))
        # 应用已保存的跟读预点亮句数（当前句之后暗态显示的后续句数，0=关闭）
        self._lyric_window.preview_count = int(
            self.settings.get_setting('preview_lines', 0))
        # 应用已保存的"未播放歌词保持暗态"（False=亮态常驻，唱完正常淡出）
        self._lyric_window.preview_keep_dim = bool(
            self.settings.get_setting('preview_keep_dim', True))

        # 应用已保存的防捕获设置（独立 Overlay：录屏/直播软件不可见）
        if self.settings.get_setting('exclude_from_capture', False):
            self.set_exclude_from_capture(True)
    
    # ---- 业务方法（UI 层调用这些方法触发业务逻辑） ----
    
    def switch_player(self, player_name: str) -> None:
        """切换播放器"""
        logger.info("切换播放器：%s", player_name)
        netease_adapter = self.settings.get_setting('netease_adapter_enabled', True)
        self.player_manager.switch_player(player_name, netease_adapter=netease_adapter)
        # 更新歌词服务的 fetcher 引用
        if self.lyric_service:
            self.lyric_service.fetcher = self.player_manager.current_fetcher
        self.player_manager.start_current()
        logger.info("已切换到播放器 %s", player_name)
        self.status_changed.emit(f"状态：已切换到播放器 {player_name}")
        # 播放器不支持进度同步时提示用户（仅一次，切换时弹出）
        if not self._player_supports_progress(player_name):
            self.progress_unsupported_warning.emit(player_name)
    
    def set_netease_adapter(self, enabled: bool) -> None:
        """切换网易云适配方式（勾选=网易云日志适配器，取消=SMTC）"""
        logger.info("切换网易云适配方式：%s", "日志适配器" if enabled else "SMTC")
        self.settings.set_setting('netease_adapter_enabled', enabled)
        # 仅在当前是网易云音乐时立即重建 fetcher 以套用新的适配方式
        if self.player_manager.current_player_name == '网易云音乐':
            self.player_manager.switch_player('网易云音乐', netease_adapter=enabled, force=True)
            # 更新歌词服务的 fetcher 引用
            if self.lyric_service:
                self.lyric_service.fetcher = self.player_manager.current_fetcher
            self.player_manager.start_current()
            self.status_changed.emit(f"状态：已切换网易云适配方式（{'日志' if enabled else 'SMTC'}）")
    
    def start_player_listener(self) -> None:
        """启动播放器监听（需在主事件循环中调用）"""
        logger.info("启动播放器监听")
        self.player_manager.start_current()
    
    def stop_player_listener(self) -> None:
        """停止播放器监听"""
        logger.info("停止播放器监听")
        self.player_manager.stop_current()
    
    @qasync.asyncSlot()
    async def fetch_lyric(self, source: str, trans_only: bool, manual_input_callback=None) -> bool:
        """
        异步获取歌词（不会阻塞事件循环）
        
        Args:
            source: 歌词源
            trans_only: 是否仅获取翻译歌词
            manual_input_callback: 手动输入回调
            
        Returns:
            bool: 是否成功获取歌词（供切歌自动播放时判断是否继续）
        """
        # 互斥守卫：上一次获取尚未完成时忽略本次请求，
        # 防止多个 fetch_lyric 协程并发执行导致 qasync 事件循环崩溃
        if self._fetch_in_progress:
            logger.warning("歌词获取正在进行中，忽略重复请求")
            return False

        self._fetch_in_progress = True
        try:
            self.status_changed.emit("状态：正在获取当前播放...")

            if not self.lyric_service:
                logger.error("歌词服务未初始化，无法获取歌词")
                self.lyric_fetch_failed.emit("歌词服务未初始化")
                return False

            logger.info("开始获取歌词：来源=%s，仅翻译=%s", source, trans_only)
            result = await self.lyric_service.fetch_lyric_with_fallback(
                source=source,
                trans_only=trans_only,
                manual_input_callback=manual_input_callback
            )

            if result.success:
                lyric = self.filter_credit_lines(result.lyric)
                logger.info("歌词获取成功：%s - %s，时长 %dms", result.song, result.artist, result.duration_ms)
                self.lyric_fetched.emit(lyric, result.duration_ms, result.song, result.artist)
                self.status_changed.emit(f"状态：已获取「{result.song}」的歌词")
                return True
            else:
                if not result.song and not result.artist:
                    logger.info("歌词获取已取消")
                    self.status_changed.emit("状态：已取消")
                else:
                    logger.warning("未找到歌词：%s - %s（可能为纯音乐）", result.song, result.artist)
                    self.lyric_fetch_failed.emit("未找到歌词，请尝试换源")
                    self.status_changed.emit("状态：未找到歌词，请尝试换源")
                return False
        finally:
            self._fetch_in_progress = False
    
    @qasync.asyncSlot()
    async def list_smtc_sessions(self) -> list:
        """枚举当前 SMTC 会话（排除已配置的播放器），返回可用 AUMID 列表供 UI 选择"""
        from core.fetcher import list_smtc_sessions as _list_smtc_sessions
        available = await _list_smtc_sessions()
        if not available:
            return []
        configured = [cfg.get("process", "").lower()
                      for cfg in self.settings.get_players().values()
                      if cfg.get("process")]
        return [aumid for aumid in available
                if not any(proc and proc in aumid.lower() for proc in configured)]

    @qasync.asyncSlot()
    async def list_all_smtc_sessions(self) -> list:
        """枚举当前所有 SMTC 会话（不排除已配置的播放器），供修改播放器时重新筛选"""
        from core.fetcher import list_smtc_sessions as _list_smtc_sessions
        return await _list_smtc_sessions()

    def add_player(self, name: str, process: str,
                   support_progress: bool = True) -> bool:
        """添加播放器配置"""
        success = self.settings.add_player(name, process, support_progress)
        if success:
            # 同步到 PlayerManager
            self.player_manager.players_config = self.settings.get_players()
            self.player_list_updated.emit(self.settings.get_player_names())
            self.status_changed.emit(f"状态：已添加播放器 {name}")
        else:
            logger.warning("添加播放器 %s 失败：已存在", name)
            self.status_changed.emit("状态：该播放器已存在")
        return success

    def update_player(self, name: str, new_name: str, process: str,
                      support_progress: bool = True) -> bool:
        """修改播放器配置（可重命名、重新绑定会话、调整是否支持同步进度）"""
        if name not in self.settings.get_players():
            logger.warning("修改播放器 %s 失败：不存在", name)
            self.status_changed.emit("状态：播放器不存在")
            return False
        success = self.settings.update_player(name, new_name, process, support_progress)
        if not success:
            logger.warning("修改播放器 %s 失败：新名称 %s 已存在", name, new_name)
            self.status_changed.emit("状态：该名称已被使用")
            return False
        # 同步到 PlayerManager
        self.player_manager.players_config = self.settings.get_players()
        # 若修改的是当前播放器，重建 fetcher 以套用新会话/名称/进度设置
        if name == self.player_manager.current_player_name:
            if new_name != name:
                self.settings.set_setting('player', new_name)
            netease_adapter = self.settings.get_setting('netease_adapter_enabled', True)
            self.player_manager.switch_player(new_name, netease_adapter=netease_adapter, force=True)
            # 更新歌词服务的 fetcher 引用
            if self.lyric_service:
                self.lyric_service.fetcher = self.player_manager.current_fetcher
            self.player_manager.start_current()
        self.player_list_updated.emit(self.settings.get_player_names())
        self.status_changed.emit(f"状态：已修改播放器 {new_name}")
        return True
    
    def delete_player(self, name: str) -> bool:
        """删除播放器配置"""
        success = self.settings.delete_player(name)
        if success:
            # 同步到 PlayerManager
            self.player_manager.players_config = self.settings.get_players()
            self.player_list_updated.emit(self.settings.get_player_names())
            self.status_changed.emit(f"状态：已删除播放器 {name}")
        else:
            if len(self.settings.get_players()) <= 1:
                logger.warning("删除播放器 %s 失败：至少保留一个", name)
                self.status_changed.emit("状态：至少保留一个播放器")
            else:
                logger.warning("删除播放器 %s 失败：不存在", name)
                self.status_changed.emit("状态：播放器不存在")
        return success
    
    def add_preset(self, name: str, preset_data: Dict[str, Any]) -> bool:
        """添加预设"""
        success = self.settings.add_preset(name, preset_data)
        if success:
            self.preset_list_updated.emit(self.settings.get_preset_names())
            self.status_changed.emit(f"状态：已创建预设 {name}")
        else:
            logger.warning("创建预设 %s 失败：已存在", name)
            self.status_changed.emit("状态：该预设名称已存在")
        return success
    
    def delete_preset(self, name: str) -> bool:
        """删除预设"""
        success = self.settings.delete_preset(name)
        if success:
            self.preset_list_updated.emit(self.settings.get_preset_names())
            self.status_changed.emit(f"状态：已删除预设 {name}")
        else:
            if len(self.settings.get_presets()) <= 1:
                logger.warning("删除预设 %s 失败：至少保留一个", name)
                self.status_changed.emit("状态：至少保留一个预设")
            else:
                logger.warning("删除预设 %s 失败：不存在", name)
                self.status_changed.emit("状态：预设不存在")
        return success
    
    def save_and_close(self) -> None:
        """保存配置并关闭"""
        self.settings.save()
        if self._lyric_window:
            self._lyric_window.close()
    def get_settings(self) -> SettingsManager:
        """获取设置管理器（供 UI 层读取配置）"""
        return self.settings
    
    def get_current_media(self) -> MediaInfo:
        """获取当前播放的媒体信息（供 UI 层判断纯音乐等）"""
        return self.player_manager.get_current_media()
    
    def get_player_names(self) -> list:
        """获取播放器名称列表"""
        return self.settings.get_player_names()
    
    def get_preset_names(self) -> list:
        """获取预设名称列表"""
        return self.settings.get_preset_names()
    
    def get_players_config(self) -> Dict[str, Any]:
        """获取播放器配置（供 UI 层刷新列表）"""
        return self.settings.get_players()
    
    def get_presets(self) -> Dict[str, Any]:
        """获取预设数据（供 UI 层加载预设）"""
        return self.settings.get_presets()
    
    # ---- 歌词窗口控制方法 ----
    
    def start_playback(self, lyric_settings: LyricSettings) -> None:
        """
        开始播放歌词
        
        Args:
            lyric_settings: 歌词显示参数
        """
        if not self._lyric_window:
            logger.warning("歌词窗口未初始化")
            return
        
        logger.info("开始播放歌词：模式=%s，字符数=%d",
                    lyric_settings.mode, len(lyric_settings.text))
        # 应用歌词起始位置范围
        self._lyric_window.pos_x_min = lyric_settings.pos_x_min
        self._lyric_window.pos_x_max = lyric_settings.pos_x_max
        self._lyric_window.pos_y_min = lyric_settings.pos_y_min
        self._lyric_window.pos_y_max = lyric_settings.pos_y_max
        self._lyric_window.start_lyric(
            lyric_settings.text,
            lyric_settings.font,
            lyric_settings.text_color,
            lyric_settings.stroke_color,
            lyric_settings.stroke_width,
            lyric_settings.angle_min,
            lyric_settings.angle_max,
            lyric_settings.margin_time,
            lyric_settings.max_interval,
            lyric_settings.max_duration,
            lyric_settings.mode,
            lyric_settings.spacing,
            lyric_settings.shake_intensity,
            lyric_settings.shake_speed,
            lyric_settings.fade_speed,
            lyric_settings.rise_speed,
            lyric_settings.glow,
            lyric_settings.glow_color,
            lyric_settings.glow_size,
            lyric_settings.glow_alpha,
        )
        # 若播放器支持进度查询，用真实播放进度驱动歌词时间轴
        self._start_progress_sync()
        self.status_changed.emit(f"状态：正在播放... 模式：{lyric_settings.mode}")
    
    def stop_playback(self) -> None:
        """停止播放歌词"""
        logger.info("停止播放歌词")
        self._stop_progress_sync()
        if self._lyric_window:
            self._lyric_window.stop_lyric()
            self.status_changed.emit("状态：已停止")

    def _player_supports_progress(self, player_name: str) -> bool:
        """判断播放器是否支持进度同步（配置里 support_progress 默认开启）"""
        return self.settings.get_players().get(player_name, {}).get("support_progress", True)

    def _start_progress_sync(self) -> None:
        """开始轮询播放器真实进度（仅当当前 Fetcher 支持且播放器配置允许进度查询）"""
        fetcher = self.player_manager.current_fetcher
        player_name = self.player_manager.current_player_name
        if (fetcher is not None and fetcher.supports(Fetcher.CAP_PROGRESS)
                and self._player_supports_progress(player_name)):
            logger.debug("当前 Fetcher 支持进度查询，启动进度轮询")
            self._progress_timer.start()
        else:
            logger.debug("当前 Fetcher 不支持进度查询，使用内部计时")
            self._progress_timer.stop()

    def _stop_progress_sync(self) -> None:
        """停止轮询播放器进度"""
        self._progress_timer.stop()

    def _sync_playback_progress(self) -> None:
        """轮询播放器真实进度并同步到歌词窗口，实现时间轴实时适配"""
        fetcher = self.player_manager.current_fetcher
        if fetcher is None or self._lyric_window is None:
            return
        try:
            progress, duration = fetcher.get_timeline()
            if progress is not None:
                self._lyric_window.set_external_time(int(progress * 1000))
            else:
                # 进度不可用（SMTC 停滞/读取失败）：切回内部计时并衔接，
                # 避免 external_time 停留在陈旧值导致歌词被钉死
                self._lyric_window.switch_to_internal_timing()
        except Exception:
            logger.debug("读取播放器进度失败", exc_info=True)

    def pause_playback(self) -> None:
        """暂停歌词播放：定格当前画面，不销毁歌词窗口"""
        if self._lyric_window:
            logger.info("暂停歌词播放")
            self._lyric_window.pause_lyric()
            self.status_changed.emit("状态：已暂停")

    def resume_playback(self) -> None:
        """恢复歌词播放：从暂停位置继续"""
        if self._lyric_window:
            logger.info("恢复歌词播放")
            self._lyric_window.resume_lyric()
            self.status_changed.emit("状态：已恢复")
    
    def set_perspective_enabled(self, enabled: bool) -> None:
        """设置 3D 透视开关"""
        if self._lyric_window:
            self._lyric_window.perspective_enabled = enabled
    
    def set_perspective_x(self, value: float) -> None:
        """设置透视 X 强度"""
        if self._lyric_window:
            self._lyric_window.persp_x_strength = value
    
    def set_perspective_y(self, value: float) -> None:
        """设置透视 Y 强度"""
        if self._lyric_window:
            self._lyric_window.persp_y_strength = value
    
    def set_perspective_compensation(self, value: float) -> None:
        """设置透视补偿"""
        if self._lyric_window:
            self._lyric_window.persp_compensation = value

    def set_lyric_offset(self, seconds: float) -> None:
        """设置歌词演出延迟（秒，0.1s 精度，正值延后/负值提前），实时生效并持久化"""
        logger.info("设置歌词演出延迟：%.1fs", seconds)
        self.settings.set_setting('lyric_offset', seconds)
        if self._lyric_window:
            self._lyric_window.set_lyric_offset_ms(int(round(seconds * 1000)))

    def set_preview_lines(self, count: int) -> None:
        """设置跟读预点亮句数（当前句之后暗态显示的后续句数，0=关闭），实时生效并持久化"""
        logger.info("设置跟读预点亮句数：%d", count)
        self.settings.set_setting('preview_lines', int(count))
        if self._lyric_window:
            self._lyric_window.set_preview_count(int(count))

    def set_preview_keep_dim(self, keep_dim: bool) -> None:
        """设置未播放歌词是否保持暗态（False=亮态常驻显示，唱到直接呈现、唱完正常淡出）"""
        logger.info("设置未播放歌词保持暗态：%s", keep_dim)
        self.settings.set_setting('preview_keep_dim', bool(keep_dim))
        if self._lyric_window:
            self._lyric_window.preview_keep_dim = bool(keep_dim)
            self._lyric_window.update()

    def set_exclude_from_capture(self, enabled: bool) -> None:
        """设置歌词窗口防捕获（独立 Overlay：录屏/直播软件不可见）"""
        self.settings.set_setting('exclude_from_capture', enabled)
        if not self._lyric_window:
            return
        if not self._lyric_window.set_exclude_from_capture(enabled):
            # 旧版 Windows 不支持 WDA_EXCLUDEFROMCAPTURE，提示用户
            self.status_changed.emit("状态：防捕获开启失败（需要 Win10 2004+）")

    def set_pos_x_min(self, value: int) -> None:
        """设置歌词起始 X 最小值（百分比）"""
        if self._lyric_window:
            self._lyric_window.pos_x_min = value
    
    def set_pos_x_max(self, value: int) -> None:
        """设置歌词起始 X 最大值（百分比）"""
        if self._lyric_window:
            self._lyric_window.pos_x_max = value
    
    def set_pos_y_min(self, value: int) -> None:
        """设置歌词起始 Y 最小值（百分比）"""
        if self._lyric_window:
            self._lyric_window.pos_y_min = value
    
    def set_pos_y_max(self, value: int) -> None:
        """设置歌词起始 Y 最大值（百分比）"""
        if self._lyric_window:
            self._lyric_window.pos_y_max = value

    def filter_credit_lines(self, text: str) -> str:
        """过滤掉歌词中的编曲作词等标注行"""
        if not self.settings.get_setting('filter_credits', True):
            return text
        patterns = self.settings.get_setting('credit_patterns', None)
        if not patterns:
            patterns = list(DEFAULT_CREDIT_PATTERNS)
        compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
        lines = text.split('\n')
        filtered = []
        for line in lines:
            ls = line.strip()
            if not ls:
                filtered.append(line)
                continue
            ts_match = re.match(r'\[(\d+):(\d+)(?:[.:](\d+))?\](.*)', ls)
            text_part = ts_match.group(4).strip() if ts_match else ls
            if not any(p.search(text_part) for p in compiled):
                filtered.append(line)
        return '\n'.join(filtered)
    
    # ---- 内部方法 ----
    
    def _on_fetcher_init_error(self, reason: str) -> None:
        """Fetcher 初始化失败回调：仅上报网易云日志适配器失败，提示 UI 弹警告窗"""
        logger.warning("Fetcher 初始化失败上报：%s", reason)
        self.netease_log_init_failed.emit(reason)
    
    def _on_media_changed_internal(self, change: MediaChange) -> None:
        """媒体变化事件处理（按事件类型分发）"""
        if change.event == FetcherEvent.SONG_CHANGED:
            logger.debug(
                "Controller 收到切歌通知: %s - %s",
                change.media.song, change.media.artist,
            )
            # 通知 UI 层歌曲已更新，触发自动播放流程
            self.song_updated.emit()
        elif change.event == FetcherEvent.PLAY_STATE_CHANGED:
            logger.debug(
                "Controller 收到播放状态通知: %s",
                "播放" if change.media.is_playing else "暂停",
            )
            self.playback_status_updated.emit(change.media.is_playing)
