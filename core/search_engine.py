import urllib.parse, base64
import httpx
import logging

logger = logging.getLogger(__name__)


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

    @classmethod
    async def search_netease(cls, song_name, artist=""):
        try:
            keyword = f"{song_name} {artist}".strip()
            url = f"http://music.163.com/api/search/get?s={urllib.parse.quote(keyword)}&type=1&limit=1"
            resp = await cls._get(url)
            data = resp.json()
            songs = data.get('result', {}).get('songs', [])
            if songs:
                song = songs[0]
                song_id = song['id']
                duration = song.get('duration', 0)
                lyric_url = f"http://music.163.com/api/song/lyric?id={song_id}&lv=1&kv=1&tv=-1"
                lrc_resp = await cls._get(lyric_url)
                lrc_data = lrc_resp.json()
                lrc = lrc_data.get('lrc', {}).get('lyric', '')
                tlyric = lrc_data.get('tlyric', {}).get('lyric', '')
                logger.info("网易云搜索成功：%s，时长 %dms，原始歌词 %d 字符，翻译 %d 字符",
                            keyword, duration, len(lrc), len(tlyric))
                return lrc, tlyric, duration
            logger.info("网易云搜索无结果：%s", keyword)
            return None, None, 0
        except Exception:
            logger.warning("网易云搜索失败：%s", song_name, exc_info=True)
            return None, None, 0

    @classmethod
    async def search_qq(cls, song_name, artist=""):
        try:
            keyword = f"{song_name} {artist}".strip()
            search_url = f"https://c.y.qq.com/soso/fcgi-bin/client_search_cp?p=1&n=1&w={urllib.parse.quote(keyword)}&format=json"
            headers = {**cls.HEADERS, 'Referer': 'https://y.qq.com/'}
            resp = await cls._get(search_url, headers=headers)
            data = resp.json()
            songs = data.get('data', {}).get('song', {}).get('list', [])
            if songs:
                song = songs[0]
                songmid = song.get('songmid')
                duration = song.get('interval', 0) * 1000
                lyric_url = f"https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg?songmid={songmid}&format=json&nobase64=1"
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
            logger.info("QQ音乐搜索无结果：%s", keyword)
            return None, None, 0
        except Exception:
            logger.warning("QQ音乐搜索失败：%s", song_name, exc_info=True)
            return None, None, 0

    @classmethod
    async def search_kugou(cls, song_name, artist=""):
        try:
            keyword = f"{song_name} {artist}".strip()
            search_url = f"http://mobilecdn.kugou.com/api/v3/search/song?format=json&keyword={urllib.parse.quote(keyword)}&page=1&pagesize=1"
            resp = await cls._get(search_url)
            data = resp.json()
            songs = data.get('data', {}).get('info', [])
            if songs:
                song = songs[0]
                song_hash = song.get('hash')
                duration = song.get('duration', 0) * 1000
                lyric_url = f"http://m.kugou.com/app/i/krc.php?cmd=100&hash={song_hash}&timelength=999999"
                lrc_resp = await cls._get(lyric_url)
                lyric = lrc_resp.text
                if lyric and 'krc' not in lyric and lyric.strip():
                    logger.info("酷狗搜索成功：%s，时长 %dms，歌词 %d 字符",
                                keyword, duration, len(lyric))
                    return lyric, None, duration
            logger.info("酷狗搜索无结果：%s", keyword)
            return None, None, 0
        except Exception:
            logger.warning("酷狗搜索失败：%s", song_name, exc_info=True)
            return None, None, 0

    @classmethod
    async def search(cls, song_name, artist="", source="网易云", trans_only=False):
        logger.info("开始搜索歌词：歌名=%s，歌手=%s，来源=%s，仅翻译=%s",
                    song_name, artist, source, trans_only)
        if source == "网易云":
            lrc, tlyric, duration = await cls.search_netease(song_name, artist)
        elif source == "QQ音乐":
            lrc, tlyric, duration = await cls.search_qq(song_name, artist)
        elif source == "酷狗":
            lrc, tlyric, duration = await cls.search_kugou(song_name, artist)
        else:
            logger.warning("未知歌词源：%s", source)
            return None, 0

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
