import asyncio
import logging
from abc import ABC, abstractmethod
from asyncio import Task
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict

from cloudmusic_detector import AsyncCloudMusic
from cloudmusic_detector.types import PlayState, PlayingState
from winrt._winrt_windows_media_control import GlobalSystemMediaTransportControlsSessionMediaProperties
from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSession,
    GlobalSystemMediaTransportControlsSessionManager,
    GlobalSystemMediaTransportControlsSessionMediaProperties,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus,
)

logger: logging.Logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@dataclass(frozen=True)
class MediaInfo:
    """媒体状态快照。duration / position 单位均为秒。"""

    song: str = ""
    artist: str = ""
    duration: float = 0.0
    position: float = 0.0
    is_playing: bool = False

    @property
    def has_track(self) -> bool:
        """返回是否有正在播放的歌曲"""
        return bool(self.song)

    @property
    def duration_ms(self) -> int:
        """返回总时长（毫秒）"""
        return int(self.duration * 1000)

    @property
    def position_ms(self) -> int:
        """返回当前播放位置（毫秒）"""
        return int(self.position * 1000)

    @classmethod
    def from_playing_state(cls, state: PlayingState) -> "MediaInfo":
        """从 PlayingState 快照创建 MediaInfo"""
        return cls(
            song=state.track.name,
            artist=state.track.artist_str,
            duration=state.track.duration,
            position=state.position,
            is_playing=state.is_playing,
        )


class FetcherEvent(Enum):
    """Fetcher 事件类型"""
    SONG_CHANGED = "song_changed"        # 切歌（歌曲元数据变化）
    PLAY_STATE_CHANGED = "play_state"    # 播放/暂停状态切换


@dataclass(frozen=True)
class MediaChange:
    """事件载荷：事件类型 + 触发事件时的完整媒体快照。"""
    event: FetcherEvent
    media: MediaInfo


class Fetcher(ABC):
    """
    Fetcher抽象类
    
    Attributes: 
        CAP_PROGRESS: 支持进度查询    
        CAP_EVENT: 支持事件回调
    """
    CAP_PROGRESS = "progress"
    CAP_EVENT = "event"

    def __init__(self, player_name: str, callback: callable = None, settings: Dict = None) -> None:
        """
        初始化Fetcher
        
        Args:
            player_name: 播放器名称
            callback: 媒体变化回调函数，签名为 callback(change: MediaChange)
            settings: 播放器配置字典，格式为 {process: 进程名, pattern: 正则}
        """
        self.player_name: str = player_name
        self.callback = callback
        self.settings: Dict = settings or {}
        # 播放器配置（子类通过 super().__init__(player_name, callback, players) 传入）
        self.players: Dict = self.settings
        self.capabilities = set()
        self._current_song = None
        self._current_artist = None
        self._last_media = MediaInfo()
        self._loop: asyncio.AbstractEventLoop | None = self._get_main_loop()
    
    # ---- 生命周期（子类必须实现） ----
    @abstractmethod
    def start(self) -> None:
        """启动监听，必须非阻塞。"""

    @abstractmethod
    def stop(self) -> None:
        """停止监听，释放资源。"""

    # ---- 查询接口 ----
    @abstractmethod
    def get_current_media(self) -> None:
        """返回当前媒体快照 MediaInfo；无播放时返回空 MediaInfo。"""

    def get_progress(self) -> float | None:
        """返回当前播放进度（秒）；不支持时返回 None。"""
        return None

    def get_duration(self) -> float | None:
        """返回总时长（秒）；不支持时返回 None。"""
        return None

    def supports(self, capability) -> bool:
        """返回是否支持指定功能。"""
        return capability in self.capabilities

    # ---- 内部工具 ----
    def _emit(self, event: FetcherEvent, media: MediaInfo) -> None:
        """统一事件发出点：所有媒体变化都通过这里推送。"""
        if self.callback:
            self.callback(MediaChange(event=event, media=media))

    def _update_media(self, media: MediaInfo, notify: bool = True) -> bool:
        """
        更新媒体快照，通过与上次快照比对识别事件类型并发出回调。
        返回是否有任何变化。
        
        Args:
            media: 最新媒体快照
            notify: 是否触发回调
        """
        old = self._last_media
        self._last_media = media
        changed = False

        # 切歌：歌曲名或歌手变化
        if (media.song, media.artist) != (old.song, old.artist):
            self._current_song = media.song
            self._current_artist = media.artist
            logger.debug("歌曲变化: %s - %s", media.song, media.artist)
            if notify:
                self._emit(FetcherEvent.SONG_CHANGED, media)
            changed = True

        # 播放状态切换：播放 <-> 暂停/停止
        if media.is_playing != old.is_playing:
            logger.debug(
                "播放状态变化: %s", "播放" if media.is_playing else "暂停"
            )
            if notify:
                self._emit(FetcherEvent.PLAY_STATE_CHANGED, media)
            changed = True

        return changed

    @staticmethod
    def _get_main_loop() -> asyncio.AbstractEventLoop | None:
        try:
            return asyncio.get_event_loop()
        except RuntimeError:
            return None

    def _call_on_main(self, fn, *args) -> None:
        """把回调安全切回主事件循环线程执行（供后台线程调用）。"""
        if self._loop is None or self._loop.is_closed():
            return
        
        try:
            self._loop.call_soon_threadsafe(fn, *args)
        except RuntimeError:
            pass


