# This module contains the configuration settings for the lyric application.

DEFAULT_PRESETS = {
    "通用": {'text': '#fffeef', 'stroke': '#d8a523', 'glow': '#d8a523'},
    "心碎": {'text': '#b223cb', 'stroke': '#991eaf', 'glow': '#b223cb'},
    "指令": {'text': '#00ffff', 'stroke': '#00aaff', 'glow': '#00aaff'}
}
CONFIG_FILE = "lyric_config.json"

DEFAULT_PLAYERS = {
    "网易云音乐": {
        "process": "cloudmusic.exe",
        "pattern": r'^(.+)\s*-\s*(.+?)$'
    },
    "酷狗音乐": {
        "process": "kgmusic.exe",
        "pattern": r'^(.+)\s*-\s*(.+?)$'
    },
    "QQ音乐": {
        "process": "QQMusic.exe",
        "pattern": r'^(.+)\s*-\s*(.+?)\s*-\s*QQ音乐$'
    }
}

# 纯音乐/伴奏特征正则列表（可在 lyric_config.json 的 settings.inst_patterns 中覆盖）
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