"""播放页：播放器/歌词源选择、适配开关、歌词输入与开始/停止"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QTextEdit, QVBoxLayout

from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    ComboBox,
    FluentIcon,
    PrimaryPushButton,
    PushButton,
    SettingCardGroup,
)

from .base import make_scroll_page, switch_card, widget_card


class PlaybackPage:
    """播放页（控件容器，不含任何业务逻辑）

    控件由 ControlPanel 统一连接 controller。
    """

    def __init__(self):
        self.page, self.vbox = make_scroll_page("playbackPage")

        # ---- 播放器与歌词源 ----
        self.player_combo = ComboBox()
        self.btn_add_p = PushButton(FluentIcon.ADD, "")
        self.btn_del_p = PushButton(FluentIcon.REMOVE, "")
        self.source_combo = ComboBox()
        self.source_combo.addItems(["网易云", "QQ音乐", "酷狗"])

        player_card = widget_card(FluentIcon.WIFI, "播放器", self.player_combo)
        player_card.hBoxLayout.addWidget(self.btn_add_p)
        player_card.hBoxLayout.addWidget(self.btn_del_p)

        netease_card, self.netease_adapter_check = switch_card(
            FluentIcon.CONNECT, "使用网易云适配",
            "勾选=网易云日志适配器，取消=SMTC（适用于 inflink-rs 等第三方插件）",
            checked=True)
        pure_card, self.filter_pure_music_check = switch_card(
            FluentIcon.BROOM, "过滤纯音乐/伴奏",
            "自动播放时按歌名特征识别，不显示歌词", checked=True)
        trans_card, self.trans_check = switch_card(
            FluentIcon.ROBOT, "仅获取翻译歌词", checked=False)

        player_group = SettingCardGroup("播放器", self.page)
        player_group.addSettingCard(player_card)
        player_group.addSettingCard(widget_card(
            FluentIcon.ALBUM, "歌词源", self.source_combo))
        player_group.addSettingCard(netease_card)
        player_group.addSettingCard(pure_card)
        player_group.addSettingCard(trans_card)

        # ---- 歌词输入 ----
        self.text_input = QTextEdit()
        self.text_input.setMinimumHeight(120)
        self.text_input.setPlaceholderText("可粘贴 LRC 歌词；留空则点击「开始播放」自动获取")
        self.refetch_btn = PushButton(FluentIcon.SYNC, "重新获取")

        lyric_card = CardWidget(self.page)
        _lyric_vbox = QVBoxLayout(lyric_card)
        _lyric_vbox.setContentsMargins(16, 12, 16, 12)
        _lyric_vbox.setSpacing(8)

        _title_row = QHBoxLayout()
        _title_row.setSpacing(4)
        _lyric_title = BodyLabel("歌词")
        _lyric_title.setStyleSheet("font-weight: 600;")
        _lyric_sub = CaptionLabel("可选，留空则自动获取")
        _title_row.addWidget(_lyric_title)
        _title_row.addWidget(_lyric_sub)
        _title_row.addStretch(1)
        _title_row.addWidget(self.refetch_btn)

        _lyric_vbox.addLayout(_title_row)
        _lyric_vbox.addWidget(self.text_input)

        # ---- 开始/停止 ----
        self.start_btn = PrimaryPushButton(FluentIcon.PLAY, "开始播放")
        self.stop_btn = PushButton(FluentIcon.PAUSE, "停止播放")
        self.status = BodyLabel("状态：就绪")
        self.status.setAlignment(Qt.AlignCenter)

        action_card = widget_card(FluentIcon.PLAY, "播放控制", self.start_btn)
        action_card.hBoxLayout.addWidget(self.stop_btn)
        status_card = widget_card(FluentIcon.INFO, "状态", self.status)

        action_group = SettingCardGroup("操作", self.page)
        action_group.addSettingCard(action_card)
        action_group.addSettingCard(status_card)

        self.vbox.addWidget(player_group)
        self.vbox.addWidget(lyric_card)
        self.vbox.addWidget(action_group)
        self.vbox.addWidget(CaptionLabel("按 Esc 退出程序"))
        self.vbox.addStretch(1)
