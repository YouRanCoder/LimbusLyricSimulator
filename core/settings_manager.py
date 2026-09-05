"""
设置管理器模块

负责配置的读取、保存、验证，完全不知道 UI 的存在。
提供统一的配置管理接口，使业务层和 UI 层都能通过它获取/保存配置。
"""

import os
import json
from typing import Dict, Any, Optional
from logging import getLogger
from config.manage import load_all_config, save_all_config, DEFAULT_PLAYERS
from config.settings import DEFAULT_PRESETS, DEFAULT_INST_PATTERNS, DEFAULT_CREDIT_PATTERNS

logger = getLogger(__name__)


class SettingsManager:
    """
    配置管理器
    
    负责：
    1. 从文件加载配置
    2. 保存配置到文件
    3. 提供配置的读写接口
    4. 管理预设和播放器配置
    """
    
    def __init__(self):
        self._settings: Dict[str, Any] = {}
        self._presets: Dict[str, Any] = {}
        self._players: Dict[str, Any] = {}
        self._loaded = False
    
    def load(self) -> None:
        """从文件加载配置"""
        data = load_all_config()
        self._settings = data.get('settings', {})
        self._presets = data.get('presets', dict(DEFAULT_PRESETS))
        self._players = data.get('players', dict(DEFAULT_PLAYERS))
        self._loaded = True
        logger.info(
            "配置加载完成：settings=%d 项, presets=%d 个, players=%d 个",
            len(self._settings), len(self._presets), len(self._players),
        )
    
    def save(self) -> None:
        """保存当前配置到文件"""
        save_all_config(self._settings, self._presets, self._players)
        logger.info("配置已保存")
    
    # ---- Settings 读写 ----
    
    def get_setting(self, key: str, default: Any = None) -> Any:
        """获取设置值"""
        return self._settings.get(key, default)
    
    def set_setting(self, key: str, value: Any) -> None:
        """设置值"""
        self._settings[key] = value
    
    def get_all_settings(self) -> Dict[str, Any]:
        """获取所有设置"""
        return dict(self._settings)
    
    def update_settings(self, settings_dict: Dict[str, Any]) -> None:
        """批量更新设置"""
        self._settings.update(settings_dict)
    
    # ---- Presets 管理 ----
    
    def get_presets(self) -> Dict[str, Any]:
        """获取所有预设"""
        return dict(self._presets)
    
    def get_preset(self, name: str) -> Optional[Dict[str, Any]]:
        """获取指定预设"""
        return self._presets.get(name)
    
    def add_preset(self, name: str, preset_data: Dict[str, Any]) -> bool:
        """
        添加预设
        
        Returns:
            bool: 是否添加成功（名称不重复）
        """
        if name in self._presets:
            logger.warning("预设 %s 已存在，添加失败", name)
            return False
        self._presets[name] = preset_data
        logger.info("已添加预设 %s", name)
        return True
    
    def delete_preset(self, name: str) -> bool:
        """
        删除预设
        
        Returns:
            bool: 是否删除成功
        """
        if name in self._presets and len(self._presets) > 1:
            del self._presets[name]
            logger.info("已删除预设 %s", name)
            return True
        logger.warning("删除预设 %s 失败（不存在或为最后一个预设）", name)
        return False
    
    def get_preset_names(self) -> list:
        """获取所有预设名称"""
        return list(self._presets.keys())
    
    # ---- Players 管理 ----
    
    def get_players(self) -> Dict[str, Any]:
        """获取所有播放器配置"""
        return dict(self._players)
    
    def add_player(self, name: str, process: str, support_progress: bool = True) -> bool:
        """
        添加播放器配置
        
        Returns:
            bool: 是否添加成功（名称不重复）
        """
        if name in self._players:
            logger.warning("播放器 %s 已存在，添加失败", name)
            return False
        self._players[name] = {
            "process": process,
            "support_progress": support_progress,
        }
        logger.info("已添加播放器 %s（进程 %s，进度支持 %s）", name, process, support_progress)
        return True
    
    def update_player(self, name: str, new_name: str, process: str,
                      support_progress: bool = True) -> bool:
        """
        修改播放器配置（支持重命名、重新绑定会话、调整是否支持同步进度）
        
        Returns:
            bool: 是否修改成功（不存在或新名称被占用时失败）
        """
        if name not in self._players:
            logger.warning("修改播放器 %s 失败：不存在", name)
            return False
        if new_name != name and new_name in self._players:
            logger.warning("修改播放器 %s 失败：新名称 %s 已存在", name, new_name)
            return False
        self._players.pop(name)
        self._players[new_name] = {
            "process": process,
            "support_progress": support_progress,
        }
        logger.info("已修改播放器 %s -> %s（进程 %s，进度支持 %s）",
                    name, new_name, process, support_progress)
        return True
    
    def delete_player(self, name: str) -> bool:
        """
        删除播放器配置
        
        Returns:
            bool: 是否删除成功
        """
        if name in self._players and len(self._players) > 1:
            del self._players[name]
            logger.info("已删除播放器 %s", name)
            return True
        logger.warning("删除播放器 %s 失败（不存在或为最后一个播放器）", name)
        return False
    
    def get_player_names(self) -> list:
        """获取所有播放器名称"""
        return list(self._players.keys())
    
    # ---- 默认值 ----
    
    @staticmethod
    def get_default_settings() -> Dict[str, Any]:
        """获取默认设置值"""
        return {
            'text_color': '#fffeef',
            'stroke_color': '#d8a523',
            'glow_color': '#d8a523',
            'glow_enabled': True,
            'glow_size': 4,
            'glow_alpha': 82,
            'trans_only': False,
            # 中英双语同时演出：勾选后原始歌词与翻译歌词同时显示（默认关闭）
            'bilingual_mode': False,
            # 渲染模式：'auto'=按句判定（CJK→阴影式/纯拉丁→描边式），'chinese'/'english'=强制统一
            'mode': 'auto',
            'font_family': 'Microsoft YaHei',
            'font_size': 28,
            'stroke_width': 0.5,
            'spacing': 5.0,
            'shake_intensity': 2,
            'shake_speed': 143,
            'fade_speed': 12,
            'rise_speed': 1,
            'margin_time': 4000,
            'max_interval': 16000,
            'max_duration': 5000,
            'angle_min': -10,
            'angle_max': 10,
            'pos_x_min': 5,
            'pos_x_max': 85,
            'pos_y_min': 5,
            'pos_y_max': 75,
            'opacity': 100,
            'allowed_region': None,
            'player': '网易云音乐',
            'source': '网易云',
            # 防捕获（独立 Overlay）：开启后录屏/直播软件捕获不到歌词层
            'exclude_from_capture': False,
            'netease_adapter_enabled': True,
            'filter_pure_music': True,
            'inst_patterns': list(DEFAULT_INST_PATTERNS),
            'filter_credits': True,
            'credit_patterns': list(DEFAULT_CREDIT_PATTERNS),
            'perspective_enabled': True,
            'persp_x_strength': 5,
            'persp_y_strength': 30,
            'persp_compensation': 3,
        }
