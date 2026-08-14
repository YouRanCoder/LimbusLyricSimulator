import sys
import asyncio
import logging

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QtMsgType, qInstallMessageHandler
import qasync

from config.logging_setup import setup_logging
from core.settings_manager import SettingsManager
from core.app_controller import AppController
from ui.control_panel import ControlPanel
from ui.lyric_window import LyricWindow

logger = logging.getLogger(__name__)


def qt_message_handler(mode, context, message):
    """Qt 运行时消息（警告/错误等）统一转发到日志系统"""
    qt_logger = logging.getLogger("Qt")
    if mode == QtMsgType.QtInfoMsg:
        qt_logger.info("%s", message)
    elif mode == QtMsgType.QtWarningMsg:
        qt_logger.warning("%s", message)
    elif mode == QtMsgType.QtCriticalMsg:
        qt_logger.critical("%s", message)
    elif mode == QtMsgType.QtFatalMsg:
        qt_logger.fatal("%s", message)
    else:
        qt_logger.debug("%s", message)


if __name__ == "__main__":
    # 0. 初始化日志（控制台 + log/ 目录下按日期时间命名的日志文件）
    log_file = setup_logging()
    logger.info("程序启动，日志文件：%s", log_file)

    app = QApplication(sys.argv)
    qInstallMessageHandler(qt_message_handler)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    try:
        # 1. 创建配置管理器
        settings = SettingsManager()
        settings.load()
        logger.info("配置加载完成")

        # 2. 创建歌词窗口（UI 层）
        lyric_window = LyricWindow()
        lyric_window.show()

        # 3. 创建应用控制器（业务协调层）
        controller = AppController(settings=settings)

        # 4. 创建控制面板（UI 层），注入控制器
        panel = ControlPanel(controller=controller)
        panel.show()

        # 5. 将 UI 注册到控制器
        controller.set_ui(panel, lyric_window)
        logger.info("界面初始化完成")
    except Exception:
        logger.critical("程序初始化失败", exc_info=True)
        raise

    with loop:
        loop.run_forever()