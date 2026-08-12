"""
应用控制器模块

负责协调业务层和 UI 层，是唯一的"知道两边"的模块。
业务层不知道 UI，UI 层不知道业务，只有 Controller 知道两边。

调用链：
用户操作 UI → UI 发送信号 → Controller 接收 → 调用业务层 → Controller 更新 UI
"""

from dataclasses import dataclass
from typing import Optional, Callable, Dict, Any
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtGui import QColor, QFont
from core.player_manager import PlayerManager
from core.lyric_service import LyricService, LyricResult
from core.settings_manager import SettingsManager
from core.fetcher import FetcherEvent, MediaChange, MediaInfo
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
    mode: str = "chinese"
    spacing: float = 5.0
    shake_intensity: int = 2
    shake_speed: int = 143
    fade_speed: int = 12
    rise_speed: int = 1
    glow: bool = True
    glow_color: Optional[QColor] = None
    glow_size: int = 4
    glow_alpha: int = 82
    start_delay: int = 0
    loop: bool = True
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
    
    # 切歌自动播放
    auto_play_requested = pyqtSignal()
    
    def __init__(self, settings: Optional[SettingsManager] = None):
        super().__init__()
        
        # 初始化业务层
        self.settings = settings or SettingsManager()
        self.settings.load()
        
        # 播放器管理器（回调指向内部方法）
        self.player_manager = PlayerManager(
            players_config=self.settings.get_players(),
            media_changed_callback=self._on_media_changed_internal
        )
        
        # 歌词服务（初始时 fetcher 为 None，切换播放器后更新）
        self.lyric_service: Optional[LyricService] = None
        
        # UI 层引用（通过 set_ui 注入）
        self._control_panel = None
        self._lyric_window = None
    
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
    
    # ---- 业务方法（UI 层调用这些方法触发业务逻辑） ----
    
    def switch_player(self, player_name: str) -> None:
        """切换播放器"""
        self.player_manager.switch_player(player_name)
        # 更新歌词服务的 fetcher 引用
        if self.lyric_service:
            self.lyric_service.fetcher = self.player_manager.current_fetcher
        self.player_manager.start_current()
        logging.debug(f"状态：已切换到播放器 {player_name}")
        self.status_changed.emit(f"状态：已切换到播放器 {player_name}")
    
    def start_player_listener(self) -> None:
        """启动播放器监听（需在主事件循环中调用）"""
        self.player_manager.start_current()
    
    def stop_player_listener(self) -> None:
        """停止播放器监听"""
        self.player_manager.stop_current()
    
    def fetch_lyric(self, source: str, trans_only: bool, manual_input_callback=None) -> None:
        """
        获取歌词
        
        Args:
            source: 歌词源
            trans_only: 是否仅获取翻译歌词
            manual_input_callback: 手动输入回调
        """
        self.status_changed.emit("状态：正在获取当前播放...")
        
        if not self.lyric_service:
            self.lyric_fetch_failed.emit("歌词服务未初始化")
            return
        
        result = self.lyric_service.fetch_lyric_with_fallback(
            source=source,
            trans_only=trans_only,
            manual_input_callback=manual_input_callback
        )
        
        if result.success:
            self.lyric_fetched.emit(result.lyric, result.duration_ms, result.song, result.artist)
            self.status_changed.emit(f"状态：已获取「{result.song}」的歌词")
        else:
            if not result.song and not result.artist:
                self.status_changed.emit("状态：已取消")
            else:
                self.lyric_fetch_failed.emit("未找到歌词，请尝试换源")
                self.status_changed.emit("状态：未找到歌词，请尝试换源")
    
    def add_player(self, name: str, process: str, pattern: str) -> bool:
        """添加播放器配置"""
        success = self.settings.add_player(name, process, pattern)
        if success:
            # 同步到 PlayerManager
            self.player_manager.players_config = self.settings.get_players()
            self.player_list_updated.emit(self.settings.get_player_names())
            self.status_changed.emit(f"状态：已添加播放器 {name}")
        else:
            self.status_changed.emit("状态：该播放器已存在")
        return success
    
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
                self.status_changed.emit("状态：至少保留一个播放器")
            else:
                self.status_changed.emit("状态：播放器不存在")
        return success
    
    def add_preset(self, name: str, preset_data: Dict[str, Any]) -> bool:
        """添加预设"""
        success = self.settings.add_preset(name, preset_data)
        if success:
            self.preset_list_updated.emit(self.settings.get_preset_names())
            self.status_changed.emit(f"状态：已创建预设 {name}")
        else:
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
                self.status_changed.emit("状态：至少保留一个预设")
            else:
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
        
        self._lyric_window.loop = lyric_settings.loop
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
            start_delay=lyric_settings.start_delay
        )
        self.status_changed.emit(f"状态：正在播放... 模式：{lyric_settings.mode}")
    
    def stop_playback(self) -> None:
        """停止播放歌词"""
        if self._lyric_window:
            self._lyric_window.stop_lyric()
            self.status_changed.emit("状态：已停止")
    
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
    
    def set_loop(self, enabled: bool) -> None:
        """设置单曲循环"""
        if self._lyric_window:
            self._lyric_window.loop = enabled
    
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
    
    def set_song_duration(self, duration_ms: int) -> None:
        """设置歌曲时长"""
        if self._lyric_window:
            self._lyric_window.song_duration = duration_ms
    
    # ---- 内部方法 ----
    
    def _on_media_changed_internal(self, change: MediaChange) -> None:
        """媒体变化事件处理（按事件类型分发）"""
        if change.event == FetcherEvent.SONG_CHANGED:
            logger.debug(
                "Controller 收到切歌通知: %s - %s",
                change.media.song, change.media.artist,
            )
            # 通知 UI 层触发自动播放流程
            self.auto_play_requested.emit()
        elif change.event == FetcherEvent.PLAY_STATE_CHANGED:
            logger.debug(
                "Controller 收到播放状态通知: %s",
                "播放" if change.media.is_playing else "暂停",
            )
            # TODO: 后续可在此暂停/恢复歌词滚动、同步 UI 播放按钮等
