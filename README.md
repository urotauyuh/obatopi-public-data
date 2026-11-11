# オバトピ大会情報の自動更新
毎日00:00 JSTのGitHub Actions。PC不要、AI・APIキー不使用。混雑時は遅延あり。
対象：2026 Stage 3 日本・韓国・中国・NA・EMEA・パシフィック・アジア本戦。
NA/EMEAはOverwatch Esports公式、中国はBlizzard/NetEase公式API。日本/韓国/パシフィック/アジアの結果・順位はOWTICS.GGの第三者補助資料と明示。アジアのオンライン日程はWDG公式と照合。
選手名簿はこの処理では更新しない。未確定カードのチーム名、未来の結果、勝敗未掲載の最終順位を捏造しない。
未知のチーム・スキーマ・不正スコア・確定結果との矛盾は地域単位で拒否。取得失敗時は前回の正常データを保持しerrorsへ記録。別年度/Stageへの自動乗換はしない。
有料runner・AI・artifact/cacheは使用しない。通常の公開リポジトリUbuntu runnerで実行。

