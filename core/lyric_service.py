"""
歌词服务模块

负责歌词获取的业务逻辑，包括：
- 从播放器获取当前歌曲信息
- 从歌词源搜索歌词
- 处理手动输入兜底逻辑

将业务逻辑从 UI 层分离，使控制面板只负责界面交互。
"""

from dataclasses import dataclass
from typing import Optional, Tuple
from core.fetcher import MediaInfo
from core.search_engine import LyricSearchEngine
from logging import getLogger

logger = getLogger(__name__)

@dataclass
class LyricResult:
    """歌词获取结果"""
    lyric: str = ""
    duration_ms: int = 0
    song: str = ""
    artist: str = ""
    
    @property
    def success(self) -> bool:
        return bool(self.lyric)


class LyricService:
    """
    歌词服务
    
    封装歌词获取的完整流程，包括：
    1. 从播放器获取当前媒体信息
    2. 如果获取失败，提供手动输入兜底
    3. 从指定歌词源搜索歌词
    4. 返回歌词文本和时长信息
    """
    
    def __init__(self, fetcher):
        """
        初始化歌词服务
        
        Args:
            fetcher: 播放器获取器实例，需实现 get_current_media() 方法
        """
        self.fetcher = fetcher
    
    def get_current_media_info(self) -> MediaInfo:
        """
        获取当前播放的媒体信息
        
        Returns:
            MediaInfo: 当前媒体信息快照
        """
        info = self.fetcher.get_current_media()
        logger.debug("获取当前媒体信息：%s - %s", info.song, info.artist)
        return info
    
    async def search_lyric(
        self, 
        song: str, 
        artist: str, 
        source: str, 
        trans_only: bool = False
    ) -> Tuple[Optional[str], int]:
        """
        从指定歌词源异步搜索歌词
        
        Args:
            song: 歌曲名称
            artist: 歌手名称
            source: 歌词源名称（如"网易云"、"QQ音乐"、"酷狗"）
            trans_only: 是否仅获取翻译歌词
            
        Returns:
            Tuple[Optional[str], int]: (歌词文本, 时长毫秒)
        """
        return await LyricSearchEngine.search(song, artist, source, trans_only)
    
    async def fetch_lyric_with_fallback(
        self,
        source: str,
        trans_only: bool,
        manual_input_callback=None
    ) -> LyricResult:
        """
        异步获取当前播放的歌词，支持手动输入兜底
        
        流程：
        1. 尝试从播放器获取当前歌曲信息
        2. 如果获取失败，调用 manual_input_callback 让用户手动输入
        3. 从指定歌词源搜索歌词
        4. 返回结果
        
        Args:
            source: 歌词源名称
            trans_only: 是否仅获取翻译歌词
            manual_input_callback: 手动输入回调函数，返回 (song, artist) 或 None
            
        Returns:
            LyricResult: 歌词获取结果
        """
        # 1. 获取当前媒体信息
        info = self.get_current_media_info()
        song, artist = info.song, info.artist
        logger.info("获取歌词流程启动：歌曲=%s，歌手=%s，来源=%s，仅翻译=%s",
                    song, artist, source, trans_only)
        
        # 2. 如果获取失败，尝试手动输入
        if not info.has_track:
            logger.warning("未能自动获取歌曲信息，尝试手动输入")
            if manual_input_callback:
                result = manual_input_callback()
                if result is None:
                    # 用户取消输入
                    logger.info("用户取消手动输入")
                    return LyricResult()
                song, artist = result
                logger.info("手动输入歌曲信息：%s - %s", song, artist)
            else:
                # 没有提供回调函数，直接返回空结果
                logger.warning("未提供手动输入回调，返回空结果")
                return LyricResult()
        
        # 3. 搜索歌词
        lyric, duration = await self.search_lyric(song, artist, source, trans_only)
        
        # 4. 构建结果
        # 优先使用播放器上报的真实时长，否则用搜索接口返回的时长
        duration_ms = info.duration_ms if info.duration > 0 else duration
        logger.info("歌词获取完成：找到=%s，时长=%dms", bool(lyric), duration_ms)
        
        return LyricResult(
            lyric=lyric or "",
            duration_ms=duration_ms,
            song=song,
            artist=artist
        )
