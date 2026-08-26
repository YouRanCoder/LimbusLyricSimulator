"""外观页：预设/模式、字体字号、文字/阴影颜色、描边与字间距"""

from PyQt5.QtGui import QColor, QFontDatabase

from qfluentwidgets import (
    ColorPickerButton,
    ComboBox,
    DoubleSpinBox,
    FluentIcon,
    PushButton,
    SettingCardGroup,
    SpinBox,
)

from .base import make_scroll_page, widget_card


class AppearancePage:
    """外观页（控件容器，不含任何业务逻辑）"""

    def __init__(self):
        self.page, self.vbox = make_scroll_page("appearancePage")

        # ---- 预设与模式 ----
        self.preset_combo = ComboBox()
        self.btn_new = PushButton(FluentIcon.ADD, "")
        self.btn_del = PushButton(FluentIcon.REMOVE, "")
        self.mode_combo = ComboBox()
        self.mode_combo.addItem("自动（按句判定）", userData="auto")
        self.mode_combo.addItem("中文", userData="chinese")
        self.mode_combo.addItem("英文", userData="english")

        preset_card = widget_card(FluentIcon.LABEL, "预设", self.preset_combo)
        preset_card.hBoxLayout.addWidget(self.btn_new)
        preset_card.hBoxLayout.addWidget(self.btn_del)
        mode_card = widget_card(FluentIcon.EDIT, "模式", self.mode_combo)

        preset_group = SettingCardGroup("预设与模式", self.page)
        preset_group.addSettingCard(preset_card)
        preset_group.addSettingCard(mode_card)

        # ---- 字体 ----
        self.font_combo = ComboBox()
        # QFontComboBox 构造时会枚举并加载系统全部字体（312 个字体约 520ms，
        # 直接拖慢启动出现白屏），改用普通 QComboBox 填充字体家族名（仅 ~2ms）
        self.font_combo.addItems(QFontDatabase().families())
        self.font_size = SpinBox()
        self.font_size.setRange(10, 100)
        self.btn_auto_font = PushButton(FluentIcon.BRUSH, "推荐字体")

        font_card = widget_card(FluentIcon.ALBUM, "字体", self.font_combo)
        size_card = widget_card(FluentIcon.ZOOM_IN, "字号", self.font_size)
        auto_card = widget_card(FluentIcon.BRUSH, "自动选择推荐字体", self.btn_auto_font)

        font_group = SettingCardGroup("字体", self.page)
        font_group.addSettingCard(font_card)
        font_group.addSettingCard(size_card)
        font_group.addSettingCard(auto_card)

        # ---- 颜色 ----
        self.color_btn = ColorPickerButton(QColor("#fffeef"), "文字颜色")
        self.stroke_btn = ColorPickerButton(QColor("#d8a523"), "阴影颜色")
        self.stroke_spin = DoubleSpinBox()
        self.stroke_spin.setRange(0.0, 10.0)
        self.stroke_spin.setSingleStep(0.1)
        self.stroke_spin.setDecimals(1)
        self.spacing_spin = DoubleSpinBox()
        self.spacing_spin.setRange(-10.0, 30.0)
        self.spacing_spin.setSingleStep(0.5)
        self.spacing_spin.setDecimals(1)

        color_group = SettingCardGroup("颜色", self.page)
        color_group.addSettingCard(widget_card(FluentIcon.PALETTE, "文字颜色", self.color_btn))
        color_group.addSettingCard(widget_card(FluentIcon.PALETTE, "阴影颜色", self.stroke_btn))
        color_group.addSettingCard(widget_card(FluentIcon.BRUSH, "描边粗细（px）", self.stroke_spin))
        color_group.addSettingCard(widget_card(FluentIcon.MOVE, "字间距（px）", self.spacing_spin))

        self.vbox.addWidget(preset_group)
        self.vbox.addWidget(font_group)
        self.vbox.addWidget(color_group)
        self.vbox.addStretch(1)