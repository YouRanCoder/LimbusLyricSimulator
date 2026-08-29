import urllib.parse, base64
import httpx
import logging
import re

logger = logging.getLogger(__name__)

_LRC_LINE = re.compile(r'\[(\d+):(\d+)(?:[.:](\d+))?\](.*)')


def _normalize_text(s: str) -> str:
    """比对用规范化：小写并去除所有空白字符"""
    return re.sub(r"\s+", "", s or "").lower()


def _parse_lrc_lines(lrc_text: str) -> list:
    """把 LRC 文本解析为 [(毫秒, 文本), ...]，已按时间排序"""
    result = []
    if not lrc_text:
        return result
    for line in lrc_text.split('\n'):
        match = _LRC_LINE.match(line.strip())
        if not match:
            continue
        m, s = int(match.group(1)), int(match.group(2))
        frac = match.group(3)
        text = match.group(4).strip()
        if not text:
            continue
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
    return result


def merge_bilingual_lyric(lrc: str, tlyric: str, max_gap_ms: int = 500) -> str:
    """把原始歌词与翻译歌词合并为「中英同时演出」的单条时间轴

    使用双指针贪心匹配：对每个原始行，在其时间戳前后各 max_gap_ms 范围内
    找最近的翻译行，命中后输出 [原始行, 翻译行] 两条连续时间行使其同时显示；
    每条翻译行只匹配一次（先到先得）。找不到匹配翻译的原始行只输出原文，
    未被匹配的翻译行按自身时间戳兜底输出。
    """
    origin = _parse_lrc_lines(lrc)
    trans = _parse_lrc_lines(tlyric)
    if not origin:
        return tlyric or ""
    if not trans:
        return lrc or ""

    lines = []
    matched_trans = set()  # 已匹配的翻译行索引
    j = 0  # 翻译行游标（trans 已按时间排序）
    for ms, text in origin:
        lines.append(f"[{_fmt_ts(ms)}]{text}")
        # 向前推进游标到不早于 ms - max_gap 的翻译行
        while j < len(trans) and trans[j][0] < ms - max_gap_ms:
            j += 1
        # 在 [ms - max_gap, ms + max_gap] 内挑选最接近的未使用翻译行
        best_idx, best_dist = None, max_gap_ms + 1
        k = j
        while k < len(trans) and trans[k][0] <= ms + max_gap_ms:
            if k not in matched_trans:
                dist = abs(trans[k][0] - ms)
                if dist < best_dist:
                    best_idx, best_dist = k, dist
            k += 1
        if best_idx is not None:
            matched_trans.add(best_idx)
            lines.append(f"[{_fmt_ts(ms)}]{trans[best_idx][1]}")

    # 兜底：未被匹配且不与任何原始行相近的翻译行，按自身时间戳输出
    orphan_trans = [t for i, t in enumerate(trans)
                    if i not in matched_trans
                    and not any(abs(t[0] - oms) <= max_gap_ms for oms, _ in origin)]
    for ms, text in orphan_trans:
        lines.append(f"[{_fmt_ts(ms)}]{text}")

    merged = '\n'.join(lines)
    logger.info("中英双语合并完成：原始 %d 行，翻译 %d 行，合并后 %d 行",
                len(origin), len(trans), len(lines))
    return merged


def _fmt_ts(ms: int) -> str:
    """毫秒转 LRC 时间标签 [mm:ss.xx]"""
    total_s = max(0, ms) // 1000
    frac = (max(0, ms) % 1000) // 10
    return f"{total_s // 60:02d}:{total_s % 60:02d}.{frac:02d}"


def _strip_brackets(s: str) -> str:
    """去掉括号装饰后缀，如「歌名(Live)」「歌名（翻自 xxx）」→「歌名」"""
    return re.sub(r"[（(【\[][^\n]*?[）)】\]]", "", s or "")


