"""抖音分享页 SSR 解析单测（不依赖外网）。"""
from app.downloaders.douyin_downloader import (
    _find_aweme_detail,
    _music_url,
    _best_play_url,
    _parse_render_data,
    _normalize_duration,
    DouyinDownloader,
)


def test_parse_router_data_and_item_list():
    html = r"""
    <html><body>
    <script>
    window._ROUTER_DATA = {
      "loaderData": {
        "video_(id)/page": {
          "videoInfoRes": {
            "item_list": [{
              "aweme_id": "7123456789012345678",
              "desc": "测试标题 #话题",
              "music": {
                "play_url": {
                  "uri": "https://example.com/music.mp3",
                  "url_list": ["https://example.com/music.mp3"]
                }
              },
              "video": {
                "duration": 15000,
                "cover": {"url_list": ["https://example.com/cover.jpg"]},
                "play_addr": {
                  "url_list": [
                    "https://example.com/playwm/a",
                    "https://example.com/playwm/b"
                  ]
                },
                "bit_rate": [{
                  "bit_rate": 1000,
                  "play_addr": {
                    "url_list": ["https://example.com/playwm/low", "https://example.com/playwm/hi"]
                  }
                }]
              },
              "video_tag": [{"tag_name": "话题"}]
            }]
          }
        }
      }
    };
    </script>
    </body></html>
    """
    data = _parse_render_data(html)
    assert data, "应解析出 _ROUTER_DATA"
    aweme = _find_aweme_detail(data)
    assert aweme["aweme_id"] == "7123456789012345678"
    assert aweme["desc"].startswith("测试标题")
    assert _music_url(aweme).endswith("music.mp3")
    play = _best_play_url(aweme["video"])
    assert "playwm" not in play
    assert play.endswith("/hi") or "hi" in play
    assert _normalize_duration(15000) == 15.0


def test_parse_render_data_script_tag():
    import urllib.parse
    import json

    payload = {
        "aweme": {
            "detail": {
                "aweme_id": "99",
                "desc": "from render_data",
                "video": {"duration": 3, "play_addr": {"url_list": ["https://x/play"]}},
            }
        }
    }
    encoded = urllib.parse.quote(json.dumps(payload, ensure_ascii=False))
    html = f'<script id="RENDER_DATA" type="application/json">{encoded}</script>'
    data = _parse_render_data(html)
    aweme = _find_aweme_detail(data)
    assert aweme["aweme_id"] == "99"
    assert aweme["desc"] == "from render_data"


def test_extract_video_id_from_long_url():
    dy = DouyinDownloader()
    vid = dy.extract_video_id("https://www.douyin.com/video/7123456789012345678?from=copy")
    assert vid == "7123456789012345678"
    vid2 = dy.extract_video_id(
        "看看这个 https://www.iesdouyin.com/share/video/7987654321098765432/ 复制打开抖音"
    )
    assert vid2 == "7987654321098765432"


def test_extract_video_id_from_modal_id():
    """网页版弹窗链接：id 只在 modal_id 查询参数里，路径是 /user/self。"""
    dy = DouyinDownloader()
    url = (
        "https://www.douyin.com/user/self?from_tab_name=main"
        "&modal_id=7695269189719772450&showTab=favorite_collection"
    )
    assert dy.extract_video_id(url) == "7695269189719772450"


def test_extract_video_id_from_other_query_forms():
    dy = DouyinDownloader()
    assert dy.extract_video_id("https://www.douyin.com/discover?modal_id=7412345678901234567") == \
        "7412345678901234567"
    assert dy.extract_video_id("https://www.douyin.com/user/MS4wLjAB?aweme_id=7312345678901234567") == \
        "7312345678901234567"
    assert dy.extract_video_id("https://www.douyin.com/share/video/7212345678901234567") == \
        "7212345678901234567"


def test_extract_video_id_ignores_bad_links():
    dy = DouyinDownloader()
    # 没有作品 id 的列表页
    assert dy.extract_video_id("https://www.douyin.com/user/self?showTab=favorite_collection") == ""
    assert dy.extract_video_id("") == ""


def test_url_parser_douyin_modal_id():
    from app.utils.url_parser import extract_video_id

    url = "https://www.douyin.com/user/self?from_tab_name=main&modal_id=7695269189719772450"
    assert extract_video_id(url, "douyin") == "7695269189719772450"
    assert extract_video_id("https://www.douyin.com/video/7123456789012345678", "douyin") == \
        "7123456789012345678"
