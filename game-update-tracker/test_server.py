import unittest
from datetime import datetime
from unittest.mock import patch

import server


class LeakAndThumbnailTests(unittest.TestCase):
    def test_article_does_not_follow_another_games_related_link(self):
        html = (
            '<article><img alt="NTE クロバネ" width="96" height="96" '
            'src="https://static.gamsgocdn.com/image/crow.webp">'
            '<a href="/ja/blog/arknights-endfield-1-6-banners">関連記事</a></article>'
        )
        with patch.object(server, "gamsgo_get", return_value=html) as get:
            _, _, chars, _ = server.resolve_gamsgo(
                "https://www.gamsgo.com/ja/blog/nte-leaks", "1.4", ["NTE"]
            )
        self.assertEqual(chars, [{
            "name": "クロバネ",
            "img": "https://static.gamsgocdn.com/image/crow.webp",
        }])
        get.assert_called_once()

    def test_cached_articles_have_game_specific_portraits(self):
        for slug, name, prefix in (
            ("hsr-leaks", "パール", "スタレ"),
            ("nte-leaks", "クロバネ", "NTE"),
        ):
            url = "https://www.gamsgo.com/ja/blog/" + slug
            with open(server._gamsgo_cache_path(url), encoding="utf-8") as f:
                html = f.read()
            with self.subTest(slug=slug), patch.object(server, "gamsgo_get", return_value=html):
                _, _, chars, _ = server.resolve_gamsgo(url, "", [prefix])
                self.assertIn(name, [c["name"] for c in chars])
                self.assertTrue(all("REPLACE_ME" not in c["img"] for c in chars))
                self.assertNotIn("アークナイツ：エンドフィールド", [c["name"] for c in chars])

    def test_gacha_uses_schedule_image_when_tier_and_leak_have_none(self):
        source = {
            "id": "starrail", "name": "崩壊：スターレイル", "short": "スタレ",
            "url": "news", "next_date_url": "schedule", "tier_url": "tier",
        }
        schedule = (
            '<img alt="パール" src="https://img.gamewith.jp/pearl.png">'
        )
        with (
            patch.object(server, "http_get", side_effect=lambda url: schedule if url == "schedule" else ""),
            patch.object(server, "parse_gamewith", return_value={"version": "Ver.4.6"}),
            patch.object(server, "gacha_chars", return_value=[]),
            patch.object(server, "gw_schedule_banner_chars", return_value=["パール"]),
        ):
            game = server.refresh_one(source)
        self.assertEqual(game["new_characters"], [{
            "name": "パール", "img": "https://img.gamewith.jp/pearl.png", "url": None,
        }])

    def test_nte_current_pickup_overrides_stale_tier_banner(self):
        source = next(s for s in server.load_sources() if s["id"] == "nte")
        self.assertEqual(source["gacha_url"], source["next_date_url"])
        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 10, 26, tzinfo=tz)

        schedule = (
            '<table><tr><th>ガチャ</th><th>おすすめ度/開催期間/ピックアップ</th></tr>'
            '<tr><td>一番星</td><td>【開催期間】10月21日~11月11日まで'
            '【ピックアップ対象】Sランクキャラ「明音凛」</td></tr></table>'
        )
        with (
            patch.object(server, "http_get", side_effect=lambda url: schedule if url == source["gacha_url"] else ""),
            patch.object(server, "parse_gamewith", return_value={"version": "Ver.1.0"}),
            patch.object(server, "parse_tier", return_value=[]),
            patch.object(server, "latest_chars", return_value=["クロバネ"]),
            patch.object(server, "_tier_widget", return_value=([], [("明音凛", 1, "https://img.gamewith.jp/akane.png")])),
            patch.object(server, "_tier_links", return_value={"明音凛": "https://gamewith.jp/nte/573344"}),
            patch.object(server, "resolve_gamsgo", return_value=(None, None, [], source["gamsgo"])),
            patch.object(server, "datetime", FixedDateTime),
        ):
            game = server.refresh_one(source)
        self.assertIsNone(game["error"])
        self.assertEqual(game["new_characters"], [{
            "name": "明音凛", "img": "https://img.gamewith.jp/akane.png",
            "url": "https://gamewith.jp/nte/573344",
        }])


if __name__ == "__main__":
    unittest.main()
