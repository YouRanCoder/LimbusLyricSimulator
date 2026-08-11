import asyncio
import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass

from cloudmusic_detector import CloudMusic
from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager,
)

logger = logging.getLogger(__name__)
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
        return bool(self.song)

    @property
    def duration_ms(self) -> int:
        return int(self.duration * 1000)

    @property
    def position_ms(self) -> int:
        return int(self.position * 1000)


class Fetcher(ABC):
    CAP_PROGRESS = "progress"  # 可查询播放进度
    CAP_EVENT = "event"  # 可推送切歌事件
    CAP_POLL = "poll"  # 可轮询获取当前媒体状态
    def __init__(self, player_name, callback=None, players=None):
        self.player_name = player_name
        self.callback = callback
        self.players = players or {}  # 播放器配置（进程名等），由外部注入
        self.capabilities = set()
        self._current_song = None
        self._current_artist = None
        self._loop = self._get_main_loop()
    # ---- 生命周期（子类必须实现） ----
    @abstractmethod
    def start(self):
        """启动监听，必须非阻塞。"""
    @abstractmethod
    def stop(self):
        """停止监听，释放资源。"""
    # ---- 查询接口 ----
    @abstractmethod
    def get_current_media(self):
        """返回当前媒体快照 MediaInfo；无播放时返回空 MediaInfo。"""
    def get_progress(self):
        """返回当前播放进度（秒）；不支持时返回 None。"""
        return None
    def get_duration(self):
        """返回总时长（秒）；不支持时返回 None。"""
        return None
    def supports(self, capability):
        return capability in self.capabilities
    # ---- 内部工具 ----
    def notify_song_changed(self, song, artist):
        """调用回调通知歌曲变化。"""
        if self.callback:
            self.callback(song, artist)
    def _set_current(self, song, artist, notify=True):
        """记录当前歌曲；与上次不同时通知回调。返回是否发生变化。"""
        if song == self._current_song and artist == self._current_artist:
            return False
        self._current_song = song
        self._current_artist = artist
        logger.debug("歌曲变化: %s - %s", song, artist)
        if notify:
            self.notify_song_changed(song, artist)
        return True
    @staticmethod
    def _get_main_loop():
        try:
            return asyncio.get_event_loop()
        except RuntimeError:
            return None
    def _call_on_main(self, fn, *args):
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

    def __init__(self, player_name, callback=None, players=None):
        super().__init__(player_name, callback, players)
        self.capabilities = {self.CAP_EVENT}
        self.session = None
        self.manager = None
        self._task = None

    # ---- 生命周期 ----
    def start(self):
        """启动 SMTC 监听（需在主事件循环中调用，非阻塞）。"""
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.get_event_loop().create_task(self.init())

    def stop(self):
        """停止 SMTC 监听。"""
        if self.session is not None:
            try:
                self.session.remove_media_properties_changed(
                    self.on_media_changed
                )
            except Exception:
                pass
        self.session = None
        if self._task is not None:
            self._task.cancel()
            self._task = None

    # ---- 查询接口 ----
    def get_current_media(self):
        if not self._current_song:
            return MediaInfo()
        return MediaInfo(song=self._current_song, artist=self._current_artist)

    # ---- 内部实现 ----
    async def init(self):
        self.manager = (
            await GlobalSystemMediaTransportControlsSessionManager
            .request_async()
        )
        process = self.players.get(self.player_name, {}).get("process", "")
        self.session = next(
            (s for s in self.manager.get_sessions()
             if s.source_app_user_model_id == process),
            None,
        )
        if self.session is None:
            logger.warning("没有找到 SMTC 播放器: %s", self.player_name)
            return
        self.session.add_media_properties_changed(self.on_media_changed)
        await self.update_song(notify=False)

    def on_media_changed(self, sender, args):
        if self._loop is None or self._loop.is_closed():
            return
        try:
            self._loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self.update_song())
            )
        except RuntimeError:
            pass

    async def update_song(self, notify=True):
        if self.session is None:
            return
        info = await self.session.try_get_media_properties_async()
        song, artist = info.title, info.artist
        # 同曲连续两次读取一致时再确认一次，用于识别同一首歌重新播放
        if song == self._current_song and artist == self._current_artist:
            await asyncio.sleep(0.8)
            info = await self.session.try_get_media_properties_async()
            song, artist = info.title, info.artist
        self._set_current(song, artist, notify=notify)

