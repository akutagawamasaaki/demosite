# ゲーム最新アップデート一覧

基本プレイ無料ゲームの次回アップデート予定日・新キャラ・最強キャラランキングを一覧表示するツール。
データは GameWith と gamsgo（リーク）から取得する。

対象: 原神 / 崩壊：スターレイル / ゼンレスゾーンゼロ / 鳴潮 / アークナイツ：エンドフィールド / NTE / ペルソナ5: The Phantom X

## 構成

| ファイル | 役割 |
|---|---|
| `index.html` | 一覧画面。ローカルサーバ接続時はライブ取得、静的配信時は `data.json` を直読み |
| `server.py` | ローカルサーバ＋取得・解析ロジック。`--refresh` でヘッドレス更新も可能 |
| `sources.json` | タイトルごとの取得元URL定義 |
| `data.json` | 取得結果（これが画面の表示データ） |
| `game-updates.html` | データ埋め込み済みの単体版（ファイルを直接開いて閲覧） |
| `start.command` | Mac用ランチャー（ダブルクリックで起動） |
| `.github/workflows/update.yml` | 6時間ごとに `data.json` を自動更新するワークフロー |

## ローカルで使う（Mac）

`start.command` をダブルクリック → ブラウザで `http://localhost:8765/` が開く → 「すべて更新」。
Python3 が必要（初回は `xcode-select --install`）。

## GitHub Pages で公開する（閲覧側は不要、自動更新）

1. GitHub で公開リポジトリを作成する。
2. このフォルダを push する。

   ```bash
   git remote add origin https://github.com/<ユーザー名>/<リポジトリ名>.git
   git push -u origin main
   ```

3. リポジトリの **Settings → Pages** で、Source を **Deploy from a branch** にし、Branch を **main / (root)** にして Save。
4. リポジトリの **Settings → Actions → General → Workflow permissions** を **Read and write permissions** にする（ボットが `data.json` を push できるようにするため）。
5. 数分後、`https://<ユーザー名>.github.io/<リポジトリ名>/` で閲覧できる。別PCはこのURLを開くだけ。

### 更新のされ方

- `.github/workflows/update.yml` が 6時間ごとに `python3 server.py --refresh` を実行し、`data.json` が変わっていればコミットする。
- コミットを検知して Pages が自動再公開するため、閲覧者は常に最新を見られる。
- すぐ更新したいときは **Actions タブ → Update game data → Run workflow** で手動実行できる。

## 留意事項

- 静的配信（Pages）ではブラウザから直接ゲームサイトを取得できない（CORS）ため、画面の「すべて更新」ボタンは表示されない。更新はワークフローが担う。
- 取得元サイトの構造が変わると一部の抽出がずれることがある。
- gamsgo のバージョン固有URL（ゼンゼロ・エンドフィールド以外のリーク）は恒久URLだが、必要に応じて `sources.json` を見直す。
