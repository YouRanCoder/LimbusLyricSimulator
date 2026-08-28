"""动画页：发光、3D 透视、颤动、淡出/上升与角度范围"""

from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QHBoxLayout

from qfluentwidgets import (
    ColorPickerButton,
    FluentIcon,
    SettingCard,
    SettingCardGroup,
    SpinBox,
)

from .base import make_scroll_page, slider_card, switch_card, widget_card


class AnimationPage:
    """动画页（控件容器，不含任何业务逻辑）"""

    def __init__(self):
        self.page, self.vbox = make_scroll_page("animationPage")

        # ---- 发光 ----
        glow_card, self.glow_check = switch_card(
            FluentIcon.BROOM, "发光", checked=True)
        self.glow_color_btn = ColorPickerButton(QColor("#d8a523"), "光晕颜色")
        glow_size_card, self.glow_size_slider, self.glow_size_label = slider_card(
            FluentIcon.ZOOM, "光晕粗细", 4, 30, 4)
        glow_alpha_card, self.glow_alpha_slider, self.glow_alpha_label = slider_card(
            FluentIcon.BROOM, "光晕透明度", 10, 120, 82)

        glow_group = SettingCardGroup("发光", self.page)
        glow_group.addSettingCard(glow_card)
        glow_group.addSettingCard(widget_card(FluentIcon.PALETTE, "光晕颜色", self.glow_color_btn))
        glow_group.addSettingCard(glow_size_card)
        glow_group.addSettingCard(glow_alpha_card)

        # ---- 3D 透视 ----
        persp_card, self.perspective_check = switch_card(
            FluentIcon.VIDEO, "3D透视（测试）",
            content="开启后歌词按屏幕位置产生近大远小的倾斜效果；关闭则保持平面渲染", checked=True)
        px_card, self.persp_x_slider, self.persp_x_label = slider_card(
            FluentIcon.MOVE, "透视X", 0, 100, 5,
            content="水平方向的倾斜强度：值越大，左右两侧歌词倾斜越明显")
        py_card, self.persp_y_slider, self.persp_y_label = slider_card(
            FluentIcon.MOVE, "透视Y", 0, 100, 30,
            content="垂直方向的倾斜强度：值越大，上下两侧歌词俯仰感越明显")
        pc_card, self.persp_comp_slider, self.persp_comp_label = slider_card(
            FluentIcon.MOVE, "水平补偿", 0, 100, 3,
            content="透视导致的水平拉伸补偿：值越大，右侧歌词被横向放大越多（用于抵消透视畸变）")

        persp_group = SettingCardGroup("3D 透视", self.page)
        persp_group.addSettingCard(persp_card)
        persp_group.addSettingCard(px_card)
        persp_group.addSettingCard(py_card)
        persp_group.addSettingCard(pc_card)

        # ---- 颤动/动画 ----
        si_card, self.shake_intensity_slider, self.shake_intensity_label = slider_card(
            FluentIcon.MOVE, "颤强", 0, 10, 2,
            content="逐字动画时每个字符随机抖动的最大像素半径；0=完全静止")
        ss_card, self.shake_speed_slider, self.shake_speed_label = slider_card(
            FluentIcon.SPEED_HIGH, "颤速", 10, 200, 143, suffix=" ms",
            content="抖动重新选取目标的间隔：值越小抖动越快越剧烈，越大越缓")
        fs_card, self.fade_speed_slider, self.fade_speed_label = slider_card(
            FluentIcon.VIDEO, "淡出速度", 1, 15, 12,
            content="已唱完的歌词行残影每帧的透明度衰减：值越大消失得越快")
        rs_card, self.rise_speed_slider, self.rise_speed_label = slider_card(
            FluentIcon.VIDEO, "上升速度", 0, 5, 1,
            content="已唱完的歌词行残影每帧向上飘动的像素：0=不飘动，值越大飘得越高")

        self.angle_min = SpinBox()
        self.angle_min.setRange(-90, 90)
        self.angle_max = SpinBox()
        self.angle_max.setRange(-90, 90)
        angle_box = QHBoxLayout()
        angle_box.setSpacing(8)
        angle_box.addWidget(self.angle_min)
        angle_box.addWidget(self.angle_max)

        angle_card = SettingCard(FluentIcon.MOVE, "角度范围",
            content="歌词随机旋转的角度区间（度）：左为最小，右为最大；负值向左倾，正值向右倾")
        angle_card.hBoxLayout.addStretch(1)
        angle_card.hBoxLayout.addLayout(angle_box)

        anim_group = SettingCardGroup("动画", self.page)
        anim_group.addSettingCard(si_card)
        anim_group.addSettingCard(ss_card)
        anim_group.addSettingCard(fs_card)
        anim_group.addSettingCard(rs_card)
        anim_group.addSettingCard(angle_card)

        self.vbox.addWidget(glow_group)
        self.vbox.addWidget(persp_group)
        self.vbox.addWidget(anim_group)
        self.vbox.addStretch(1)
