# This module contains the configuration settings for the lyric application.

DEFAULT_PRESETS = {
    "通用": {'text': '#fffeef', 'stroke': '#d8a523', 'glow': '#d8a523'},
    "心碎": {'text': '#b223cb', 'stroke': '#991eaf', 'glow': '#b223cb'},
    "指令": {'text': '#00ffff', 'stroke': '#00aaff', 'glow': '#00aaff'}
}
CONFIG_FILE = "lyric_config.json"

DEFAULT_PLAYERS = {
    "网易云音乐": {
        "process": "cloudmusic",
    },
    "酷狗音乐": {
        "process": "kugou",
        "support_progress": False
    },
    "QQ音乐": {
        "process": "qqmusic",
    }
}

# 纯音乐/伴奏特征正则列表（可在 lyric_config.json 的 settings.inst_patterns 中覆盖）
# 编曲作词标注过滤正则列表（可在 lyric_config.json 的 settings.credit_patterns 中覆盖）
DEFAULT_CREDIT_PATTERNS = [
    r"作词",
    r"作曲",
    r"编曲",
    r"制作人",
    r"OP[：:]",
    r"SP[：:]",
    r"原唱",
    r"翻唱",
    r"混音",
    r"录音",
    r"和声",
    r"监制",
    r"统筹",
    r"企划",
    r"出品",
    r"封面",
    r"曲\s*[：:]",
    r"词\s*[：:]",
    r"编曲\s*[：:]",
    r"吉他\s*[：:]",
    r"贝斯\s*[：:]",
    r"鼓\s*[：:]",
    r"键盘\s*[：:]",
    r"弦乐\s*[：:]",
    r"program(ming)?\s*[：:]",
    r"produced\s+by",
    r"written\s+by",
    r"composed\s+by",
    r"arranged\s+by",
    r"mixed\s+by",
    r"mastered\s+by",
]

DEFAULT_INST_PATTERNS = [
    r"\(inst\.?\)",
    r"（inst\.?）",
    r"\[inst\.?\]",
    r"【inst\.?】",
    r"\binst\.?$",
    r"instrumental",
    r"纯音乐",
    r"伴奏",
    r"off\s*vocal",
    r"offvocal",
    r"カラオケ",
    r"karaoke",
]