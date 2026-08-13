"""
播放器管理模块

负责播放器的创建、切换和生命周期管理，包括：
- 根据播放器名称创建对应的 Fetcher 实例
- 管理播放器切换时的资源释放和重建
- 维护当前播放器配置

将播放器管理逻辑从 UI 层分离，使控制面板不需要关心具体的 Fetcher 实现细节。
"""

from typing import Optional, Callable, Dict, Any
from core.fetcher import Fetcher, FetcherBySMTC, MediaChange


class PlayerManager:
    """
    播放器管理器
    
    封装播放器的创建和切换逻辑，提供统一的接口给 UI 层使用。
    主要职责：
    1. 根据播放器名称创建对应的 Fetcher
    2. 管理 Fetcher 的生命周期（启动/停止）
    3. 在切换播放器时正确处理资源释放
    """
    
    def __init__(
        self, 
        players_config: Dict[str, Any],
        media_changed_callback: Optional[Callable[[MediaChange], None]] = None
    ):
        """
        初始化播放器管理器
        
        Args:
            players_config: 播放器配置字典，格式为 {播放器名称: {process: 进程名, pattern: 正则}}
            media_changed_callback: 媒体变化回调函数，签名为 callback(change: MediaChange)
        """
        self.players_config = players_config
        self.media_changed_callback = media_changed_callback
        self._current_fetcher: Optional[Fetcher] = None
        self._current_player_name: Optional[str] = None
    
    @property
    def current_fetcher(self) -> Optional[Fetcher]:
        """获取当前的 Fetcher 实例"""
        return self._current_fetcher
    
    @property
    def current_player_name(self) -> Optional[str]:
        """获取当前播放器名称"""
        return self._current_player_name
    
    def switch_player(self, player_name: str) -> None:
        """
        切换到指定播放器
        
        会先停止当前播放器，然后创建并启动新的 Fetcher。
        
        Args:
            player_name: 要切换到的播放器名称
        """
        # 如果已经是当前播放器，不需要切换
        if player_name == self._current_player_name and self._current_fetcher is not None:
            return
        
        # 停止当前播放器
        self.stop_current()
        
        # 创建新的 Fetcher
        self._current_fetcher = FetcherBySMTC(
            player_name=player_name,
            callback=self.media_changed_callback,
            settings=self.players_config,
        )
        self._current_player_name = player_name
    
    def start_current(self) -> None:
        """启动当前播放器"""
        if self._current_fetcher is not None:
            self._current_fetcher.start()
    
    def stop_current(self) -> None:
        """停止当前播放器"""
        if self._current_fetcher is not None:
            self._current_fetcher.stop()
    
    def get_current_media(self):
        """
        获取当前播放的媒体信息
        
        Returns:
            MediaInfo: 当前媒体信息，如果没有播放器则返回空的 MediaInfo
        """
        if self._current_fetcher is None:
            from core.fetcher import MediaInfo
            return MediaInfo()
        return self._current_fetcher.get_current_media()
    
    def add_player(self, name: str, process: str, pattern: str) -> None:
        """
        添加自定义播放器配置
        
        Args:
            name: 播放器名称
            process: 进程名（如 qqmusic.exe）
            pattern: 标题匹配正则
        """
        self.players_config[name] = {
            "process": process,
            "pattern": pattern
        }
    
    def delete_player(self, name: str) -> bool:
        """
        删除播放器配置
        
        Args:
            name: 要删除的播放器名称
            
        Returns:
            bool: 是否删除成功
        """
        if name in self.players_config:
            del self.players_config[name]
            # 如果删除的是当前播放器，清空当前状态
            if name == self._current_player_name:
                self.stop_current()
                self._current_fetcher = None
                self._current_player_name = None
            return True
        return False
    
    def get_player_names(self) -> list:
        """获取所有可用的播放器名称列表"""
        return list(self.players_config.keys())
