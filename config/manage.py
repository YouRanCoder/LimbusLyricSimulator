import os, json
from .settings import CONFIG_FILE, DEFAULT_PRESETS, DEFAULT_PLAYERS
# ==================== 配置读写 ====================
def load_all_config():
    if not os.path.exists(CONFIG_FILE):
        return {'settings': {}, 'presets': dict(DEFAULT_PRESETS), 'players': dict(DEFAULT_PLAYERS)}
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    for key in ['presets', 'players', 'settings']:
        if key not in data:
            data[key] = {}
    if not data['presets']:
        data['presets'] = dict(DEFAULT_PRESETS)
    if not data['players']:
        data['players'] = dict(DEFAULT_PLAYERS)
    return data

def save_all_config(panel, presets, players):
    data = {
        'settings': {
            'text_color': panel.current_color.name(),
            'stroke_color': panel.current_stroke_color.name(),
            'glow_color': panel.current_glow_color.name(),
            'glow_enabled': panel.glow_check.isChecked(),
            'glow_size': panel.glow_size_slider.value(),
            'glow_alpha': panel.glow_alpha_slider.value(),
            'loop': panel.loop_check.isChecked(),
            'trans_only': panel.trans_check.isChecked(),
            'mode': panel.mode_combo.currentData(),
            'font_family': panel.font_combo.currentFont().family(),
            'font_size': panel.font_size.value(),
            'stroke_width': panel.stroke_spin.value(),
            'spacing': panel.spacing_spin.value(),
            'shake_intensity': panel.shake_intensity_slider.value(),
            'shake_speed': panel.shake_speed_slider.value(),
            'fade_speed': panel.fade_speed_slider.value(),
            'rise_speed': panel.rise_speed_slider.value(),
            'margin_time': panel.margin_spin.value(),
            'max_interval': panel.max_interval_spin.value(),
            'max_duration': panel.max_duration_spin.value(),
            'angle_min': panel.angle_min.value(),
            'angle_max': panel.angle_max.value(),
            'player': panel.player_combo.currentText(),
            'source': panel.source_combo.currentText(),
            'delay': panel.delay_combo.currentIndex(),
            'perspective_enabled': panel.perspective_check.isChecked(),
            'persp_x_strength': panel.persp_x_slider.value(),
            'persp_y_strength': panel.persp_y_slider.value(),
            'persp_compensation': panel.persp_comp_slider.value(),
        },
        'presets': presets,
        'players': players
    }
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)