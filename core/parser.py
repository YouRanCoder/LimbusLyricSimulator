import re
def parse_lrc(lrc_text):
    lines = lrc_text.strip().split('\n')
    result = []
    pattern = re.compile(r'\[(\d+):(\d+(?:\.\d+)?)\](.*)')
    for line in lines:
        match = pattern.match(line.strip())
        if match:
            m = int(match.group(1))
            s = float(match.group(2))
            text = match.group(3).strip()
            if text:
                result.append((int((m*60+s)*1000), text))
    result.sort(key=lambda x: x[0])
    return result