class LyricSearchEngine:
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    @classmethod
    async def _get(cls, url: str, headers=None) -> httpx.Response:
        """异步 GET 请求（每次请求独立客户端，退出时无需显式清理）"""
        async with httpx.AsyncClient(
            headers=cls.HEADERS, timeout=5, follow_redirects=True
        ) as client:
            return await client.get(url, headers=headers)

    # ---- 候选校验 ----

    @staticmethod
    def _match_score(candidate_name: str, request_name: str) -> int:
        """歌名匹配打分：3=规范化后相等，2=互相包含，0=不匹配

        比对时同时考虑去括号形式，兼容「歌名(Live)」「歌名（洛天依原创曲）」等装饰。
        """
        def variants(name):
            v = {_normalize_text(name)}
            stripped = _normalize_text(_strip_brackets(name))
            if stripped:
                v.add(stripped)
            return v

        req, cand = variants(request_name), variants(candidate_name)
        if req & cand:
            return 3
        for a in req:
            for b in cand:
                if a in b or b in a:
                    return 2
        return 0

    @classmethod
    def _pick_best(cls, candidates, song_name: str, duration_ms: int = 0):
        """从模糊搜索的多候选中挑出与请求匹配的一首，全部不合格则返回 None

        candidates: [(name, artist, duration_ms, key), ...]，key 为查歌词用的标识。
        规则：歌名规范化后必须相等或互含（拒绝搜索接口的模糊联想结果，
        防止"按歌手随机给一首"的驴唇不对马嘴）；同分时取时长最接近的
        （播放器上报时长可信时），未知时长的候选排最后但不淘汰。
        """
        scored = []
        for name, artist, dur, key in candidates:
            score = cls._match_score(name, song_name)
            if score <= 0:
                continue
            dur_diff = abs(dur - duration_ms) if (duration_ms > 0 and dur > 0) else 10 ** 9
            scored.append((score, dur_diff, name, artist, dur, key))
        if not scored:
            logger.info("候选校验全部不匹配：%s（丢弃 %d 条模糊联想结果）",
                        song_name, len(candidates))
            return None
        # 时长偏差超过 15 秒的同分候选降级到末尾（大概率是 Live/Remix 版本）
        scored.sort(key=lambda t: (-t[0], min(t[1], 15001)))
        _, _, name, artist, dur, key = scored[0]
        logger.info("候选命中：%s - %s（%dms），参与校验候选 %d 条",
                    name, artist, dur, len(candidates))
        return name, artist, dur, key

    # ---- 网易云 ID 直查 ----

    @classmethod
    async def fetch_netease_lyric_by_id(cls, song_id: int, need_trans: bool = False):
        """通过网易云歌曲 ID 直查歌词（elog 适配器提供精确 ID 时使用）

        主接口 song/media 结构简单、对 VIP/无版权歌曲更宽松；
        该接口不带翻译，「仅翻译」模式时补调 song/lyric 接口获取。

        Returns:
            (原始歌词, 翻译歌词) 或 None（ID 无效/无歌词/请求失败）
        """
        try:
            resp = await cls._get(
                f"https://music.163.com/api/song/media?id={int(song_id)}")
            data = resp.json()
            lrc = data.get('lyric') if isinstance(data.get('lyric'), str) else ''
            if not lrc.strip():
                logger.info("网易云 ID 直查无歌词：id=%s（可能为云盘歌曲）", song_id)
                return None
            tlyric = ''
            if need_trans:
                try:
                    resp2 = await cls._get(
                        f"http://music.163.com/api/song/lyric?id={int(song_id)}&lv=1&kv=1&tv=-1")
                    raw = resp2.json().get('tlyric')
                    tlyric = raw.get('lyric', '') if isinstance(raw, dict) else ''
                except Exception:
                    logger.debug("网易云 ID 直查补取翻译失败：id=%s", song_id, exc_info=True)
            logger.info("网易云 ID 直查歌词成功：id=%d，原始 %d 字符，翻译 %d 字符",
                        song_id, len(lrc), len(tlyric))
            return lrc, tlyric
        except Exception:
            logger.warning("网易云 ID 直查歌词失败：id=%s", song_id, exc_info=True)
            return None

    # ---- 文本搜索（多候选 + 校验）----

    @classmethod
    async def search_netease(cls, song_name, artist="", duration_ms=0):
        try:
            keyword = f"{song_name} {artist}".strip()
            url = f"http://music.163.com/api/search/get?s={urllib.parse.quote(keyword)}&type=1&limit=10"
            resp = await cls._get(url)
            data = resp.json()
            songs = data.get('result', {}).get('songs') or []
            candidates = [
                (s.get('name', ''),
                 ', '.join(a.get('name', '') for a in s.get('artists') or []),
                 int(s.get('duration') or 0),
                 s['id'])
                for s in songs if s.get('id')
            ]
            picked = cls._pick_best(candidates, song_name, duration_ms)
            if not picked:
                logger.info("网易云搜索无匹配：%s", keyword)
                return None, None, 0
            _, _, duration, song_id = picked
            lyric_url = f"http://music.163.com/api/song/lyric?id={song_id}&lv=1&kv=1&tv=-1"
            lrc_resp = await cls._get(lyric_url)
            lrc_data = lrc_resp.json()
            lrc = lrc_data.get('lrc', {}).get('lyric', '')
            tlyric = lrc_data.get('tlyric', {}).get('lyric', '')
            logger.info("网易云搜索成功：%s，时长 %dms，原始歌词 %d 字符，翻译 %d 字符",
                        keyword, duration, len(lrc), len(tlyric))
            return lrc, tlyric, duration
        except Exception:
            logger.warning("网易云搜索失败：%s", song_name, exc_info=True)
            return None, None, 0

    @classmethod
    async def search_qq(cls, song_name, artist="", duration_ms=0):
        try:
            keyword = f"{song_name} {artist}".strip()
            search_url = f"https://c.y.qq.com/soso/fcgi-bin/client_search_cp?p=1&n=10&w={urllib.parse.quote(keyword)}&format=json"
            headers = {**cls.HEADERS, 'Referer': 'https://y.qq.com/'}
            resp = await cls._get(search_url, headers=headers)
            data = resp.json()
            songs = data.get('data', {}).get('song', {}).get('list') or []
            candidates = [
                (s.get('songname', '') or s.get('songorig', ''),
                 ', '.join(a.get('name', '') for a in s.get('singer') or []),
                 int(s.get('interval') or 0) * 1000,
                 s.get('songmid'))
                for s in songs if s.get('songmid')
            ]
            picked = cls._pick_best(candidates, song_name, duration_ms)
            if not picked:
                logger.info("QQ音乐搜索无匹配：%s", keyword)
                return None, None, 0
            _, _, duration, songmid = picked
            lyric_url = f"https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg?songmid={songmid}&format=json&nobase64=0"
            lrc_resp = await cls._get(lyric_url, headers=headers)
            lrc_data = lrc_resp.json()
            lyric = lrc_data.get('lyric', '')
            if lyric:
                lyric = base64.b64decode(lyric).decode('utf-8')
            # QQ音乐歌词格式转换
            if lyric and '[' not in lyric:
                lyric = None
            logger.info("QQ音乐搜索成功：%s，时长 %dms，歌词 %s",
                        keyword, duration, f"{len(lyric)} 字符" if lyric else "为空")
            return lyric, None, duration
        except Exception:
            logger.warning("QQ音乐搜索失败：%s", song_name, exc_info=True)
            return None, None, 0

    @classmethod
    async def search_kugou(cls, song_name, artist="", duration_ms=0):
        try:
            keyword = f"{song_name} {artist}".strip()
            search_url = f"http://mobilecdn.kugou.com/api/v3/search/song?format=json&keyword={urllib.parse.quote(keyword)}&page=1&pagesize=10"
            resp = await cls._get(search_url)
            data = resp.json()
            songs = data.get('data', {}).get('info') or []
            candidates = [
                (s.get('songname', ''),
                 s.get('singername', ''),
                 int(s.get('duration') or 0) * 1000,
                 s.get('hash'))
                for s in songs if s.get('hash')
            ]
            picked = cls._pick_best(candidates, song_name, duration_ms)
            if not picked:
                logger.info("酷狗搜索无匹配：%s", keyword)
                return None, None, 0
            _, _, duration, song_hash = picked
            lyric_url = f"http://m.kugou.com/app/i/krc.php?cmd=100&hash={song_hash}&timelength=999999"
            lrc_resp = await cls._get(lyric_url)
            lyric = lrc_resp.text
            if lyric and 'krc' not in lyric and lyric.strip():
                logger.info("酷狗搜索成功：%s，时长 %dms，歌词 %d 字符",
                            keyword, duration, len(lyric))
                return lyric, None, duration
            logger.info("酷狗歌词不可用：%s", keyword)
            return None, None, 0
        except Exception:
            logger.warning("酷狗搜索失败：%s", song_name, exc_info=True)
            return None, None, 0

    @classmethod
    async def search(cls, song_name, artist="", source="网易云", trans_only=False,
                     song_id=0, duration_ms=0, bilingual=False):
        logger.info("开始搜索歌词：歌名=%s，歌手=%s，来源=%s，仅翻译=%s，中英双语=%s，歌曲ID=%s",
                    song_name, artist, source, trans_only, bilingual, song_id or "无")
        lrc = tlyric = None
        duration = 0
        if source == "网易云":
            # elog 适配器提供了有效歌曲 ID：直查歌词接口（精确，绕过模糊搜索），
            # 失败（无词/无效 ID/网络异常）再回退文本搜索
            if song_id and int(song_id) > 0:
                got = await cls.fetch_netease_lyric_by_id(int(song_id),
                                                          need_trans=trans_only)
                if got:
                    lrc, tlyric = got
                    # 直查接口不返回时长，返回 0 让上层沿用播放器上报的真实时长
                    duration = 0
            if lrc is None and tlyric is None:
                lrc, tlyric, duration = await cls.search_netease(
                    song_name, artist, duration_ms)
        elif source == "QQ音乐":
            lrc, tlyric, duration = await cls.search_qq(song_name, artist, duration_ms)
        elif source == "酷狗":
            lrc, tlyric, duration = await cls.search_kugou(song_name, artist, duration_ms)
        else:
            logger.warning("未知歌词源：%s", source)
            return None, 0

        if bilingual and (lrc or tlyric) and (lrc or tlyric).strip():
            merged = merge_bilingual_lyric(lrc, tlyric)
            logger.info("返回中英双语合并歌词，时长 %dms", duration)
            return merged, duration
        if trans_only and tlyric and tlyric.strip():
            logger.info("返回翻译歌词，时长 %dms", duration)
            return tlyric, duration
        if lrc and lrc.strip():
            logger.info("返回原始歌词，时长 %dms", duration)
            return lrc, duration
        if tlyric and tlyric.strip():
            logger.info("返回翻译歌词（兜底），时长 %dms", duration)
            return tlyric, duration
        logger.warning("歌词搜索无结果：%s", song_name)
        return None, duration
