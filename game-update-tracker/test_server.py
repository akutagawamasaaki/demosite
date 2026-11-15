import unittest
from datetime import datetime
from unittest.mock import patch

import server


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 11, 15, tzinfo=tz)


class GachaScheduleTests(unittest.TestCase):
    def test_schedule_keeps_stars_inside_names(self):
        html = (
            '<table><tr><th colspan="4">前半(11/11~12/02)</th></tr>'
            '<tr><td>星神★アッハ</td><td>銀狼LV.999</td><td>火花</td><td>爻光</td></tr>'
            '<tr><th>後半(12/02~12/23)</th></tr><tr><td>後半キャラ</td></tr></table>'
        )
        with patch.object(server, "datetime", FixedDateTime):
            self.assertEqual(server.gw_schedule_banner_chars(html),
                             ["星神★アッハ", "銀狼LV.999", "火花", "爻光"])
        self.assertTrue(server._valid_name("星神☆アッハ"))
        for invalid in ("★★★★★", "★★★★☆", "123", "1.2", ""):
            self.assertFalse(server._valid_name(invalid))

    def test_end_only_periods_and_explicit_year(self):
        rows = [
            ("暴走ルーチェ", "12月10日(木) 10:59まで"),
            ("暴走ソイ", "12月10日(木) 10:59まで"),
            ("山岸風花", "11月26日(木) 10:59まで"),
            ("結城理", "2027年6月26日(土) 10:59まで"),
            ("終了キャラ", "2026年6月26日(金) 10:59まで"),
            ("水着美波", "11月19日(木) から"),
        ]
        html = '<table><tr><th>ガチャ</th><th>開催期間/ピックアップ</th></tr>'
        for name, period in rows:
            html += (f'<tr><td>PICKUP怪ドル契約</td><td>【開催期間】{period}'
                     f'【ピックアップ対象】★5怪盗「{name}」</td></tr>')
        with patch.object(server, "datetime", FixedDateTime):
            self.assertEqual(server.gacha_chars(html + '</table>'),
                             ["暴走ルーチェ", "暴走ソイ", "山岸風花", "結城理"])

    def test_current_range_excludes_upcoming_and_low_rarity(self):
        html = (
            '<table><tr><th>ガチャ</th><th>開催期間/ピックアップ</th></tr>'
            '<tr><td>前半</td><td>【開催期間】2026/11/4~2026/11/24'
            '【ピックアップ対象】★5「ミティヤ」★5「フリーナ」★4「バレリー」</td></tr>'
            '<tr><td>後半</td><td>【開催期間】2026/11/24~2026/12/15'
            '【ピックアップ対象】★5「兹白」★5「リンネア」</td></tr></table>'
        )
        with patch.object(server, "datetime", FixedDateTime):
            self.assertEqual(server.gacha_chars(html), ["ミティヤ", "フリーナ"])


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
