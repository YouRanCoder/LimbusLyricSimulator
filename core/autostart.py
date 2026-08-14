"""
开机自启动管理

通过 Windows 注册表 HKCU Run 键实现（当前用户，无需管理员权限）。
启动命令用 cmd /s /c 显式固定工作目录到项目根目录，
避免开机时工作目录不对导致配置/日志写错位置。
"""

import os
import sys
from logging import getLogger

logger = getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "LimbusLyricSimulator"


def get_startup_command() -> str:
    """构造开机启动命令：固定工作目录后调用 pythonw.exe（不弹黑窗）"""
    exe = sys.executable
    pythonw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if not os.path.isfile(pythonw):
        pythonw = exe
    script = os.path.abspath(sys.argv[0])
    project_dir = os.path.dirname(script)
    inner = f'cd /d "{project_dir}" && "{pythonw}" "{script}"'
    return f'cmd /s /c "{inner}"'


def is_autostart_enabled() -> bool:
    """查询注册表 Run 键中是否已注册本程序"""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except OSError:
        return False


def set_autostart(enabled: bool) -> bool:
    """设置或取消开机自启动，返回是否成功"""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, get_startup_command())
                logger.info("已开启开机自启动")
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
                logger.info("已关闭开机自启动")
        return True
    except OSError as e:
        logger.warning("设置开机自启动失败：%s", e)
        return False