class FetcherBySMTC(Fetcher):
    """基于 Windows SMTC 的通用播放器获取器（事件驱动）。
    通过系统媒体传输控件监听指定进程的切歌事件，不提供进度查询。
    """

    def __init__(self, player_name, callback=None, players=None) -> None:
        super().__init__(player_name, callback, players)
        self.capabilities: set[str] = {self.CAP_EVENT}
        self.session = None
        # SessionManager
        self.manager = None
        self._task = None
        self._is_playing = False

    # ---- 生命周期 ----
    def start(self) -> None:
        """启动 SMTC 监听（需在主事件循环中调用，非阻塞）。"""
        if self._task is not None and not self._task.done():
            return
        self._task: Task[None] = asyncio.get_event_loop().create_task(self.init())

    def stop(self) -> None:
        """停止 SMTC 监听。"""
        if self.session is not None:
            try:
                self.session.remove_media_properties_changed(self.on_media_changed)
            except Exception:
                pass
        self.session = None
        if self._task is not None:
            self._task.cancel()
            self._task = None

    # ---- 查询接口 ----
    def get_current_media(self) -> MediaInfo:
        if not self._current_song:
            return MediaInfo()
        logger.debug("尝试获取当前媒体信息: %s - %s", self._current_song, self._current_artist)
        return MediaInfo(
            song=self._current_song,
            artist=self._current_artist,
            is_playing=self._is_playing,
        )

    # ---- 内部实现 ----
    async def init(self) -> None:
        logger.debug("开始初始化")
        self.manager: GlobalSystemMediaTransportControlsSessionManager = (
            await GlobalSystemMediaTransportControlsSessionManager.request_async()
        )
        sessions = list(self.manager.get_sessions())
        logger.debug(
            "当前 SMTC 会话: %s",
            [s.source_app_user_model_id for s in sessions],
        )
        process = self.players.get(self.player_name, {}).get("process", "")
        self.session: GlobalSystemMediaTransportControlsSession | None = next(
            (s for s in sessions
             if s.source_app_user_model_id
             and process.lower() in s.source_app_user_model_id.lower()),
            None,
        )
        # 兜底：按进程名匹配不到时，使用当前正在播放的会话
        if self.session is None:
            self.session = self.manager.get_current_session()
        if self.session is None:
            logger.warning("没有找到 SMTC 播放器: %s", self.player_name)
            return
        self.session.add_media_properties_changed(self.on_media_changed)
        await self.update_song(notify=False)

    def on_media_changed(self, sender, args) -> None:
        if self._loop is None or self._loop.is_closed():
            return
        try:
            self._loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self.update_song())
            )
        except RuntimeError:
            pass

    def _read_playback_status(self) -> bool:
        """从 SMTC 会话读取当前是否正在播放。"""
        try:
            play_info = self.session.get_playback_info()
            status = play_info.playback_status
            return status == GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING
        except Exception:
            return self._is_playing

    async def update_song(self, notify=True) -> None:
        if self.session is None:
            return
        info: GlobalSystemMediaTransportControlsSessionMediaProperties | None = await self.session.try_get_media_properties_async()
        song, artist = info.title, info.artist
        # 同曲连续两次读取一致时再确认一次，用于识别同一首歌重新播放
        if song == self._current_song and artist == self._current_artist:
            await asyncio.sleep(0.8)
            info: GlobalSystemMediaTransportControlsSessionMediaProperties | None = await self.session.try_get_media_properties_async()
            song, artist = info.title, info.artist

        is_playing = self._read_playback_status()
        self._is_playing = is_playing
        self._update_media(
            MediaInfo(song=song, artist=artist, is_playing=is_playing),
            notify=notify,
        )

class FetchByCMLog(Fetcher):
    """基于网易云音乐日志的获取器（事件驱动）。
    
    通过监控网易云音乐日志文件，解析切歌事件、播放状态和播放进度。
    """

    def __init__(self, player_name, callback=None, players=None) -> None:
        """callback:媒体变化回调，签名为 callback(change: MediaChange)"""
        super().__init__(player_name, callback, players)
        self.capabilities: set[str] = {self.CAP_PROGRESS, self.CAP_EVENT}
        self._task = None
        self._cm: AsyncCloudMusic | None = None

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task: Task[None] = asyncio.get_event_loop().create_task(self._init())
        return super().start()

    async def _init(self) -> None:
        self._cm = AsyncCloudMusic()
        await self._cm.start()
        # 注册切歌与播放/暂停回调
        self._cm.on_track_change(self._on_track_change)
        self._cm.on_state_change(self._on_state_change)
        # 推送初始快照（不触发回调）
        self._sync_state(notify=False)

    def stop(self) -> None:
        if self._cm is not None:
            try:
                asyncio.get_event_loop().create_task(self._cm.stop())
            except RuntimeError:
                pass
            self._cm = None
        if self._task is not None:
            self._task.cancel()
            self._task = None
        return super().stop()

    # ---- 查询接口 ----
    def get_current_media(self) -> MediaInfo:
        """返回当前媒体快照 MediaInfo"""
        if self._cm is None:
            return MediaInfo()
        return MediaInfo.from_playing_state(self._cm.state)

    def get_progress(self) -> float | None:
        """返回当前播放进度（秒）。"""
        if self._cm is None:
            return None
        return self._cm.state.position

    def get_duration(self) -> float | None:
        """返回总时长（秒）。"""
        if self._cm is None or not self._cm.track:
            return None
        return self._cm.track.duration

    # ---- 内部实现 ----
    def _sync_state(self, notify: bool = True) -> None:
        """读取最新快照，通过统一的 _update_media 比对并分发事件。"""
        if self._cm is None:
            return
        self._update_media(
            MediaInfo.from_playing_state(self._cm.state),
            notify=notify,
        )

    def _on_track_change(self, track) -> None:
        """切歌回调（可能在其他线程触发，切回主事件循环）。"""
        self._call_on_main(self._sync_state)

    def _on_state_change(self, state) -> None:
        """播放/暂停回调（可能在其他线程触发，切回主事件循环）。"""
        self._call_on_main(self._sync_state)
        
        