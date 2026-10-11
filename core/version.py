"""
应用版本号模块

本文件是应用版本的唯一事实来源（Single Source of Truth）：
- 发版时修改 APP_VERSION 并打同名 git tag（如 v3.0.1）；
- 运行时（源码/打包）均从这里读取，不使用 importlib.metadata
  （package = false 且 PyInstaller 打包后无 dist-info，都取不到）。
"""

# 应用版本，与 git tag（去掉 v 前缀）保持一致
APP_VERSION = "3.0.0"

# 仓库地址（更新检查 API 与 Release 页面均基于此派生）
REPO_OWNER = "YouRanCoder"
REPO_NAME = "LimbusLyricSimulator"

# GitHub Releases 最新版查询接口
RELEASE_API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"

# API 直连失败时的国内镜像候选（前缀拼接在 RELEASE_API_URL 之前）。
# 仅保留实测能返回 JSON 的镜像；ghproxy.cn/ghfast.top 等对 api.github.com
# 会返回 HTML 页或超时，故不列入。顺序即尝试顺序，直连永远优先。
RELEASE_API_MIRRORS = [
    "https://gh-proxy.com/",
]
