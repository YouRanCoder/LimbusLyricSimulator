"""控制面板分页公共组件与布局助手

所有分页都复用这里的滚动容器与设置卡片构造器，
保证外观统一、代码不重复。
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from qfluentwidgets import (
    CaptionLabel,
    ScrollArea,
    SettingCard,
    Slider,
    SwitchButton,
)


def make_scroll_page(object_name: str = "page") -> tuple:
    """创建带滚动视图的分页容器

    Args:
        object_name: 页面唯一标识，FluentWindow 导航用它作为路由键，不能重复。

    Returns:
        (page, vbox): page 是子页面，vbox 用于继续添加 SettingCardGroup。
    """
    page = QWidget()
    page.setObjectName(object_name)
    outer = QVBoxLayout(page)
    outer.setContentsMargins(0, 0, 0, 0)

    scroll = ScrollArea(page)
    scroll.setWidgetResizable(True)
    scroll.enableTransparentBackground()
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    view = QWidget()
    view.setObjectName("view")
    vbox = QVBoxLayout(view)
    vbox.setContentsMargins(20, 20, 20, 20)
    vbox.setSpacing(8)

    scroll.setWidget(view)
    outer.addWidget(scroll)
    return page, vbox


def slider_card(icon, title, minimum, maximum, value, suffix=""):
    """滑块设置卡片，返回 (card, slider, value_label)"""
    card = SettingCard(icon, title)
    slider = Slider(Qt.Horizontal)
    slider.setRange(minimum, maximum)
    slider.setValue(value)
    slider.setMinimumWidth(160)
    card.hBoxLayout.addWidget(slider, 1)

    label = CaptionLabel(f"{value}{suffix}")
    label.setMinimumWidth(64)
    label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    card.hBoxLayout.addWidget(label)
    return card, slider, label


def switch_card(icon, title, content=None, checked=False):
    """开关设置卡片，返回 (card, switch)"""
    card = SettingCard(icon, title, content)
    switch = SwitchButton()
    switch.setChecked(checked)
    card.hBoxLayout.addWidget(switch)
    return card, switch


def widget_card(icon, title, widget):
    """普通控件设置卡片，返回 card（控件已放入卡片右侧）"""
    card = SettingCard(icon, title)
    card.hBoxLayout.addStretch(1)
    card.hBoxLayout.addWidget(widget)
    return card
