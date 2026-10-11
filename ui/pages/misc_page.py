"""杂项页：版本更新检查、日志目录等低频维护功能"""

from qfluentwidgets import (
    CaptionLabel,
    FluentIcon,
    PushButton,
    SettingCardGroup,
)

from core.version import APP_VERSION
from core.elog_cleaner import get_netease_elog_size
from .base import make_scroll_page, switch_card, widget_card


class MiscPage:
    """杂项页（控件容器，不含任何业务逻辑）

    控件由 ControlPanel 统一连接 controller。
    """

    def __init__(self):
        self.page, self.vbox = make_scroll_page("miscPage")

        # 网易云 elog 大小标签初始值（未检测到/实际大小）
        size = get_netease_elog_size()
        elog_text = f"{size / 1024 / 1024:.1f} MB" if size else "未检测到"
        self._elog_size_bytes = size

        # ---- 版本与更新 ----
        self.version_label = CaptionLabel(f"当前版本 v{APP_VERSION}")
        version_card = widget_card(FluentIcon.INFO, "当前版本", self.version_label)

        self.update_btn = PushButton(FluentIcon.SYNC, "检查更新")
        self.update_btn.setMinimumWidth(120)
        update_card = widget_card(FluentIcon.UPDATE, "检查更新", self.update_btn,
                                  "查询 GitHub 最新版本，发现新版本时展示更新日志")
        self.auto_update_check_card, self.auto_update_check = switch_card(
            FluentIcon.CLOUD, "启动时自动检查更新",
            "程序启动后联网检查 GitHub 最新版本，仅发现新版本时弹窗提醒",
            checked=True)

        update_group = SettingCardGroup("版本更新", self.page)
        update_group.addSettingCard(version_card)
        update_group.addSettingCard(update_card)
        update_group.addSettingCard(self.auto_update_check_card)

        # ---- 日志 ----
        self.open_log_btn = PushButton(FluentIcon.FOLDER, "打开目录")
        self.open_log_btn.setMinimumWidth(120)
        log_card = widget_card(FluentIcon.DOCUMENT, "运行日志", self.open_log_btn,
                               "日志位于程序目录下的 log 文件夹，反馈问题请附上 latest.log")

        self.elog_label = CaptionLabel(elog_text)
        elog_size_card = widget_card(FluentIcon.INFO, "网易云日志大小", self.elog_label,
                                     "cloudmusic.elog 过大会拖慢网易云与歌词同步")
        self.elog_clean_btn = PushButton(FluentIcon.BROOM, "清理")
        self.elog_clean_btn.setMinimumWidth(120)
        elog_clean_card = widget_card(FluentIcon.DELETE, "清理网易云日志", self.elog_clean_btn)

        log_group = SettingCardGroup("日志", self.page)
        log_group.addSettingCard(log_card)
        log_group.addSettingCard(elog_size_card)
        log_group.addSettingCard(elog_clean_card)

        self.vbox.addWidget(update_group)
        self.vbox.addWidget(log_group)
        self.vbox.addStretch(1)
