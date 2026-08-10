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

def save_all_config(settings, presets, players):
    """保存配置到 JSON 文件。

    Args:
        settings: 设置字典，由调用方从 UI 提取后传入
        presets: 预设配色方案字典
        players: 播放器配置字典
    """
    data = {
        'settings': settings,
        'presets': presets,
        'players': players,
    }
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)