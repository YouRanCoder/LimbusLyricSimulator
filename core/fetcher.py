import asyncio
import logging
import re
from abc import ABC, abstractmethod
from asyncio import Task
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from typing import Dict

from config.settings import DEFAULT_INST_PATTERNS

from cloudmusic_detector import AsyncCloudMusic
from cloudmusic_detector.types import PlayingState
from winrt._winrt_windows_media_control import GlobalSystemMediaTransportControlsSessionMediaProperties
from winrt.windows.media.control import (
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
    SONG_CHANGED = "song_changed"                # 切歌（歌曲元数据变化）
    PLAY_STATE_CHANGED = "play_state_changed"    # 播放/暂停状态切换


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
            settings: 播放器配置字典，格式为 {process: SMTC 会话标识}
        """
        self.player_name: str = player_name
        self.callback = callback
        self.settings: Dict = settings or {}
        # 播放器配置（子类通过 super().__init__(player_name, callback, settings) 传入）
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
    def get_current_media(self) -> MediaInfo:
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
            logger.debug("推送事件 %s：%s - %s", event.value, media.song, media.artist)
            self.callback(MediaChange(event=event, media=media))
        else:
            logger.warning("无回调函数，事件 %s 被丢弃", event.value)

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

    def __init__(self, player_name, callback=None, settings=None) -> None:
        super().__init__(player_name, callback, settings)
        self.capabilities: set[str] = {self.CAP_EVENT, self.CAP_PROGRESS}
        self.session = None
        # SessionManager
        self.manager = None
        self._task = None
        self._is_playing = False
        self._stopped = False
        # SMTC 事件注册令牌（winrt 的 remove_*_changed 需传入 add_*_changed 返回的 token）
        self._sessions_token = None
        self._media_props_token = None
        self._playback_token = None

    # ---- 生命周期 ----
    def start(self) -> None:
        """启动 SMTC 监听（需在主事件循环中调用，非阻塞）。"""
        if self._task is not None and not self._task.done():
            return
        self._stopped = False
        self._task: Task[None] = asyncio.get_event_loop().create_task(self.init())

    def stop(self) -> None:
        """停止 SMTC 监听。"""
        self._stopped = True
        if self.session is not None:
            try:
                self.session.remove_media_properties_changed(self._media_props_token)
                self.session.remove_playback_info_changed(self._playback_token)
            except Exception:
                logger.debug("移除 SMTC 事件监听失败", exc_info=True)
        self.session = None
        if self.manager is not None:
            try:
                self.manager.remove_sessions_changed(self._sessions_token)
            except Exception:
                logger.debug("移除 SMTC 会话变化监听失败", exc_info=True)
        if self._task is not None:
            self._task.cancel()
            self._task = None
        logger.debug("SMTC 监听已停止：%s", self.player_name)

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
    def get_progress(self) -> float | None:
        """返回当前播放进度（秒）；无会话或读取失败时返回 None。"""
        if self.session is None:
            return None
        try:
            timeline = self.session.get_timeline_properties()
            if timeline is None:
                return None
            return timeline.position.total_seconds()
        except Exception:
            logger.debug("读取 SMTC 播放进度失败", exc_info=True)
            return None

    def get_duration(self) -> float | None:
        """返回总时长（秒）；无会话或读取失败时返回 None。"""
        if self.session is None:
            return None
        try:
            timeline = self.session.get_timeline_properties()
            if timeline is None or timeline.end_time is None:
                return None
            return timeline.end_time.total_seconds()
        except Exception:
            logger.debug("读取 SMTC 总时长失败", exc_info=True)
            return None
    # ---- 内部实现 ----
    async def init(self) -> None:
        self.manager: GlobalSystemMediaTransportControlsSessionManager = (
            await GlobalSystemMediaTransportControlsSessionManager.request_async()
        )
        # 订阅会话变化事件：播放器后启动/重启时自动补绑定会话
        try:
            self._sessions_token = self.manager.add_sessions_changed(self._on_sessions_changed)
        except Exception:
            logger.debug("注册 SMTC 会话变化监听失败", exc_info=True)
        # 先按当前会话快照绑定，未找到时等待 sessions_changed 事件
        self._bind_session()

    def _bind_session(self) -> None:
        """按进程名匹配并绑定 SMTC 会话；播放器后启动/重启时由 sessions_changed 事件补绑定。"""
        if self._stopped:
            return
        try:
            sessions = list(self.manager.get_sessions())
        except Exception:
            logger.debug("枚举 SMTC 会话失败", exc_info=True)
            return
        logger.debug(
            "当前 SMTC 会话: %s",
            [s.source_app_user_model_id for s in sessions],
        )
        process = self.settings.get(self.player_name, {}).get("process", "")
        matched = next(
            (s for s in sessions
             if s.source_app_user_model_id
             and process.lower() in s.source_app_user_model_id.lower()),
            None,
        )
        if matched is None:
            logger.warning("没有找到 SMTC 播放器: %s，等待其启动", self.player_name)
            return
        if self._same_session(matched):
            return
        # 解除旧会话监听
        if self.session is not None:
            try:
                self.session.remove_media_properties_changed(self._media_props_token)
                self.session.remove_playback_info_changed(self._playback_token)
            except Exception:
                logger.debug("移除旧 SMTC 会话监听失败", exc_info=True)
        self.session = matched
        logger.info("SMTC 会话已建立：%s", self.session.source_app_user_model_id)
        self._media_props_token = self.session.add_media_properties_changed(self.on_media_changed)
        self._playback_token = self.session.add_playback_info_changed(self.on_playback_changed)
        self._call_on_main(self._schedule_initial_sync)

    def _same_session(self, new_session) -> bool:
        """判断 new_session 是否就是当前已绑定的会话"""
        if self.session is None:
            return False
        if new_session is self.session:
            return True
        try:
            return new_session.get_global_session_id() == self.session.get_global_session_id()
        except Exception:
            return False

    def _on_sessions_changed(self, sender, args) -> None:
        """会话列表变化（播放器后启动/重启）时重新扫描匹配会话"""
        if self._loop is None or self._loop.is_closed():
            return
        try:
            self._loop.call_soon_threadsafe(self._bind_session)
        except RuntimeError:
            pass

    def _schedule_initial_sync(self) -> None:
        """在事件循环上调度初始快照推送（不触发回调）"""
        if self._loop is None or self._loop.is_closed():
            return
        try:
            asyncio.ensure_future(self._initial_sync())
        except RuntimeError:
            pass

    async def _initial_sync(self) -> None:
        await self.update_song_info(notify=False)
        await self.update_playback_state(notify=False)

    def on_media_changed(self, sender, args) -> None:
        if self._loop is None or self._loop.is_closed():
            return
        try:
            self._loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self.update_song_info())
            )
        except RuntimeError:
            pass

    def on_playback_changed(self, sender, args) -> None:
        """播放状态变化回调"""
        if self._loop is None or self._loop.is_closed():
            return
        try:
            self._loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self.update_playback_state())
            )
        except RuntimeError:
            pass

    def _read_playback_status(self) -> bool:
        """从 SMTC 会话读取当前是否正在播放。"""
        try:
            play_info = self.session.get_playback_info()
            status = play_info.playback_status
            logger.debug("SMTC 播放状态: %s", status)
            return status == GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING
        except Exception:
            logger.debug("读取 SMTC 播放状态失败，沿用上次状态", exc_info=True)
            return self._is_playing

    async def update_song_info(self, notify=True) -> None:
        """仅更新歌曲元数据"""
        if self.session is None:
            return
        try:
            media_props: GlobalSystemMediaTransportControlsSessionMediaProperties | None = await self.session.try_get_media_properties_async()
        except Exception:
            logger.debug("读取 SMTC 歌曲信息失败", exc_info=True)
            return
        if not media_props:
            return
        song, artist = media_props.title, media_props.artist
        # 同曲连续两次读取一致时再确认一次，用于识别同一首歌重新播放
        if song == self._current_song and artist == self._current_artist:
            await asyncio.sleep(0.8)
            try:
                media_props = await self.session.try_get_media_properties_async()
            except Exception:
                logger.debug("重复读取 SMTC 歌曲信息失败", exc_info=True)
                media_props = None
            if media_props:
                song, artist = media_props.title, media_props.artist

        is_playing = self._read_playback_status()
        self._is_playing = is_playing
        self._update_media(
            MediaInfo(song=song, artist=artist, is_playing=is_playing),
            notify=notify,
        )

    async def update_playback_state(self, notify=True) -> None:
        """仅更新播放状态"""
        if self.session is None:
            return
        
        is_playing = self._read_playback_status()
        if is_playing != self._is_playing:
            self._is_playing = is_playing
            logger.debug("播放状态独立更新: %s", "播放" if is_playing else "暂停")
            # 使用当前的歌曲信息构造快照并推送
            self._update_media(
                MediaInfo(
                    song=self._current_song, 
                    artist=self._current_artist, 
                    is_playing=is_playing
                ),
                notify=notify,
            )
class FetcherByCMLog(Fetcher):
    """基于网易云音乐日志的获取器（事件驱动，异步启动）。
    
    通过监控网易云音乐日志文件，解析切歌事件、播放状态和播放进度。
    
    依赖库 AsyncCloudMusic.start()/stop() 为真异步实现：阻塞的文件读取、
    日志回溯与 webdb 查询都通过 asyncio.to_thread 在后台线程执行，
    不会卡住 Qt 事件循环（此前阻塞约 1~2 秒导致打包版启动卡顿）。
    """

    def __init__(self, player_name, callback=None, settings=None) -> None:
        """callback:媒体变化回调，签名为 callback(change: MediaChange)"""
        super().__init__(player_name, callback, settings)
        self.capabilities: set[str] = {self.CAP_PROGRESS, self.CAP_EVENT}
        self._task: Task | None = None
        self._cloud_music: AsyncCloudMusic | None = None

    def start(self) -> None:
        """异步启动网易云监听，非阻塞。"""
        if self._task is not None and not self._task.done():
            return
        logger.info("启动网易云日志监听：%s", self.player_name)
        self._task = asyncio.get_event_loop().create_task(self._init())
        # task 异常静默会导致"监听毫无反应但无日志"的假象，这里记录
        self._task.add_done_callback(self._on_init_done)
        return super().start()

    def _on_init_done(self, task: Task) -> None:
        """记录 _init 结束状态（正常/异常），避免 task 异常被静默吞掉。"""
        if task.cancelled():
            logger.debug("网易云日志监听启动任务已取消")
        elif task.exception() is not None:
            logger.warning(
                "网易云日志监听启动任务异常", exc_info=task.exception()
            )
        else:
            logger.debug("网易云日志监听启动任务正常结束")

    async def _init(self) -> None:
        try:
            cm = AsyncCloudMusic()
            # 先注册回调（依赖库会将回调调度回事件循环线程）
            cm.on_track_change(self._on_track_change)
            cm.on_state_change(self._on_state_change)
            # 记录 elog 路径与大小，便于定位"启动后无任何反应"类问题
            try:
                elog_path = cm._listener.file_path
                logger.info("网易云 elog 路径：%s", elog_path)
                import os
                logger.info(
                    "网易云 elog 大小：%s",
                    f"{os.path.getsize(elog_path) / 1024 / 1024:.1f} MB" if os.path.exists(elog_path) else "不存在",
                )
            except Exception:
                pass
            # 加超时保护：cm.start() 内部是 to_thread 回溯整个 elog，
            # 超大文件时可能耗时很长，超时则降级到 SMTC 语义并给出明确日志
            await asyncio.wait_for(cm.start(), timeout=20)
        except asyncio.TimeoutError:
            logger.warning(
                "网易云日志监听启动超时（elog 回溯 > 20s），放弃日志适配器"
            )
            return
        except Exception:
            logger.warning("启动网易云日志监听失败", exc_info=True)
            return
        self._cloud_music = cm
        # 推送初始快照（不触发回调）
        self._sync_state(notify=False)
        logger.info("网易云日志监听初始化完成")

    def stop(self) -> None:
        if self._cloud_music is not None:
            try:
                # stop() 内部为 to_thread 后台停止，不阻塞事件循环
                asyncio.get_event_loop().create_task(self._cloud_music.stop())
            except RuntimeError:
                pass
            self._cloud_music = None
        if self._task is not None:
            self._task.cancel()
            self._task = None
        logger.info("停止网易云日志监听：%s", self.player_name)
        return super().stop()

    # ---- 查询接口 ----
    def get_current_media(self) -> MediaInfo:
        """返回当前媒体快照 MediaInfo"""
        if self._cloud_music is None:
            return MediaInfo()
        return MediaInfo.from_playing_state(self._cloud_music.state)

    def get_progress(self) -> float | None:
        """返回当前播放进度（秒）。

        切歌瞬间依赖库尚未收到新的进度/状态事件，会把 position 误报为总时长
        （其内部 _relative_time 被重置为 0，min((now-0)/1000, duration) 恒等于
        duration）。此时返回 None 让上层忽略该无效进度，避免歌词闪跳到末尾。
        """
        if self._cloud_music is None:
            return None
        state = self._cloud_music.state
        duration = self._cloud_music.track.duration if self._cloud_music.track else 0
        if duration > 0 and state.position >= duration:
            logger.debug(
                "切歌瞬间进度无效（position=%ss ≈ 总时长=%ss），忽略",
                state.position,
                duration,
            )
            return None
        return state.position

    def get_duration(self) -> float | None:
        """返回总时长（秒）。"""
        if self._cloud_music is None or not self._cloud_music.track:
            return None
        return self._cloud_music.track.duration

    # ---- 内部实现 ----
    def _sync_state(self, notify: bool = True) -> None:
        """读取最新快照，通过统一的 _update_media 比对并分发事件。"""
        if self._cloud_music is None:
            return
        state = self._cloud_music.state
        logger.debug(
            "网易云日志快照：%s - %s，position=%s，duration=%s，%s",
            state.track.name,
            state.track.artist_str,
            state.position,
            state.track.duration,
            "播放" if state.is_playing else "暂停",
        )
        self._update_media(
            MediaInfo.from_playing_state(state),
            notify=notify,
        )

    def _on_track_change(self, track) -> None:
        """切歌回调（可能在其他线程触发，切回主事件循环）。"""
        self._call_on_main(self._sync_state)

    def _on_state_change(self, state) -> None:
        """播放/暂停回调（可能在其他线程触发，切回主事件循环）。"""
        self._call_on_main(self._sync_state)


def select_fetcher(player_name: str, callback: callable = None, settings: Dict = None, netease_adapter: bool = True) -> Fetcher:
    """根据播放器名称选择合适的Fetcher实现"""
    if player_name.lower() == "网易云音乐" and netease_adapter:
        logger.info("播放器 %s 使用网易云日志 Fetcher", player_name)
        return FetcherByCMLog(player_name, callback, settings)
    else:
        logger.info("播放器 %s 使用 SMTC Fetcher", player_name)
        return FetcherBySMTC(player_name, callback, settings)


async def list_smtc_sessions() -> list:
    """枚举当前系统 SMTC 会话，返回各会话的 source_app_user_model_id 列表。

    供添加播放器时从活跃会话中选择使用；无会话或读取失败时返回空列表。
    """
    try:
        manager: GlobalSystemMediaTransportControlsSessionManager = (
            await GlobalSystemMediaTransportControlsSessionManager.request_async()
        )
        sessions = list(manager.get_sessions())
        return [s.source_app_user_model_id for s in sessions if s.source_app_user_model_id]
    except Exception:
        logger.debug("枚举 SMTC 会话失败", exc_info=True)
        return []


@lru_cache(maxsize=16)
def _compile_inst_regex(patterns_tuple) -> "re.Pattern":
    return re.compile("|".join(patterns_tuple), re.IGNORECASE)


def is_pure_music(song: str, artist: str = "", patterns=None) -> bool:
    """判断歌曲是否为纯音乐/伴奏（按歌名/歌手特征匹配）。
    patterns 为 None 时使用默认规则；传入列表则完全按用户规则匹配（空列表表示不过滤）。
    """
    if patterns is None:
        patterns = DEFAULT_INST_PATTERNS
    text = f"{song} {artist}".strip()
    if not text or not patterns:
        return False
    return bool(_compile_inst_regex(tuple(patterns)).search(text))
__ALL__ = [
    "MediaInfo",
    "FetcherEvent",
    "MediaChange",
    "Fetcher",
    "FetcherBySMTC",
    "FetcherByCMLog",
    "select_fetcher",
    "list_smtc_sessions",
    "is_pure_music",
]