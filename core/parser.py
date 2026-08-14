import re
import logging

logger = logging.getLogger(__name__)


def parse_lrc(lrc_text):
    lines = lrc_text.strip().split('\n')
    result = []
    pattern = re.compile(r'\[(\d+):(\d+)(?:[.:](\d+))?\](.*)')
    for line in lines:
        match = pattern.match(line.strip())
        if match:
            m = int(match.group(1))
            s = int(match.group(2))
            frac = match.group(3)
            text = match.group(4).strip()
            if text:
                ms = (m * 60 + s) * 1000
                if frac:
                    if len(frac) >= 3:
                        ms += int(frac[:3])
                    elif len(frac) == 2:
                        ms += int(frac) * 10
                    else:
                        ms += int(frac) * 100
                result.append((ms, text))
    result.sort(key=lambda x: x[0])
    logger.info("LRC 解析完成：共 %d 行时间轴", len(result))
    return result