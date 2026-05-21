# Contributing to Tango Note

Tango Note への貢献を歓迎します。/ Contributions are welcome.

## Issue

- バグ報告: `.github/ISSUE_TEMPLATE/bug_report.md` のテンプレートを使用してください。
- 機能要望: `.github/ISSUE_TEMPLATE/feature_request.md` のテンプレートを使用してください。

## Pull Request

1. リポジトリを Fork する。
2. 作業用ブランチを切る (`git checkout -b feature/your-feature`)。
3. 変更を加える。
4. テストが通ることを確認する (`pytest`)。
5. Commit して Push する。
6. Pull Request を作成する。

## 開発環境のセットアップ / Development setup

```
pip install -e ".[dev]"
pytest
```

## 設計方針 / Design principles

- `core` / `cli` / `gui` の 3 層構造を維持する。
- `core` は `cli` / `gui` を import しない (依存方向は一方向)。
- 表示文字列は `_("...")` でラップする (i18n 対応)。
