# Login State Tracking Design

## Overview

Adobe Analytics / Customer Journey Analytics デモ用の静的HTMLサイトに、疑似ログイン機能を追加する。ユーザーは全ページ共通ヘッダー右上からアカウント名だけでログインでき、ログイン後はヘッダー上にアカウント名を表示する。ログイン状態はブラウザ保存でページ遷移後も維持し、Adobe Launch の既存 `adobedtm` コードは変更しない。

本対応の目的は、未ログイン状態とログイン状態の両方をAA / CJA上で計測し、さらにログインしたアカウント名をイベント・ページビュー文脈で確認できるようにすること。

## Goals

- 全ページ共通ヘッダー右上に疑似ログイン導線を追加する
- ログイン後にアカウント名をサイト上へ表示する
- ログイン状態を `localStorage` に保存し、ページ遷移・再読み込み後も維持する
- `logged_out` / `logged_in` の状態をページ表示時に計測する
- `login_success` / `logout` 操作イベントを計測する
- ログイン済み時のみ計測データへアカウント名を載せる
- 既存の Debug Window で `/ee` リクエスト上の状態変化を確認できるようにする

## Non-Goals

- 本番利用を前提にした認証・認可の実装
- パスワード入力、メールアドレス入力、セッション期限管理
- 外部認証基盤との連携
- サーバーサイド保存やユーザー管理

## User Experience

### Logged Out

- ヘッダー右上に `Log in` ボタンを表示する
- ボタン押下で、同じヘッダー領域内に小さな入力パネルを展開する
- 入力項目はアカウント名のみとする

### Logged In

- ログイン成功後、ヘッダー右上表示を `こんにちは、<アカウント名>` と `Log out` に切り替える
- 状態は他ページへ遷移しても維持される
- ページ再読み込み後も同じ表示を維持する

### Responsive Behavior

- デスクトップではヘッダー右上に横並びで表示する
- 狭い画面幅では入力欄とボタンを折り返し可能にする
- Hero CTA や既存の主要導線より目立たないサブ機能として扱う

## Functional Design

### Storage Model

- `localStorage` にログイン状態オブジェクトを保存する
- 保存値は以下の最小構成とする
  - `isLoggedIn`: `true` / `false`
  - `accountName`: 文字列
- 保存キー名は実装時に一意で衝突しにくい名称を付ける

### Rendering Model

- 共通ヘッダーを持つ全HTMLに、ログインUIを差し込むためのプレースホルダーを追加する
- 初期表示時に `site.js` が保存状態を読み込み、ヘッダー表示を組み立てる
- `Log in` 押下時のみ入力パネルを表示する
- `Log out` 押下時は保存状態をクリアし、未ログイン表示へ戻す

### Input Validation

- 空文字または空白のみのアカウント名はログイン不可とする
- 前後空白は trim して保存・表示・計測に使用する
- エラー表示は最小限とし、入力欄付近に短い補助文を出す

## Analytics Design

### Page View Context

各ページ表示時に、既存のページビューイベントへ以下のログイン文脈を追加する。

- `login_status`: `logged_out` または `logged_in`
- `account_name`: ログイン済み時のみ付与

### Interaction Events

以下の操作イベントを追加する。

- `login_success`
  - 発火条件: 有効なアカウント名でログインした時
  - 付与値: `login_status=logged_in`, `account_name=<trim済みの値>`
- `logout`
  - 発火条件: `Log out` 押下時
  - 付与値: `login_status=logged_out`
  - `account_name` は付与しない

### Data Layer Strategy

- 既存の `window.adobeDataLayer` 利用方針に合わせる
- ログイン関連データは既存イベント構造に追加し、Launch スニペット本体は変更しない
- 実装時は、既存のページメタ・CTAイベント送信パターンに寄せる

### Debug Window

- 既存の Debug Window は `/ee` リクエスト内容を表示するため、ログイン文脈がEdge送信に乗れば追加UI改修なしでも確認できる可能性が高い
- ただし、現在の重要項目抽出ロジックにログイン関連フィールドが出ない場合は、Debug Window の表示項目に `login_status` と `account_name` を追加する

## Technical Approach

### Files Likely to Change

- `/assets/site.js`
- `/assets/styles.css`
- `/index.html`
- `/product-a.html`
- `/product-b.html`
- `/product-c.html`
- `/order1.html`
- `/order2.html`

### Implementation Boundaries

- ログイン機能は `site.js` 内で独立した小さな責務に分ける
  - ストレージ読み書き
  - ヘッダーUI描画
  - イベントハンドリング
  - analytics payload 補助
- 既存のDebug Window、ページビュー、CTA処理を壊さないことを優先する

## Risks And Mitigations

- ヘッダーHTMLが各ページに分散しているため、差し込み位置のずれが起きる可能性がある
  - 全ページで同じマークアップパターンにそろえてからUIを追加する
- 既存analytics実装のデータ構造とずれると、Launch側で値を拾えない可能性がある
  - 既存のページビュー送信処理と同じ拡張ポイントを使う
- Debug Window に表示されないとデモ確認しづらい
  - 必要に応じて表示抽出ロジックへログイン文脈を追加する

## Acceptance Criteria

- 全6ページのヘッダー右上にログイン導線が表示される
- アカウント名入力のみでログインできる
- ログイン後に `こんにちは、<アカウント名>` が表示される
- ページ遷移および再読み込み後もログイン表示が維持される
- ログアウトで未ログイン表示へ戻る
- ページ表示時に `logged_in` / `logged_out` を判別できるデータが送信される
- ログイン成功時に `login_success`、ログアウト時に `logout` が送信される
- ログイン済み時のアカウント名が送信データ上で確認できる
- Debug Window または `/ee` リクエスト確認により、状態とアカウント名を検証できる

## Testing Approach

- 各ページで未ログイン初期表示を確認する
- ログイン後にヘッダー表示が切り替わることを確認する
- 別ページ遷移後もログイン状態が維持されることを確認する
- 再読み込み後も状態が維持されることを確認する
- ログアウト後に状態が解除されることを確認する
- Debug Window で `login_success` / `logout` / ページ表示時のログイン文脈を確認する

## Recommended Plan Direction

実装計画では、まず既存 `site.js` のページビュー送信ポイントと Debug Window の表示ロジックを特定し、その後に共通ヘッダーUI差し込み、ストレージ管理、analytics拡張、表示確認の順で進めるのが適切である。
