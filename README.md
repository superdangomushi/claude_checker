# Claude Checker 🔋

macOSのメニューバーに、Claude Codeの使用上限（Claude公式が返す 5時間 / 7日間 のリミット）をバッテリーのように常駐表示するアプリ。

```
🟢 87%   ← メニューバーに常駐
```

クリックすると詳細メニュー:

```
Remaining (5h): 87%
─────────────
5h:  13% used
7d:  4% used
Reset in: 3h 24m
─────────────
Source: Claude Code (live)
Fallback plan: Max 5x
Change Fallback Plan ▸
─────────────
Refresh
Quit
```

## 仕組み

Claude Code は APIレスポンスのヘッダーから `rate_limits.{five_hour, seven_day}.used_percentage` を抜き出して、statusLine hook の stdin JSON に渡してくる。

このプロジェクトはそれを利用します:

1. `statusline_bridge.py` を Claude Code の `statusLine` 設定として登録
2. Claude Code が API を叩くたびに、bridgeが stdin JSON を受信
3. `rate_limits` を `~/.claude_battery_state.json` に保存
4. メニューバーアプリは 30秒おきにそのファイルを読んで表示

statusLine 自体には何も出力しないので、画面下のUIには影響しません（メニューバーだけに集約）。

### フォールバック

Claude Code がまだAPI呼び出ししてない（= state ファイルが空）場合は、`~/.claude/projects/**/*.jsonl` を5時間ウィンドウで集計する**推定モード**にフォールバックします。プランは右クリックメニューから選択可能（Pro / Max 5x / Max 20x）。
これなんかトークンの総量がおかしいので、あんまり信頼しない方がいいです。


## インストール

```bash
./install.sh
```

実行内容:

- `~/Library/Application Support/ClaudeBattery/` にコード + venv を作成
- `rumps`, `pyobjc` をインストール
- `~/.claude/settings.json` に `statusLine` フックを追加（既存はバックアップ）
- `~/Library/LaunchAgents/com.user.claudebattery.plist` を作って `launchctl load`

ログイン時に自動起動、クラッシュしても復活します。

## アンインストール

```bash
./uninstall.sh
```

LaunchAgent停止、ファイル削除、`settings.json` の `statusLine` エントリも自動で外します。

## トラブルシュート

- **メニューバーに出ない** → ログを確認: `~/Library/Application Support/ClaudeBattery/stderr.log`
- **`Source: JSONL estimate` のまま** → Claude Codeで1回API呼び出し（メッセージ送信）すれば `Claude Code (live)` に切り替わります
- **すぐ反映したい** → アイコンクリック → `Refresh`

## 要件

- macOS (Apple Silicon / Intel どちらも可)
- Python 3.8+
- Claude Code (subscription user)

API key ユーザーは Anthropic から rate_limits が返らないので、推定モードのみになります。
