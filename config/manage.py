import os, json
import logging
from .settings import CONFIG_FILE, DEFAULT_PRESETS, DEFAULT_PLAYERS

logger = logging.getLogger(__name__)

# ==================== 配置读写 ====================
def load_all_config():
    if not os.path.exists(CONFIG_FILE):
        logger.info("配置文件 %s 不存在，使用默认配置", CONFIG_FILE)
        return {'settings': {}, 'presets': dict(DEFAULT_PRESETS), 'players': dict(DEFAULT_PLAYERS)}
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        logger.warning("读取配置文件 %s 失败，使用默认配置", CONFIG_FILE, exc_info=True)
        return {'settings': {}, 'presets': dict(DEFAULT_PRESETS), 'players': dict(DEFAULT_PLAYERS)}
    logger.info("读取配置文件 %s 成功", CONFIG_FILE)
    for key in ['presets', 'players', 'settings']:
        if key not in data:
            logger.warning("配置文件缺少 %s 字段，已补充为空", key)
            data[key] = {}
    if not data['presets']:
        logger.warning("配置文件中预设为空，已恢复默认预设")
        data['presets'] = dict(DEFAULT_PRESETS)
    if not data['players']:
        logger.warning("配置文件中播放器为空，已恢复默认播放器")
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
    logger.info("配置已保存到 %s", CONFIG_FILE)