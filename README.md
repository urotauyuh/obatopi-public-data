# オバトピ大会データの自動取得（AIなし）

公開公式データ専用。動画・個人ファイル・APIキーは置かない。
GitHub Actionsの標準Ubuntu runnerで毎日0時JSTに予約。PC不要、AI呼出しなし。
混雑時の実行遅延はあり得る。Actionsの有料runner・artifact・cacheは使わない。

## 現在の対応範囲

- NA/EMEA 2026 Stage 3の公式日程・結果と公式掲載順位。
- 順位は試合結果から推測せず、公式表の掲載順・表題・更新日をそのまま保持。
- JP/KR/CNや名簿は自動取得未対応。以前の確認日を更新しない。
- 未知の選手・チーム、別年度・別Stageを勝手に混ぜない。
- 取得・検査失敗時は正常な前回データを維持し、失敗状態を保存。

## 接続前

2026-11-05にGitHub Actionsの試運転成功とサイトへの接続・公開表示を確認。
観戦ナビ: https://owcs-japan-navi.urotauyuh.chatgpt.site
取得JSON: https://raw.githubusercontent.com/urotauyuh/obatopi-public-data/main/data.json
サイトは固定の公開データURLを読み、ロスターの確認日を勝手に進めない。
対応範囲は上記NA/EMEAのみ。全地域の自動更新が完成したという意味ではない。
