#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ゲーム最新アップデート確認ツール ローカルサーバ

役割:
  - index.html / 静的ファイルの配信（同一オリジンのためCORS不要）
  - GameWith のアプデまとめページを取得し、見出しから更新情報を抽出
  - 取得結果を data.json にキャッシュ

エンドポイント:
  GET  /                     index.html
  GET  /api/games            data.json を返却（無ければ sources.json から雛形生成）
  POST /api/refresh?id=ID    指定タイトルを再取得し data.json を更新
  POST /api/refresh-all      全タイトルを順次再取得

起動: python3 server.py  （ブラウザで http://localhost:8765 ）
"""

import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCES_PATH = os.path.join(BASE_DIR, "sources.json")
DATA_PATH = os.path.join(BASE_DIR, "data.json")
PORT = int(os.environ.get("PORT", "8765"))
JST = timezone(timedelta(hours=9))
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# ----------------------------------------------------------------------------
# GameWith パーサー
# ----------------------------------------------------------------------------
CHAR_SEC = ["新キャラ", "新エージェント", "新オペレーター", "新規キャラ"]
CONTENT_KW = ["新コンテンツ", "新ストーリー", "新マップ", "新エリア", "新任務",
              "新イベント", "新ボス", "新祈願", "新装備", "メインストーリー", "新シティ"]
STOP_KW = ["ガチャ", "音動機", "光円錐", "武器", "ボンプ", "メンテ", "過去",
           "予告番組", "生放送", "交換コード", "配布", "スケジュール", "改善",
           "仕様", "PV", "ロードマップ", "補填"]
JUNK_RE = re.compile(r"(一覧|ランキング|記事|データベース|関連|おすすめ|シミュ|評価|掲示板|まとめ$|の最強|攻略|アイコン|システム|その他)")
BAD_NAME = re.compile(r"(情報|光円錐|音動機|武器|ガチャ|復刻|コンテンツ|ストーリー|イベント|聖遺物|音骸|コラボ|装備|ハーモニー|アクセサリ|^新|・$|^・)")
DATE_RE = re.compile(r"(\d{1,2}[/／]\d{1,2}|\d{4}年\d{1,2}月\d{1,2}日|\d{1,2}月\d{1,2}日)")
NAME_RE = re.compile(r"新キャラ[「【]([^」】]+)[」】]|新キャラ[：:]\s*([^\s、。]+?)(?:が|を|実装|登場|$)")
IMPL_RE = re.compile(r"(?:に|^|・)([ぁ-んァ-ヶ一-龠ー・]{2,10})が(?:実装|登場|参戦)")


def _clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()


PLACEHOLDER_IMG = re.compile(r"transparent1px|blank\.|data:image|/1px\.|spacer", re.I)


def _img_src(tag):
    """img タグから実体の画像URLを返す。遅延読込のプレースホルダ（1px透過等）は
    避け、data-original / data-src を優先する。無ければ src。"""
    for attr in ("data-original", "data-src"):
        m = re.search(attr + r'="([^"]+)"', tag)
        if m and not PLACEHOLDER_IMG.search(m.group(1)):
            return m.group(1)
    m = re.search(r'(?:^|\s)src="([^"]+)"', tag)
    return m.group(1) if m and not PLACEHOLDER_IMG.search(m.group(1)) else None


def _img_map(html):
    """ページ内の <img alt="名前" src="…"> から 名前→画像URL の対応表を作る。"""
    m = {}
    for tag in re.findall(r"<img\b[^>]*>", html, re.I):
        a = re.search(r'alt="([^"]*)"', tag)
        s = _img_src(tag)
        if a and s and a.group(1).strip():
            m.setdefault(a.group(1).strip(), s)
    return m


def parse_gamewith(html):
    """GameWith のアプデまとめページHTMLから更新情報を抽出する。"""
    mt = re.search(r"<title>([^<]*)</title>", html)
    title = _clean(mt.group(1)) if mt else ""
    md = re.search(r'<meta name="description" content="([^"]*)"', html)
    desc = _clean(md.group(1)) if md else ""

    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", html)
    heads = [_clean(h) for h in re.findall(r"(?is)<h[23][^>]*>(.*?)</h[23]>", t)]
    heads = [h for h in heads if h]
    imgs = _img_map(html)

    # バージョン
    blob = title + " " + desc + " " + " ".join(heads[:30])
    vm = re.search(r"Ver\.?\s*([\d.]+)", blob)
    if vm:
        version = "Ver." + vm.group(1)
    else:
        bm = re.search(r"「([^」]+)」", title) or re.search(r"｜([^｜【】]+?)【", title)
        version = bm.group(1).strip() if bm else ""

    # 今後のスケジュール表から「現行より先のバージョン」の予定日を抽出（暫定）
    cur = re.search(r"(\d+\.\d+)", version)
    gw_next = _schedule_next(html, cur.group(1) if cur else None)

    # 新キャラ（名前＋画像）
    names, mode = [], None
    for h in heads:
        nm = NAME_RE.search(h)
        if nm:
            name = (nm.group(1) or nm.group(2) or "").strip()
            if name and not BAD_NAME.search(name) and not JUNK_RE.search(name):
                names.append(name)
                continue
        im = IMPL_RE.search(h)
        if im and "復刻" not in h:
            name = im.group(1).strip()
            if name and not BAD_NAME.search(name) and not JUNK_RE.search(name):
                names.append(name)
        if any(k in h for k in CHAR_SEC) and not JUNK_RE.search(h):
            mode = "char"
            continue
        if any(k in h for k in CONTENT_KW):
            mode = None
            continue
        if any(k in h for k in STOP_KW):
            mode = None
            continue
        if (mode == "char" and 1 < len(h) <= 12
                and not JUNK_RE.search(h) and not BAD_NAME.search(h)
                and not DATE_RE.search(h)):
            names.append(h)

    names = list(dict.fromkeys(names))[:6]
    characters = [{"name": n, "img": imgs.get(n)} for n in names]
    return {
        "version": version,
        "new_characters": characters,
        "summary": desc,
        "gw_next": gw_next,  # (version, date) or None
    }


# ----------------------------------------------------------------------------
# 次バージョン予定日の抽出（GameWithスケジュール表 → gamsgoリーク）
# ----------------------------------------------------------------------------
VTOK_RE = re.compile(r"(\d+)\.(\d+)")
# 年の断片（2026/06 → 26/06）を拾わないよう、スラッシュ表記は前後の数字を除外する
NEXT_DATE_RE = re.compile(
    r"(\d{4}年\d{1,2}月\d{1,2}日|\d{1,2}月\d{1,2}日|\d{1,2}月頃|(?<!\d)\d{1,2}[/／]\d{1,2}(?!\d))")


def _ver_tuple(s):
    m = re.match(r"(\d+)\.(\d+)", s or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def _norm_date(d):
    m = re.search(r"(\d{1,2})月(\d{1,2})日", d)
    if m:
        return f"{int(m.group(1))}/{int(m.group(2))}"
    m = re.search(r"(\d{1,2})月頃", d)
    if m:
        return f"{int(m.group(1))}月頃"
    m = re.search(r"(\d{4})年(\d{1,2})月$", d)
    if m:
        return f"{int(m.group(2))}月頃"
    return d.replace("／", "/")


def _table_rows(html):
    for tbl in re.findall(r"(?is)<table.*?</table>", html):
        for r in re.findall(r"(?is)<tr.*?</tr>", tbl):
            yield " ".join(_clean(c) for c in re.findall(r"(?is)<t[dh].*?</t[dh]>", r))


def _schedule_next(html, cur=None):
    """GameWith の「今後のスケジュール表」から次回アップデートのバージョンと予定日を返す。

    予定日は「今日以降で最も近い行」を採用する。現行版の自動判定は誤りやすい
    （アプデ直前は次版が現行と誤検出される）ため、版番号ではなく日付で選ぶ。
    誤検出を避けるため、表頭に「アップデート日」と「バージョン/Ver」を含む
    スケジュール表のみを対象とする。
    """
    today = datetime.now(JST).date()
    for tbl in re.findall(r"(?is)<table.*?</table>", html):
        head = _clean(tbl)
        if "アップデート日" not in head or ("バージョン" not in head and "Ver" not in head):
            continue
        cands = []
        for r in re.findall(r"(?is)<tr.*?</tr>", tbl):
            row = " ".join(_clean(c) for c in re.findall(r"(?is)<t[dh].*?</t[dh]>", r))
            vm = VTOK_RE.search(row)
            dm = NEXT_DATE_RE.search(row)
            if vm and dm:
                cands.append(((int(vm.group(1)), int(vm.group(2))), dm.group(1)))
        if not cands:
            continue
        # 今日以降で配信日が最も近い行を採用する。
        ahead = [(dt, v, d) for v, d in cands if (dt := _md_date(d)) and dt >= today]
        if ahead:
            _, v, d = min(ahead)
            return (f"{v[0]}.{v[1]}", _norm_date(d))
    return None


BLOCK_IMG = re.compile(
    r"(icon|logo|gamsgo|ブログ|chatgpt|netflix|spotify|youtube|premium|claude|"
    r"twitter|facebook|pinterest|line|reddit|telegram|linkedin|wechat|"
    r"gacha|チャージ|ガチャ|^x$|画像$)", re.I)


def _norm_name(s):
    return re.sub(r"（.*?）|[\s・･、,（）()【】「」]", "", s)


def _char_img_map(html):
    """gamsgo のキャラクター画像から 名前→画像URL の対応表を作る。"""
    m = {}
    for tag in re.findall(r"<img\b[^>]*>", html, re.I):
        a = re.search(r'alt="([^"]*)"', tag)
        s = _img_src(tag)
        if (a and s and a.group(1).strip()
                and "gamsgocdn" in s and not BLOCK_IMG.search(a.group(1))):
            m.setdefault(a.group(1).strip(), s)
    return m


def _match_img(name, imap):
    nn = _norm_name(name)
    if len(nn) < 2:
        return None
    for alt, src in imap.items():
        na = _norm_name(alt)
        if na and (nn in na or na in nn):
            return src
    return None


def _valid_name(nm):
    return nm and len(nm) <= 16 and "。" not in nm and not re.search(r"★|^[\d.]+$", nm)


# GameWith のガチャスケジュール等で「近日実装予定」を示す見出し文の型。
UPCOMING_CHAR_RE = [
    re.compile(r"([ァ-ヶー]{2,8}|[一-龠]{2,6})はいつ実装"),
    re.compile(r"([ァ-ヶー]{2,8}|[一-龠]{2,6})は[一-龠]属性のキャラ"),
    re.compile(r"\d{1,2}月\d{1,2}日\([日月火水木金土]\)([ァ-ヶーA-Za-z一-龠]{2,10})実装"),
]


_GACHA_RANK = re.compile(r"(?:★5|★５|SSランク|Sランク|限定)[^「]{0,8}「([^」]+)」")
_GACHA_BADNAME = re.compile(r"Ver|まで|以降|一覧|交換|スタンダード|通常|\d")


def _gacha_row_chars(name_cell, period_cell):
    """ガチャ表の1行からピックアップキャラ名を取り出す。
    ピックアップ対象「○○」の最高レアを優先し、無ければガチャ名から抽出する。"""
    out = []
    for m in _GACHA_RANK.finditer(period_cell + " " + name_cell):
        nm = re.sub(r"[（(].*?[）)]", "", m.group(1)).strip()
        if _valid_name(nm) and len(nm) >= 2 and not _GACHA_BADNAME.search(nm) and nm not in out:
            out.append(nm)
    if not out and "ガチャ" in name_cell and not re.search(r"武器|祈願|シミュ|PICKUP|契約", name_cell):
        nm = re.sub(r"[（(].*?[）)]", "", name_cell).replace("ガチャ", "").strip()
        if _valid_name(nm) and len(nm) >= 2 and not _GACHA_BADNAME.search(nm):
            out.append(nm)
    return out


def gacha_chars(html):
    """GameWith のガチャスケジュールページから、現在開催中のキャラガチャの
    ピックアップキャラ名を返す。開催中が無ければ直近の開催予定を返す。"""
    today = datetime.now(JST).date()
    cur, upcoming = [], []
    for tbl in re.findall(r"(?is)<table.*?</table>", html):
        flat = _clean(tbl)
        if "おすすめ度" not in flat and "ピックアップ" not in flat:
            continue
        for r in re.findall(r"(?is)<tr.*?</tr>", tbl):
            cells = [_clean(c) for c in re.findall(r"(?is)<t[dh].*?</t[dh]>", r)]
            if len(cells) < 2 or "武器" in cells[0] or "シミュ" in cells[0]:
                continue
            names = _gacha_row_chars(cells[0], " ".join(cells[1:]))
            if not names:
                continue
            period = " ".join(cells[1:])
            dm = re.findall(r"(\d{1,2})[月/／](\d{1,2})", period)
            if not dm:
                continue
            start = _md_date(f"{dm[0][0]}/{dm[0][1]}")
            end = _md_date(f"{dm[1][0]}/{dm[1][1]}") if (len(dm) >= 2 and "から" not in period) else None
            if start and ((end and start <= today <= end) or (not end and start <= today)):
                cur += [n for n in names if n not in cur]
            elif start and start > today:
                upcoming.append((start, names))
        if cur or upcoming:
            break
    if cur:
        return cur[:6]
    if upcoming:
        upcoming.sort(key=lambda x: x[0])
        return upcoming[0][1][:6]
    return []


def gw_upcoming_chars(html, exclude=()):
    """GameWith のガチャスケジュール等から近日実装予定の新キャラ名を抽出する。

    リーク（gamsgo）が無いタイトル向けのフォールバック。
    「○○はいつ実装」「○○は△属性のキャラ」のような未実装キャラ特有の表現を拾う。
    """
    txt = _clean(html)
    imap = _img_map(html)
    ex = {_norm_name(e) for e in exclude if e}
    names = []
    for rx in UPCOMING_CHAR_RE:
        for m in rx.finditer(txt):
            nm = m.group(1).strip()
            nn = _norm_name(nm)
            if (_valid_name(nm) and not BAD_NAME.search(nm) and not JUNK_RE.search(nm)
                    and nn not in ex and nm not in names):
                names.append(nm)
        if names:
            break
    return [{"name": n, "img": _match_img(n, imap)} for n in names[:5]]


def _sched_tables(html):
    for tbl in re.findall(r"(?is)<table.*?</table>", html):
        head = _clean(tbl)
        if "バージョン" in head and ("キャラ" in head or "時期" in head or "実装" in head):
            yield tbl


def _table_next(html, cur):
    """スケジュール表（テーブル）のみから現行版より先のバージョンと予定日を返す。"""
    curt = _ver_tuple(cur)
    if not curt:
        return None
    cands = []
    for tbl in _sched_tables(html):
        for r in re.findall(r"(?is)<tr.*?</tr>", tbl):
            row = " ".join(_clean(c) for c in re.findall(r"(?is)<t[dh].*?</t[dh]>", r))
            vm = VTOK_RE.search(row)
            dm = NEXT_DATE_RE.search(row)
            if vm and dm:
                cands.append(((int(vm.group(1)), int(vm.group(2))), dm.group(1)))
    fut = sorted([(v, d) for v, d in cands if v > curt])
    return (f"{fut[0][0][0]}.{fut[0][0][1]}", _norm_date(fut[0][1])) if fut else None


def _sched_chars(html, nv, imap):
    """スケジュール表のキャラクター列から、対象バージョンの新キャラを抽出する。"""
    out = []
    for tbl in _sched_tables(html):
        for r in re.findall(r"(?is)<tr.*?</tr>", tbl):
            cells = [_clean(c) for c in re.findall(r"(?is)<t[dh].*?</t[dh]>", r)]
            if len(cells) >= 3 and cells[0].startswith(nv):
                nm = re.split(r"[（(]", cells[2])[0].strip()
                if _valid_name(nm) and nm not in out:
                    out.append(nm)
    return [{"name": n, "img": _match_img(n, imap)} for n in out[:5]]


def _banner_chars(html, imap, exclude):
    """バナー記事のキャラクター画像から新キャラを抽出する（現行版キャラは除外）。"""
    ex = {_norm_name(e) for e in exclude if e}
    out, used_src = [], set()
    for alt, src in imap.items():
        if src in used_src:
            continue
        nm = re.split(r"[（(]", alt)[0].strip()
        nn = _norm_name(nm)
        if not _valid_name(nm) or len(nn) < 2 or re.search(r"\d", nm):
            continue
        if any(nn in e or e in nn for e in ex):
            continue
        used_src.add(src)
        out.append({"name": nm, "img": src})
        if len(out) >= 4:
            break
    return out


def gamsgo_next(html, cur):
    """gamsgo 記事から現行版より先のバージョンと予定日を返す。

    日程表（厳密）→ 全テーブルの行 → 本文「Ver/バージョン X.Y …日付」の順に探す。
    """
    curt = _ver_tuple(cur)
    if not curt:
        return None
    # 1) 厳密な日程表
    t = _table_next(html, cur)
    if t:
        return t
    # 2) 全テーブルの行（バージョン＋日付が同一行にあるもの）
    cands = []
    for row in _table_rows(html):
        vm = VTOK_RE.search(row)
        dm = NEXT_DATE_RE.search(row)
        if vm and dm:
            cands.append(((int(vm.group(1)), int(vm.group(2))), dm.group(1)))
    fut = sorted([(v, d) for v, d in cands if v > curt])
    if fut:
        return (f"{fut[0][0][0]}.{fut[0][0][1]}", _norm_date(fut[0][1]))
    # 3) 本文テキスト
    txt = _clean(html)
    txtc = []
    for m in re.finditer(r"(?:Ver\.?|バージョン)\s*(\d+)\.(\d+)[^。\n]{0,30}?" + NEXT_DATE_RE.pattern, txt):
        txtc.append(((int(m.group(1)), int(m.group(2))), m.group(3)))
    fut = sorted([(v, d) for v, d in txtc if v > curt])
    return (f"{fut[0][0][0]}.{fut[0][0][1]}", _norm_date(fut[0][1])) if fut else None


def resolve_gamsgo(url, cur, exclude_chars):
    """gamsgo の URL から次バージョンの「予定日」と「新キャラ（画像付き）」を解決する。

    リーク一覧ページに日程表があればそこから、ハブ（記事一覧）ページなら
    現行版の直後にあたるバナー／リーク記事へ辿って抽出する。
    戻り値: (version, date, characters, 参照URL) ／ 取得不可なら (None, None, [], url)
    """
    html = http_get(url)
    curt = _ver_tuple(cur)

    # A) 設定URL自体に日程表がある（genshin/hsr/wuwa の -leaks ページ）
    t = _table_next(html, cur)
    if t:
        imap = _char_img_map(html)
        chars = _sched_chars(html, t[0], imap) or _banner_chars(html, imap, exclude_chars)
        return t[0], t[1], chars, url

    # B) ハブ → 現行版の直後にあたる最小バージョンのバナー／リーク記事へ辿る
    if curt:
        cands = []
        for m in re.finditer(r'href="(/ja/blog/[a-z0-9\-]+)"', html):
            slug = m.group(1)
            if not re.search(r"(banner|leak)", slug):
                continue
            vm = re.search(r"(\d+)-(\d+)", slug)
            if vm and (int(vm.group(1)), int(vm.group(2))) > curt:
                cands.append(((int(vm.group(1)), int(vm.group(2))), slug))
        for v, slug in sorted(cands):
            art_url = "https://www.gamsgo.com" + slug
            try:
                art = http_get(art_url)
            except Exception:  # noqa: BLE001
                continue
            res = gamsgo_next(art, cur)
            if res:
                imap = _char_img_map(art)
                chars = (_sched_chars(art, res[0], imap)
                         or _banner_chars(art, imap, exclude_chars))
                return res[0], res[1], chars, art_url

    # C) 本文テキストから日付のみ
    res = gamsgo_next(html, cur)
    if res:
        imap = _char_img_map(html)
        chars = _banner_chars(html, imap, exclude_chars)
        return res[0], res[1], chars, url
    return (None, None, [], url)


# data-rank-pattern → ランクラベル（tier番号1始まりで対応づけ）
TIER_LABELS = {
    "1": ["SS", "S", "A", "B", "C"],
    "2": ["SS", "S+", "S", "A+", "A", "B", "C"],
    "4": ["SS", "S", "A", "B", "C", "D", "E"],
}
TIER_LABELS_DEFAULT = ["SS", "S+", "S", "A+", "A", "B", "C", "D"]


def _tier_widget(html):
    """先頭の w-tier-table-ui ウィジェットから (labels, [(name, tier, img), ...]) を返す。"""
    i = html.find("w-tier-table-ui")
    if i < 0:
        return [], []
    pm = re.search(r'data-rank-pattern="([^"]*)"', html[i:i + 260])
    labels = TIER_LABELS.get(pm.group(1) if pm else "", TIER_LABELS_DEFAULT)
    j = html.find("</ol>", i)
    block = html[i:j] if j > 0 else html[i:i + 60000]
    items = []
    for li in re.findall(r"<li ([^>]*)>", block):
        nm = re.search(r'd-name="([^"]*)"', li)
        tm = re.search(r'd-tier="(\d+)"', li)
        im = re.search(r'd-img="([^"]*)"', li)
        if nm and tm and nm.group(1).strip():
            items.append((nm.group(1).strip(), int(tm.group(1)), im.group(1) if im else ""))
    return labels, items


def _tier_links(html):
    """ティアウィジェットの各キャラの個別ページURL（d-link）を 名前→URL で返す。"""
    i = html.find("w-tier-table-ui")
    if i < 0:
        return {}
    j = html.find("</ol>", i)
    block = html[i:j] if j > 0 else html[i:i + 60000]
    m = {}
    for li in re.findall(r"<li ([^>]*)>", block):
        nm = re.search(r'd-name="([^"]*)"', li)
        lk = re.search(r'd-link="([^"]*)"', li)
        if nm and lk and nm.group(1).strip():
            m.setdefault(nm.group(1).strip(), lk.group(1))
    return m


def _md_date(s):
    """ "7/1" や "7月1日" を当年の date に変換する。比較不能なら None。 """
    m = re.search(r"(\d{1,2})[/／](\d{1,2})", s or "") or re.search(r"(\d{1,2})月(\d{1,2})日", s or "")
    if not m:
        return None
    try:
        return datetime(datetime.now(JST).year, int(m.group(1)), int(m.group(2))).date()
    except ValueError:
        return None


def _pick_future(dates):
    """候補日付（"M/D" 等の文字列）から、今日以降で最も近い日付を選んで返す。

    過去日は採用しない。該当が無ければ ""。
    年末年始をまたぐ場合（半年以上前の日付＝翌年扱い）にも対応する。
    """
    today = datetime.now(JST).date()
    parsed = [(dt, d) for d in dates if (dt := _md_date(d))]
    future = [(dt, d) for dt, d in parsed if dt >= today]
    if future:
        return min(future)[1]
    roll = [(dt.replace(year=dt.year + 1), d) for dt, d in parsed if (today - dt).days > 180]
    return min(roll)[1] if roll else ""


def parse_tier(html):
    """最強キャラランキングを上位4ランクだけ返す。戻り値: [{rank, chars:[...]}]（強い順）。"""
    labels, items = _tier_widget(html)
    by_tier = {}
    for name, tier, _ in items:
        by_tier.setdefault(tier, []).append(name)
    out = []
    for t in sorted(by_tier):
        rank = labels[t - 1] if 1 <= t <= len(labels) else f"Tier{t}"
        out.append({"rank": rank, "chars": by_tier[t]})
    return out[:4]


def pu_end_date(html):
    """次回アップデートの予測日を取り出す。戻り値: "M/D"（無ければ ""）。

    ページ内の候補日を集め、今日以降で最も近い日付を返す（過去日は採用しない）。
    候補は次の3種類。
    1) 「開催期間 …〜 M月D日 / M/D」= ピックアップ／ガチャの終了日（＝次回開始日）。
       イベント（タワーバトル等）の終了日はアップデート日ではないため除外する。
    2) 「M月D日(曜)…実装 / M/D(曜)…実装」= 実装日が明記されている場合
    3) 「M月D日(曜)…公式放送/生放送」= 次回告知の番組日（≒直近の節目）
    """
    txt = _clean(html)
    cands = []
    for m in re.finditer(r"開催期間[^〜～~]{0,40}[〜～~]\s*(?:\d{4}年)?\s*(\d{1,2})[月/](\d{1,2})", txt):
        ctx = txt[max(0, m.start() - 40):m.end() + 45]
        has_gacha = re.search(r"ガチャ|ピックアップ|PU", ctx)
        has_event = re.search(r"イベント|タワー|ログインボーナス|総選挙|キャンペーン|攻略", ctx)
        if has_event and not has_gacha:
            continue  # イベント終了日は次回更新日ではないので除外
        cands.append(f"{int(m.group(1))}/{int(m.group(2))}")
    for m in re.finditer(r"(\d{1,2})[月/](\d{1,2})日?\([日月火水木金土]\)[^。]{0,12}(?:実装|リリース)", txt):
        cands.append(f"{int(m.group(1))}/{int(m.group(2))}")
    for m in re.finditer(r"(\d{1,2})月(\d{1,2})日\([日月火水木金土]\)[^。]{0,18}(?:公式放送|生放送|特番|放送)", txt):
        cands.append(f"{int(m.group(1))}/{int(m.group(2))}")
    return _pick_future(cands)


def parse_tier_gamerch(html):
    """gamerch（カオゼロ等）の最強ランキングから上位3ランクを返す。
    総合タブ（tab-1）の strongest ブロックを使う。戻り値: [{rank, chars:[...]}]
    """
    i = html.find('data-tab-body="tab-1"')
    k = html.find('data-tab-body="tab-2"')
    body = html[i:k] if (i >= 0 and k > i) else (html[i:] if i >= 0 else html)
    marks = list(re.finditer(r'class="strongest-t\d+"[^>]*>\s*<p>([^<]+)</p>', body))
    out = []
    for idx, m in enumerate(marks):
        rank = _clean(m.group(1))
        end = marks[idx + 1].start() if idx + 1 < len(marks) else m.end() + 5000
        seg = body[m.end():end]
        names = list(dict.fromkeys(a for a in re.findall(r'alt="([^"]+)"', seg) if a))
        if rank and names:
            out.append({"rank": rank, "chars": names})
    return out[:4]


_LATEST_STOP = re.compile(r"(最強キャラランキング|評価履歴|みんな|最強評価の基準|の評価詳細|キャラ一覧)")
_LATEST_DELIM = set(" 　\t「（(：:/／、，＞>】▼｜|』\"")


def latest_chars(html):
    """ティアページの「最新キャラ」節から現行の新規・復刻キャラ名を抽出する。
    取れない場合はガチャアイコン番号が最大（＝直近実装）のキャラ1体を返す。
    """
    labels, items = _tier_widget(html)
    if not items:
        return []
    txt = _clean(html)
    rost = sorted({n for n, _, _ in items if len(n) >= 2}, key=len, reverse=True)
    for m in re.finditer(r"最新キャラ(?:の評価|考察|情報まとめ|の最強ランキング)?", txt):
        region = txt[m.end():m.end() + 110]
        st = _LATEST_STOP.search(region)
        if st:
            region = region[:st.start()]
        masked, found = region, []
        for n in rost:
            for mt in re.finditer(re.escape(n), masked):
                before = masked[mt.start() - 1] if mt.start() > 0 else " "
                if before in _LATEST_DELIM:
                    found.append((mt.start(), n))
                    masked = masked[:mt.start()] + ("\x00" * len(n)) + masked[mt.end():]
                    break
        if found:
            return [n for _, n in sorted(found)]
    # フォールバック: ガチャアイコン番号が最大のキャラ（直近実装）
    best = None
    for name, _, img in items:
        m = re.search(r"(\d+)(?!.*\d)", img)
        if m and (best is None or int(m.group(1)) > best[0]):
            best = (int(m.group(1)), name)
    return [best[1]] if best else []


def http_get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ja"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return raw.decode("utf-8", errors="replace")


# ----------------------------------------------------------------------------
# データ管理
# ----------------------------------------------------------------------------
def load_sources():
    with open(SOURCES_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_data():
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, encoding="utf-8") as f:
            return json.load(f)
    # 雛形（未取得状態）
    games = []
    for s in load_sources():
        g = dict(s)
        g.update({"version": "", "release_date": "", "next_version": "",
                  "date_source": "", "date_url": s.get("url", ""),
                  "new_characters": [], "leak_characters": [], "leak_url": "",
                  "char_links": {}, "gacha_url": s.get("gacha_url") or s.get("next_date_url") or "",
                  "summary": "", "tier": [], "banner_chars": [],
                  "fetched_at": None, "error": None})
        games.append(g)
    return {"updated_at": None, "games": games}


def save_data(data):
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def now_iso():
    return datetime.now(JST).isoformat(timespec="seconds")


def refresh_one(source, prev=None):
    """1タイトルを取得・解析し、ソース情報とマージした辞書を返す。

    次バージョンの予定日は GameWith のスケジュール表を優先し、
    無ければ gamsgo のリーク記事を参照する。出典は date_source に保持する。

    取得に失敗した場合、前回の正常データ（prev）があればそれを保持し、
    エラーで上書きしない（クラウド実行時の 403 等で表示が壊れるのを防ぐ）。
    """
    g = dict(source)
    provider = source.get("provider", "gamewith")
    try:
        # 更新ページ（バージョン・スケジュール）の解析は GameWith 提供のみ
        gw_next, gw_chars, gw_new = None, [], []
        if provider == "gamewith":
            parsed = parse_gamewith(http_get(source["url"]))
            gw_next = parsed.pop("gw_next", None)
            gw_new = parsed.pop("new_characters", [])  # 更新ページの新キャラ（名前＋画像）
            gw_chars = [c["name"] for c in gw_new]
            g.update(parsed)
        else:
            g.update({"version": "", "summary": ""})

        curm = re.search(r"(\d+\.\d+)", g.get("version", ""))
        cur = curm.group(1) if curm else source.get("ver_hint", "")
        next_ver, release, date_source, date_url = "", "未定", "", source["url"]

        # リーク新キャラ（と配信予定日）を gamsgo から取得する。
        # ゲーム名は新キャラ画像の誤検出になりやすいので除外語に含める。
        exclude = gw_chars + [source.get("name", ""), source.get("short", "")]
        leak = None  # (next_version, date, url)
        leak_chars = []  # gamsgo のリーク新キャラ（画像付き）
        leak_url = ""    # リーク出典（gamsgo記事）URL
        if source.get("gamsgo"):
            try:
                nv, rel, chars, used = resolve_gamsgo(source["gamsgo"], cur, exclude)
            except Exception:  # noqa: BLE001
                nv, rel, chars, used = None, None, [], source["gamsgo"]
            leak_chars = chars
            leak_url = used or source["gamsgo"]
            if nv:
                leak = (nv, rel, used)

        # 配信予定日: GameWith に次回配信予定日があれば（暫定でも）それを採用。
        # GameWith に次回日が無い場合のみ、リーク（gamsgo）を採用する。
        # 優先順位: GameWith の次回予定日 → 現行PU終了日の予測 → リーク（gamsgo）
        pu = ""
        nd_html = None
        if source.get("next_date_url"):
            try:
                nd_html = http_get(source["next_date_url"])
                pu = pu_end_date(nd_html)
            except Exception:  # noqa: BLE001
                nd_html, pu = None, ""

        # ガチャの最新キャラはティアページの「最新キャラ」節から構成する（後段）。
        new_chars = []

        if gw_next:
            next_ver, release = gw_next
            date_source, date_url = "GameWith（暫定）", source["url"]
        elif pu:
            release, date_source, date_url = pu, "予測（PU終了日）", source["next_date_url"]
        elif leak:
            next_ver, release, date_url = leak[0], leak[1], leak[2]
            date_source = "gamsgo（リーク）"
        elif source.get("next_date_url"):
            # 予定日が取れなくても、出典はGameWithのガチャページに向ける。
            date_source, date_url = "GameWith（ガチャ）", source["next_date_url"]

        g.update({"release_date": release, "next_version": next_ver,
                  "date_source": date_source, "date_url": date_url,
                  "new_characters": new_chars, "leak_characters": leak_chars,
                  "leak_url": leak_url, "char_links": {},
                  "gacha_url": source.get("gacha_url") or source.get("next_date_url") or ""})

        # 最強キャラランキング（tier_url がある場合のみ）。
        # 赤字対象（現行の新規・復刻キャラ）はティアページの「最新キャラ」節から取る。
        if source.get("tier_url"):
            try:
                tier_html = http_get(source["tier_url"])
                if provider == "gamerch":
                    tier = parse_tier_gamerch(tier_html)
                    g["banner_chars"] = []
                else:
                    tier = parse_tier(tier_html)
                    g["banner_chars"] = latest_chars(tier_html)
                    # キャラガチャ: ガチャスケジュールページの開催中ピックアップを優先。
                    # 取得できない場合はティアページの「最新キャラ」を使う。サムネはティアページ。
                    names = []
                    if source.get("gacha_url"):
                        try:
                            names = gacha_chars(http_get(source["gacha_url"]))
                        except Exception:  # noqa: BLE001
                            names = []
                    if not names:
                        names = g["banner_chars"]
                    timg = {n: img for n, _, img in _tier_widget(tier_html)[1] if img}
                    tlink = _tier_links(tier_html)
                    g["char_links"] = tlink
                    g["new_characters"] = [{"name": n, "img": _match_img(n, timg),
                                            "url": _match_img(n, tlink)} for n in names]
            except Exception:  # noqa: BLE001
                tier = []
                g["banner_chars"] = []
            g["tier"] = tier
            g["tier_url"] = source["tier_url"]
        else:
            g["tier"] = []
            g["banner_chars"] = []

        g["fetched_at"] = now_iso()
        g["error"] = None
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
        # 前回の正常データがあれば保持し、エラーで上書きしない。
        if prev and not prev.get("error") and prev.get("release_date") not in (None, "", "未定"):
            g = dict(prev)
            g.update({k: source[k] for k in source})  # ソース定義は最新に追従
            g["error"] = err
            g["stale_since"] = prev.get("fetched_at")
            return g
        g.update({"version": "", "release_date": "未定", "next_version": "",
                  "date_source": "", "date_url": source.get("url", ""),
                  "new_characters": [], "leak_characters": [], "leak_url": "",
                  "char_links": {}, "gacha_url": source.get("gacha_url") or source.get("next_date_url") or "",
                  "summary": "", "tier": [], "banner_chars": []})
        g["fetched_at"] = now_iso()
        g["error"] = err
    return g


def refresh(ids=None):
    sources = load_sources()
    if ids:
        sources = [s for s in sources if s["id"] in ids]
    data = load_data()
    by_id = {g["id"]: g for g in data["games"]}
    for s in sources:
        by_id[s["id"]] = refresh_one(s, prev=by_id.get(s["id"]))
        time.sleep(0.4)  # 取得元への配慮
    # sources.json の順序を維持
    order = [s["id"] for s in load_sources()]
    data["games"] = [by_id[i] for i in order if i in by_id]
    data["updated_at"] = now_iso()
    save_data(data)
    return data


# ----------------------------------------------------------------------------
# HTTP ハンドラ
# ----------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, name, ctype):
        path = os.path.join(BASE_DIR, name)
        if not os.path.exists(path):
            self._send(404, {"error": "not found"})
            return
        with open(path, "rb") as f:
            self._send(200, f.read(), ctype)

    def do_GET(self):
        p = urlparse(self.path)
        if p.path in ("/", "/index.html"):
            self._serve_file("index.html", "text/html; charset=utf-8")
        elif p.path == "/sources.json":
            self._serve_file("sources.json", "application/json; charset=utf-8")
        elif p.path == "/api/games":
            self._send(200, load_data())
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        p = urlparse(self.path)
        try:
            if p.path == "/api/refresh":
                q = parse_qs(p.query)
                gid = q.get("id", [None])[0]
                if not gid:
                    self._send(400, {"error": "id required"})
                    return
                data = refresh(ids=[gid])
                game = next((g for g in data["games"] if g["id"] == gid), None)
                self._send(200, {"updated_at": data["updated_at"], "game": game})
            elif p.path == "/api/refresh-all":
                self._send(200, refresh())
            else:
                self._send(404, {"error": "not found"})
        except Exception as e:  # noqa: BLE001
            self._send(500, {"error": f"{type(e).__name__}: {e}"})


def main():
    os.chdir(BASE_DIR)

    # ヘッドレス更新モード（GitHub Actions などサーバを立てない環境用）
    # python3 server.py --refresh  → 全タイトルを取得して data.json を書き出し終了
    if "--refresh" in sys.argv:
        data = refresh()
        print(f"updated_at: {data['updated_at']}")
        for g in data["games"]:
            nv = g.get("next_version") or "-"
            bc = ", ".join(g.get("banner_chars", [])) or "-"
            err = f"  ERROR: {g['error']}" if g.get("error") else ""
            print(f"  {g['short']}: 次{nv} {g['release_date']} / tier{len(g.get('tier', []))}段 / 最新[{bc}]{err}")
        return

    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://localhost:{PORT}/"
    print(f"ゲーム最新アップデート確認ツール 起動: {url}")
    print("停止: Ctrl+C")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n停止しました。")
        httpd.shutdown()


if __name__ == "__main__":
    main()
