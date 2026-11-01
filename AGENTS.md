# agentfile-lint

指令檔（AGENTS.md／CLAUDE.md）的檢查器：規則寫在一份 TOML，執行器只用 Python 標準庫，本機 hook 與 CI 呼叫同一支。

- 本 repo 會公開：追蹤的檔案、commit 與 issue 不寫任何使用者 repo 的名稱或內部細節；設計只寫通用的部分。
- 只用 Python 標準庫（>= 3.11，`tomllib`）；執行器不得新增第三方依賴。
- 開發與驗證：`make check`（等同 `python3 -m unittest discover -s tests`；Python 低於 3.11 會明確失敗，可用 `make check PYTHON=python3.12`）。
- 對自己跑檢查：`python3 -m agentfile_lint`（只掃 git 追蹤的檔案）。
- 子命令：`vendor`、`check-pins`（各引用處釘同一個完整 SHA）、`config --format json`（有效設定的 JSON）。
- 新規則一律以 `warn` 進入預設 preset，升 `error` 要在 CHANGELOG 的 `Graduated` 列出（`tests/test_versioning.py` 檢查）；流程見 `docs/versioning.md`。
- 規則是資料（`agentfile_lint/presets/default.toml` 與 repo 設定檔），行為差異不寫成程式裡的 repo 專屬分支；未知設定鍵一律失敗。
- 輸出格式 `file:line: rule-id: message` 與退出碼（0／1／2）是對外契約；改動要同步更新 `tests/test_contract.py` 並視為 major 變更。
- `tests/fixtures/legacy-oracle/` 是舊檢查器的快照，只供比對，不維護、不修改。
- 設計見 `docs/design.md`，決定見 `docs/adr/`。
