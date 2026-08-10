import sys
from ui.control_panel import ControlPanel
from PyQt5.QtWidgets import QApplication
import asyncio
import qasync
import logging
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s:%(name)s:%(message)s')
if __name__ == "__main__":
    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    panel = ControlPanel()
    panel.show()
    with loop:
        loop.run_forever()