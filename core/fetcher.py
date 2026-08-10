from PyQt5.QtWidgets import QApplication, QInputDialog
from .search_engine import LyricSearchEngine
from config.settings import DEFAULT_PLAYERS
import subprocess, re, win32gui, win32process
import asyncio
from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
from winrt.windows.media.control import (GlobalSystemMediaTransportControlsSessionManager
)
import asyncio
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
#旧版的通过窗口标题获取歌曲信息的方式，仍然保留以兼容部分播放器
class LyricFetcher:
    @staticmethod
    def get_player_pid(player_name=None, players=None):
        if players is None:
            players = DEFAULT_PLAYERS
        if player_name and player_name in players:
            proc_name = players[player_name]["process"]
        else:
            return None
        try:
            result = subprocess.run(
                ['tasklist', '/fi', f'imagename eq {proc_name}', '/fo', 'csv', '/nh'],
                capture_output=True, text=True
            )
            for line in result.stdout.strip().split('\n'):
                if proc_name in line.lower():
                    pid = line.split(',')[1].strip('"')
                    return int(pid)
        except:
            pass
        return None
    @staticmethod
    def get_song_from_title(pid, player_name=None, players=None):
        if players is None:
            players = DEFAULT_PLAYERS
        pattern_str = r'^(.+?)\s*-\s*(.+)$'
        if player_name and player_name in players:
            pattern_str = players[player_name].get("pattern", pattern_str)
        pattern = re.compile(pattern_str)
        result = []
        def callback(hwnd, _):
            _, window_pid = win32process.GetWindowThreadProcessId(hwnd)
            if window_pid == pid and win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title and ' - ' in title and len(title) < 150:
                    result.append(title)
        win32gui.EnumWindows(callback, None)
        for title in result:
            match = pattern.match(title)
            if match:
                groups = match.groups()
                if len(groups) >= 2:
                    return groups[0].strip(), groups[1].strip()
                elif len(groups) == 1:
                    return groups[0].strip(), ""
        return None, None

    @staticmethod
    def fetch_and_set(panel):
        panel.status.setText("状态：正在获取当前播放...")
        QApplication.processEvents()
        player_name = panel.player_combo.currentText()
        players = panel.players
        pid = LyricFetcher.get_player_pid(player_name, players)
        song = None
        artist = None
        if pid:
            song, artist = LyricFetcher.get_song_from_title(pid, player_name, players)
        if not song:
            text, ok = QInputDialog.getText(
                panel, "手动输入",
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
                panel.status.setText("状态：已取消")
                return
        source = panel.source_combo.currentText()
        trans_only = panel.trans_check.isChecked()
        panel.status.setText(f"状态：从{source}搜索「{song}」...")
        QApplication.processEvents()
        lyric, duration = LyricSearchEngine.search(song, artist, source, trans_only)
        if lyric:
            panel.text_input.setPlainText(lyric)
            panel.lyric_window.song_duration = duration
            panel.status.setText(f"状态：已获取「{song}」的歌词 ")
        else:
            panel.status.setText("状态：未找到歌词，请尝试换源")


class SMTCWatcher:
    def __init__(self, callback=None):
        self.callback = callback
        self.session = None
        self.manager = None
        self._loop = None
        self._current_song = None
        self._current_artist = None

    def start(self):
        """在当前运行的事件循环中启动 SMTC 监听。

        必须在事件循环启动之后调用（例如 QTimer.singleShot(0, ...)），
        不能使用 asyncio.run()，否则临时循环一关闭，事件监听就失效了。
        """
        loop = asyncio.get_event_loop()
        return loop.create_task(self.init())

    def get_current_media(self):
        """返回当前播放的歌曲和歌手，如果没有播放则返回(None, None)"""
        return self._current_song, self._current_artist

    def get_current_song(self):
        return self._current_song

    def get_current_artist(self):
        return self._current_artist

    async def init(self):
        self._loop = asyncio.get_running_loop()
        self.manager = (
            await GlobalSystemMediaTransportControlsSessionManager
            .request_async()
        )
        self.session = (
            self.manager
            .get_current_session()
        )
        if not self.session:
            logger.warning("没有SMTC播放器")
            return
        # 注册歌曲变化事件
        self.session.add_media_properties_changed(
            self.on_media_changed
        )
        # 立即获取一次，但不触发回调（避免程序刚启动就自动开始播放）
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
        if not self.session:
            return

        # SMTC 事件触发时，媒体属性可能还没同步好，
        # 此时读到的仍是旧歌曲。先读一次，若与当前相同则稍等重试。
        info = await (
            self.session
            .try_get_media_properties_async()
        )
        song = info.title
        artist = info.artist
        if song == self._current_song and artist == self._current_artist:
            await asyncio.sleep(0.8)
            info = await (
                self.session
                .try_get_media_properties_async()
            )
            song = info.title
            artist = info.artist

        # 歌曲确实没变（重复事件），去重跳过
        if song == self._current_song and artist == self._current_artist:
            return

        self._current_song = song
        self._current_artist = artist
        logger.debug(
            "歌曲变化: %s - %s",
            song,
            artist
        )
        if self.callback and notify:
            self.callback(
                song,
                artist
            )
