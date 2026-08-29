"""时间页：界面缩放、启动延时、演出延迟、时间轴参数与起始位置范围"""

from qfluentwidgets import (
    ComboBox,
    DoubleSpinBox,
    FluentIcon,
    SettingCardGroup,
    SpinBox,
)

from .base import make_scroll_page, slider_card, switch_card, widget_card


class TimelinePage:
    """时间页（控件容器，不含任何业务逻辑）"""

    def __init__(self):
        self.page, self.vbox = make_scroll_page("timelinePage")

        # ---- 界面缩放 ----
        zoom_card, self.zoom_slider, self.zoom_label = slider_card(
            FluentIcon.ZOOM, "界面缩放", 70, 150, 100, suffix="%")

        # ---- 时间轴 ----

        # 歌词演出延迟：正值延后显示，负值提前显示，0.1s 精度实时生效
        self.offset_spin = DoubleSpinBox()
        self.offset_spin.setRange(-10.0, 10.0)
        self.offset_spin.setSingleStep(0.1)
        self.offset_spin.setDecimals(1)
        self.offset_spin.setSuffix(" s")
        self.offset_spin.setValue(0.0)

        # 跟读预点亮：当前句之后保持暗态显示的后续句数（索引即句数，0=关闭）
        self.preview_combo = ComboBox()
        self.preview_combo.addItems(["关闭", "同屏 2 句（左右分区）", "同屏 3 句（左右分区）"])
        preview_card = widget_card(
            FluentIcon.LABEL, "跟读预点亮", self.preview_combo,
            content="在当前句之后以暗态提前显示后续 N 句，方便跟读；开启后歌词改用左右分区布局")

        # 未播放歌词是否保持暗态；取消勾选时以正常亮态常驻显示，唱完后正常淡出
        dim_card, self.preview_dim_check = switch_card(
            FluentIcon.BRIGHTNESS, "未播放歌词保持暗态",
            content="开启时跟读预点亮的歌词呈暗态，唱到再点亮；关闭时预点亮歌词以正常亮态常驻显示，唱到后直接呈现、唱完正常淡出",
            checked=True)

        self.margin_spin = SpinBox()
        self.margin_spin.setRange(0, 5000)
        self.margin_spin.setSingleStep(100)
        self.max_interval_spin = SpinBox()
        self.max_interval_spin.setRange(1000, 30000)
        self.max_interval_spin.setSingleStep(1000)
        self.max_duration_spin = SpinBox()
        self.max_duration_spin.setRange(500, 10000)
        self.max_duration_spin.setSingleStep(500)

        timeline_group = SettingCardGroup("时间轴", self.page)
        timeline_group.addSettingCard(zoom_card)
        timeline_group.addSettingCard(widget_card(
            FluentIcon.HISTORY, "演出延迟（负值提前）", self.offset_spin,
            content="整首歌歌词相对实际进度的偏移：正值整体延后，负值整体提前，0.1s 精度实时生效；如需「切歌后等几秒再开始」效果，可直接用正值"))
        timeline_group.addSettingCard(preview_card)
        timeline_group.addSettingCard(dim_card)
        timeline_group.addSettingCard(widget_card(
            FluentIcon.STOP_WATCH, "留白（ms）", self.margin_spin,
            content="每句逐字动画开始前的静默时间，让「歌已开口」与「字出现」之间留出缓冲，避免字比唱先蹦出来"))
        timeline_group.addSettingCard(widget_card(
            FluentIcon.STOP_WATCH, "长间隔阈值（ms）", self.max_interval_spin,
            content="当相邻两行歌词的时间间隔超过此值时，判定为间奏/纯音乐段；超过后第一句不再按剩余时间均分字速"))
        timeline_group.addSettingCard(widget_card(
            FluentIcon.STOP_WATCH, "长间隔时长（ms）", self.max_duration_spin,
            content="判定为长间隔时，每个字的目标呈现间隔（即长间隔后的第一句按此值算字速，防止间奏后字蹦得太快）"))

        # ---- 起始位置范围（百分比） ----
        self.pos_x_min_s, self.pos_x_lbl, xmin_card = self._range_row(0, 50, 5)
        self.pos_x_max_s, self.pos_x_max_lbl, xmax_card = self._range_row(50, 100, 85)
        self.pos_y_min_s, self.pos_y_lbl, ymin_card = self._range_row(0, 50, 5)
        self.pos_y_max_s, self.pos_y_max_lbl, ymax_card = self._range_row(50, 100, 75)

        pos_group = SettingCardGroup("起始位置范围（%）", self.page)
        pos_group.addSettingCard(xmin_card)
        pos_group.addSettingCard(xmax_card)
        pos_group.addSettingCard(ymin_card)
        pos_group.addSettingCard(ymax_card)

        self.vbox.addWidget(timeline_group)
        self.vbox.addWidget(pos_group)
        self.vbox.addStretch(1)

    def _range_row(self, minimum, maximum, value):
        """单个起止位置滑块，返回 (slider, label, card)"""
        card, slider, label = slider_card(
            FluentIcon.MOVE, f"位置范围 {minimum}-{maximum}", minimum, maximum, value, suffix="%",
            content="歌词在屏幕上随机放置的坐标区间（占屏幕宽/高百分比）；最小值<最大值，Y 通常留出底部空间避免歌词被任务栏遮挡")
        return slider, label, card
