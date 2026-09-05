"""时间页：演出延迟、时间轴参数与起始位置范围"""

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
            content="当前句之后以暗态提前显示后续 N 句，开启后歌词改用左右分区布局")

        # 未播放歌词是否保持暗态；取消勾选时以正常亮态常驻显示，唱完后正常淡出
        dim_card, self.preview_dim_check = switch_card(
            FluentIcon.BRIGHTNESS, "未播放歌词保持暗态",
            content="开启时预点亮歌词呈暗态，唱到再点亮；关闭时以亮态常驻",
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
        timeline_group.addSettingCard(widget_card(
            FluentIcon.HISTORY, "演出延迟（负值提前）", self.offset_spin,
            content="歌词整体偏移：正值延后，负值提前，0.1s 精度实时生效"))
        timeline_group.addSettingCard(preview_card)
        timeline_group.addSettingCard(dim_card)
        timeline_group.addSettingCard(widget_card(
            FluentIcon.STOP_WATCH, "留白（ms）", self.margin_spin,
            content="每句动画前的静默缓冲，避免字比唱先蹦出来"))
        timeline_group.addSettingCard(widget_card(
            FluentIcon.STOP_WATCH, "长间隔阈值（ms）", self.max_interval_spin,
            content="相邻两行间隔超过此值时判定为间奏，第一句不再按剩余时间均分字速"))
        timeline_group.addSettingCard(widget_card(
            FluentIcon.STOP_WATCH, "长间隔时长（ms）", self.max_duration_spin,
            content="间奏后第一句的字速基准，防止字蹦得太快"))

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
            content="歌词随机放置的坐标区间（占屏幕百分比），Y 建议留出底部空间")
        return slider, label, card
