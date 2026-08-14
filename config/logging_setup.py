"""
日志配置模块

统一配置全局日志系统：
- 同时输出到控制台和 log/ 目录下的日志文件
- 日志文件名包含日期时间（如 app_20260814_153012.log），
  方便用户反馈问题时直接提供对应时段的日志文件
- 捕获未处理的 Python 异常并写入日志，避免崩溃信息丢失
"""

import logging
import logging.handlers
import sys
from datetime import datetime
from pathlib import Path

LOG_DIR_NAME = "log"

# 控制台日志格式：保持简短，便于开发调试
_CONSOLE_FORMAT = "%(levelname)s:%(name)s:%(message)s"
# 文件日志格式：包含完整时间戳与日志来源，便于定位问题
_FILE_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False
_log_file_path: Path = Path()


def get_log_dir() -> Path:
    """返回日志目录（打包环境下位于可执行文件旁，否则位于项目根目录下）"""
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent.parent
    return base / LOG_DIR_NAME


def get_log_file_path() -> Path:
    """返回当前日志文件的完整路径"""
    return _log_file_path


def setup_logging(level: int = logging.DEBUG) -> Path:
    """
    初始化日志系统（幂等，多次调用只生效一次）。

    输出：
    - 控制台（便于开发调试）
    - log/ 目录下按日期时间命名的日志文件（便于用户反馈问题）

    Args:
        level: 根日志级别，默认 DEBUG

    Returns:
        Path: 当前日志文件的完整路径
    """
    global _configured, _log_file_path
    if _configured:
        return _log_file_path

    log_dir = get_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    # 按日期时间生成日志文件名
    file_name = datetime.now().strftime("app_%Y%m%d_%H%M%S.log")
    _log_file_path = log_dir / file_name

    root = logging.getLogger()
    root.setLevel(level)

    # 文件输出（UTF-8 编码，避免中文乱码；防止单文件过大）
    file_handler = logging.handlers.RotatingFileHandler(
        _log_file_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(_FILE_FORMAT, datefmt=_DATE_FORMAT))
    root.addHandler(file_handler)

    # 第三方库 DEBUG 日志噪音极大：qasync 会在 submit 时把 to_thread 的回调
    # 参数整体格式化（例如整个 elog 文件内容），在 UI 线程上构建巨型字符串，
    # 导致启动白屏 0.5s，日志文件也瞬间被写满 10MB。统一降到 WARNING。
    for noisy in (
        "qasync",      # 线程池 submit 参数格式化（阻塞 UI + 日志暴涨）
        "asyncio",     # proactor/事件循环内部 DEBUG
        "winrt",       # SMTC 底层包装
        "aiohttp",     # 歌词搜索 HTTP 客户端
        "urllib3",     # aiohttp 底层连接池
        "charset_normalizer",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # 控制台输出（PyInstaller --windowed 打包后 stdout/stderr 为 None，此时跳过）
    if sys.stdout is not None:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(logging.Formatter(_CONSOLE_FORMAT))
        root.addHandler(console_handler)

    # Windows 控制台默认编码（如 GBK）可能无法编码部分字符导致崩溃，
    # 统一改为 UTF-8 并容错替换，确保日志输出不会因编码问题中断
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    # 捕获未处理异常
    _install_excepthook()

    _configured = True
    logging.getLogger(__name__).info("日志系统初始化完成，日志文件：%s", _log_file_path)
    return _log_file_path


def _install_excepthook() -> None:
    """安装全局异常钩子：将未捕获的异常写入日志，避免崩溃信息丢失"""

    def excepthook(exc_type, exc_value, exc_tb):
        logging.getLogger("uncaught").critical(
            "未捕获异常，程序即将退出", exc_info=(exc_type, exc_value, exc_tb)
        )
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = excepthook