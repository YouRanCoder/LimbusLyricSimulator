import sys
import asyncio
import logging

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer, QtMsgType, qInstallMessageHandler
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

        # 2. 创建歌词窗口（UI 层），先显示让首帧尽快渲染
        lyric_window = LyricWindow()
        lyric_window.show()
        # 同步处理 show 事件，强制完成首帧绘制，避免之后构建控制面板时
        # 窗口尚未渲染（Windows 上未完成首次绘制的透明窗会显示白色占位）
        app.processEvents()

        # 3. 创建应用控制器（业务协调层）
        controller = AppController(settings=settings)

        # 4. 控制面板延迟到事件循环启动后构建：
        #    控件构造时存在一次性字体度量初始化（本机约 0.5s），若在事件循环
        #    启动前同步构建，会阻塞首帧渲染导致启动白屏。先显示歌词窗口，
        #    再进入事件循环渲染首帧，最后异步构建控制面板。
        def _create_panel():
            panel = ControlPanel(controller=controller)
            panel.show()
            controller.set_ui(panel, lyric_window)
            logger.info("界面初始化完成")

        QTimer.singleShot(0, _create_panel)
    except Exception:
        logger.critical("程序初始化失败", exc_info=True)
        raise

    with loop:
        loop.run_forever()