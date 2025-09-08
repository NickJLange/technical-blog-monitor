# テクニカルブログ・モニター

このプロジェクトは各社のテクニカルブログを監視し、ブラウザでレンダリングして本文とスクリーンショットを抽出し、テキストと画像の埋め込みを生成してベクタDBに保存するデーモンです。

## セットアップ (macOS / Python 3.11)

1) 依存関係のインストール

```
poetry install --with dev
poetry run playwright install
```

2) 環境変数

```
cp .env.example .env
# 必要に応じて .env を編集
```

3) テスト実行（カバレッジ 80% 以上）

```
pytest -q
```

4) セキュリティスキャン

```
poetry run bandit -r monitor -ll
poetry export -f requirements.txt --without-hashes -o /tmp/req.txt
pip-audit -r /tmp/req.txt
```

5) デモ実行

- 1回だけの実行
```
poetry run monitor --once --log-level DEBUG
```
- デーモン実行
```
poetry run monitor --log-level INFO
```

MONITOR_LANG=ja を設定すると、一部のメッセージが日本語化されます（将来的に拡充予定）。

