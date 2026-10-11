"""
网易云 elog 清理模块

清理网易云音乐客户端的 cloudmusic.elog 日志文件（启动后不断膨胀，
部分机器上会导致网易云卡顿，也拖慢本程序的日志回溯）。

纯业务逻辑，不依赖 Qt/UI：
UI 发起清理 → AppController 调 clear_netease_elog() → 结果随信号返回 UI 提示。
"""

from dataclasses import dataclass
import logging
import os
from typing import Optional

from cloudmusic_detector.api import CLOUDMUSIC_ELOG_PATH

logger = logging.getLogger(__name__)


@dataclass
class ElogClearResult:
    """elog 清理结果，供 UI 层提示"""
    # 是否清理成功
    success: bool
    # 释放的空间（字节），失败时为 None
    freed_bytes: Optional[int] = None
    # 失败原因（成功时为 None）
    error: Optional[str] = None

    @property
    def freed_mb(self) -> str:
        """释放空间的可读描述（MB，保留 1 位小数）"""
        return f"{(self.freed_bytes or 0) / 1024 / 1024:.1f} MB"


def get_netease_elog_path() -> str:
    """返回网易云 elog 文件路径（与依赖库的默认路径保持一致）"""
    return CLOUDMUSIC_ELOG_PATH


def get_netease_elog_size() -> int:
    """返回 elog 文件大小（字节），不存在时返回 0"""
    try:
        return os.path.getsize(CLOUDMUSIC_ELOG_PATH)
    except OSError:
        return 0


def clear_netease_elog() -> ElogClearResult:
    """清理网易云 elog 文件

    策略：直接删除文件（网易云客户端会在下次写入时自动重建）。
    文件被网易云占用导致删除失败时返回失败原因，不做粗暴重试。

    注意：清理前应停止网易云日志监听（fetcher 持有文件句柄且正在轮询），
    由调用方（AppController）负责协调，本函数只管文件本身。
    """
    if not os.path.exists(CLOUDMUSIC_ELOG_PATH):
        logger.info("网易云 elog 不存在，无需清理：%s", CLOUDMUSIC_ELOG_PATH)
        return ElogClearResult(success=True, freed_bytes=0)

    size = get_netease_elog_size()
    try:
        os.remove(CLOUDMUSIC_ELOG_PATH)
    except PermissionError:
        logger.warning("清理网易云 elog 失败：文件被占用（网易云可能正在运行）")
        return ElogClearResult(
            success=False,
            error="文件被网易云音乐占用，请先完全退出网易云音乐（含托盘图标）再清理",
        )
    except OSError as e:
        logger.warning("清理网易云 elog 失败：%s", e)
        return ElogClearResult(success=False, error=f"删除失败：{e}")

    logger.info("网易云 elog 清理完成，释放 %.1f MB", size / 1024 / 1024)
    return ElogClearResult(success=True, freed_bytes=size)
