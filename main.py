import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer
import asyncio
import qasync
import logging

from core.settings_manager import SettingsManager
from core.app_controller import AppController
from ui.control_panel import ControlPanel
from ui.lyric_window import LyricWindow

logging.basicConfig(level=logging.DEBUG, format='%(levelname)s:%(name)s:%(message)s')

if __name__ == "__main__":
    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    # 1. 创建配置管理器
    settings = SettingsManager()
    
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
    
    with loop:
        loop.run_forever()