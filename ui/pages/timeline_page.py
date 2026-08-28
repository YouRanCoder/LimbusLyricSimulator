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
        loop_card, self.loop_check = switch_card(
            FluentIcon.SYNC, "单曲循环", checked=True)
        self.delay_combo = ComboBox()
        self.delay_combo.addItems(["0s", "1s", "2s", "3s", "5s"])

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

        # 未播放歌词是否保持暗态；取消勾选时以正常亮态常驻显示，唱完后正常淡出
        dim_card, self.preview_dim_check = switch_card(
            FluentIcon.BRIGHTNESS, "未播放歌词保持暗态",
            content="取消勾选时未播放歌词正常亮态常驻显示，唱到后直接呈现，唱完正常淡出",
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
        timeline_group.addSettingCard(loop_card)
        timeline_group.addSettingCard(widget_card(
            FluentIcon.QUIET_HOURS, "启动延时", self.delay_combo))
        timeline_group.addSettingCard(widget_card(
            FluentIcon.HISTORY, "演出延迟（负值提前）", self.offset_spin))
        timeline_group.addSettingCard(widget_card(
            FluentIcon.LABEL, "跟读预点亮", self.preview_combo))
        timeline_group.addSettingCard(dim_card)
        timeline_group.addSettingCard(widget_card(
            FluentIcon.STOP_WATCH, "留白（ms）", self.margin_spin))
        timeline_group.addSettingCard(widget_card(
            FluentIcon.STOP_WATCH, "长间隔阈值（ms）", self.max_interval_spin))
        timeline_group.addSettingCard(widget_card(
            FluentIcon.STOP_WATCH, "长间隔时长（ms）", self.max_duration_spin))

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
            FluentIcon.MOVE, f"位置范围 {minimum}-{maximum}", minimum, maximum, value, suffix="%")
        return slider, label, card
