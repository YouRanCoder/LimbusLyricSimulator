"""
播放器管理模块

负责播放器的创建、切换和生命周期管理，包括：
- 根据播放器名称创建对应的 Fetcher 实例
- 管理播放器切换时的资源释放和重建
- 维护当前播放器配置

将播放器管理逻辑从 UI 层分离，使控制面板不需要关心具体的 Fetcher 实现细节。
"""

from typing import Optional, Callable, Dict, Any
from core.fetcher import Fetcher, select_fetcher, MediaChange
from logging import getLogger
logger = getLogger(__name__)

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
        media_changed_callback: Optional[Callable[[MediaChange], None]] = None,
        error_callback: Optional[Callable[[str], None]] = None
    ):
        """
        初始化播放器管理器
        
        Args:
            players_config: 播放器配置字典，格式为 {播放器名称: {process: SMTC 会话标识}}
            media_changed_callback: 媒体变化回调函数，签名为 callback(change: MediaChange)
            error_callback: 初始化失败上报回调，签名为 callback(reason: str)
        """
        self.players_config = players_config
        self.media_changed_callback = media_changed_callback
        self.error_callback = error_callback
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
    
    def switch_player(self, player_name: str, netease_adapter: bool = True, force: bool = False) -> None:
        """
        切换到指定播放器
        
        会先停止当前播放器，然后创建并启动新的 Fetcher。
        
        Args:
            player_name: 要切换到的播放器名称
            netease_adapter: 网易云音乐是否使用日志适配器（False 时退化为 SMTC）
            force: 是否强制重建 Fetcher（适配方式切换时需要）
        """
        # 如果已经是当前播放器，不需要切换
        if not force and player_name == self._current_player_name and self._current_fetcher is not None:
            logger.debug("播放器 %s 已是当前播放器，无需切换", player_name)
            return
        
        # 停止当前播放器
        self.stop_current()
        logger.info("切换到播放器：%s", player_name)
        # 创建新的 Fetcher
        self._current_fetcher = select_fetcher(
            player_name, self.media_changed_callback, self.players_config, netease_adapter,
            self.error_callback,
        )
        self._current_player_name = player_name
    
    def start_current(self) -> None:
        """启动当前播放器"""
        if self._current_fetcher is not None:
            logger.info("启动播放器监听：%s", self._current_player_name)
            self._current_fetcher.start()
    
    def stop_current(self) -> None:
        """停止当前播放器"""
        if self._current_fetcher is not None:
            logger.info("停止播放器监听：%s", self._current_player_name)
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
    
    def add_player(self, name: str, process: str) -> None:
        """
        添加自定义播放器配置
        
        Args:
            name: 播放器名称
            process: SMTC 会话标识（如 kugou）
        """
        self.players_config[name] = {
            "process": process
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
                logger.info("当前播放器 %s 已被删除，已清空当前状态", name)
            return True
        logger.warning("删除播放器 %s 失败：不存在", name)
        return False
    
    def get_player_names(self) -> list:
        """获取所有可用的播放器名称列表"""
        return list(self.players_config.keys())
