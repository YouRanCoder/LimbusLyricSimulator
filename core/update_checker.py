"""
版本更新检查模块

通过 GitHub Releases API 检查最新版本，与本地版本比较，
提供更新日志与 Release 页面链接。纯业务逻辑，不依赖 Qt/UI。

流程：
UI 发起检查 → AppController 调 check_for_update() → 结果通过信号返回 UI 弹窗。
"""

from dataclasses import dataclass
import logging
import re
from typing import Optional

import httpx

from core.version import (
    APP_VERSION,
    RELEASE_API_MIRRORS,
    RELEASE_API_URL,
    REPO_OWNER,
    REPO_NAME,
)

logger = logging.getLogger(__name__)

# 请求超时（秒）：检查更新是低频操作，留足余量又不至于卡住弹窗
_REQUEST_TIMEOUT = 10.0


@dataclass
class UpdateCheckResult:
    """版本检查结果，供 UI 层展示"""
    # 是否发现新版本
    has_update: bool
    # 本地当前版本
    current_version: str
    # 最新发布版本（比较失败/网络异常时为 None）
    latest_version: Optional[str] = None
    # 更新日志（Release 描述原文，可能为空）
    changelog: str = ""
    # Release 页面链接（引导用户自行下载）
    release_url: str = ""
    # 简短错误说明（网络失败/限流等，None 表示正常）
    error: Optional[str] = None


def compare_versions(local: str, remote: str) -> int:
    """比较两个版本号（支持 v 前缀，按数字段逐段比较）

    Args:
        local: 本地版本号，如 "3.0.0"
        remote: 远端版本号，如 "v3.1.0"

    Returns:
        1: remote 更新；-1: local 更新；0: 相同。
        数字段补零对齐比较（"3.0" 与 "3.0.0" 视为相等）。
    """
    def parse(ver: str) -> list:
        # 剥掉 v 前缀与预发布后缀（如 -beta.1），只留数字段
        core = re.sub(r"^[vV]", "", ver.strip()).split("-")[0]
        return [int(p) for p in re.findall(r"\d+", core)]

    a, b = parse(local), parse(remote)
    for i in range(max(len(a), len(b))):
        pa = a[i] if i < len(a) else 0
        pb = b[i] if i < len(b) else 0
        if pa != pb:
            return 1 if pb > pa else -1
    return 0


async def check_for_update() -> UpdateCheckResult:
    """请求 GitHub Releases API 检查最新版本（不下载，仅返回信息供用户自行下载）

    直连失败（超时/连接错误，国内常见）时依次尝试国内镜像；
    所有渠道均失败时降级为带 error 的结果，不向外抛出。
    """
    urls = [RELEASE_API_URL] + [m + RELEASE_API_URL for m in RELEASE_API_MIRRORS]
    last_error = "网络连接失败，请检查网络"

    for url in urls:
        data = await _fetch_release_json(url)
        if data is None:
            continue
        return _build_result((data.get("tag_name") or "").strip(), data)

    return UpdateCheckResult(
        has_update=False, current_version=APP_VERSION, error=last_error,
    )


async def _fetch_release_json(url: str) -> Optional[dict]:
    """从单个渠道（直连或镜像）获取 Release JSON，失败返回 None

    - 4xx（限流等）：换渠道大概率同样失败，但保留重试链统一处理；
    - 超时/连接错误/响应非 JSON：网络问题，换下一个渠道重试。
    """
    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT, follow_redirects=True
        ) as client:
            resp = await client.get(
                url, headers={"Accept": "application/vnd.github+json"}
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        # GitHub 403 限流（未认证 60 次/小时/IP）等状态码问题
        logger.warning("版本检查失败（%s）：HTTP %d", _channel_label(url), e.response.status_code)
        return None
    except (httpx.TimeoutException, httpx.TransportError) as e:
        # 超时/连接错误：网络问题，换下一个渠道重试
        logger.warning("版本检查失败（%s）：%s", _channel_label(url), e)
        return None
    except ValueError:
        # JSON 解析失败：镜像可能返回 HTML 页，换下一个渠道
        logger.warning("版本检查失败（%s）：响应非 JSON", _channel_label(url))
        return None


def _channel_label(url: str) -> str:
    """日志用渠道标签：区分直连与镜像"""
    return "直连" if url == RELEASE_API_URL else "镜像"


def _build_result(tag: str, data: dict) -> UpdateCheckResult:
    """由 Release 响应构造检查结果"""
    if not tag:
        logger.warning("版本检查失败：Release 数据缺少 tag_name")
        return UpdateCheckResult(
            has_update=False, current_version=APP_VERSION, error="远端版本数据无效",
        )
    latest = tag.lstrip("vV")
    release_url = data.get("html_url") or f"https://github.com/{REPO_OWNER}/{REPO_NAME}/releases"
    changelog = (data.get("body") or "").strip()
    has_update = compare_versions(APP_VERSION, latest) > 0

    logger.info(
        "版本检查完成：本地 %s，远端 %s，%s",
        APP_VERSION, latest, "发现新版本" if has_update else "已是最新",
    )
    return UpdateCheckResult(
        has_update=has_update,
        current_version=APP_VERSION,
        latest_version=latest,
        changelog=changelog,
        release_url=release_url,
    )
