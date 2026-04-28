# Requirements.txt 説明

## 現在の requirements.txt

```txt
# Core dependencies
open-spiel>=1.6.11
numpy>=1.21.0

# Server and networking
fastapi>=0.100.0
python-socketio[asyncio_client]>=5.9.0
uvicorn>=0.23.0
aiohttp>=3.8.0

# Development
pytest>=7.0.0
```

## 元のrequirements.txt（提供いただいたもの）

```txt
fastapi
python-socketio
aiohttp
uvicorn
python-socketio[asyncio_client]
```

## 重要な変更と理由

### ✅ 追加されたパッケージ

#### 1. **open-spiel>=1.6.11** - ⚠️ 必須！
- **理由**: OpenSpielゲーム定義の基本
- **用途**: `fafnir_game.py` で使用
- **元のrequirements.txtにはなかった** - これが問題でした
- **復活エラーの原因**: 依存関係が不足していた

#### 2. **numpy>=1.21.0** - 必須
- **理由**: 行列演算、配列操作
- **用途**: MCCFR計算、確率計算
- **元のrequirements.txtにはなかった**

#### 3. **pytest>=7.0.0** - 開発用
- **理由**: テスト実行用
- **用途**: `test_fafnir.py` で使用
- **オプション**: 開発時のみ必須

### 📌 保持されたパッケージ

#### **fastapi>=0.100.0**
- サーバーの HTTP フレームワーク
- `server.py` で使用

#### **python-socketio[asyncio_client]>=5.9.0**
- リアルタイム通信プロトコル
- `ai_bot_mccfr.py` で使用
- `[asyncio_client]` は非同期クライアント機能

#### **uvicorn>=0.23.0**
- ASGI サーバーコンテナ
- FastAPI アプリケーション実行用

#### **aiohttp>=3.8.0**
- 非同期 HTTP クライアント/サーバー
- ネットワーク通信で使用

### 🔄 改善点

1. **バージョン指定の追加** - より安定性が向上
   - 例: `fastapi>=0.100.0`
   - 下位互換性がない可能性のあるパッケージはバージョンを固定

2. **重複排除**
   - `python-socketio` と `python-socketio[asyncio_client]` が両方あった
   - → `python-socketio[asyncio_client]` に統一

3. **コメント追加** - 可読性向上
   - カテゴリ分類（Core, Server, Development）

## インストール方法の比較

### 方法1: requirements.txt（推奨）
```bash
pip install -r requirements.txt
```

### 方法2: pyproject.toml
```bash
pip install -e .
```

### 方法3: uv（最速）
```bash
uv sync
uv pip install -r requirements.txt
```

## 動作確認

すべてのパッケージが正しくインストールされていることを確認：

```bash
# インストール
pip install -r requirements.txt

# 検証スクリプトで確認
python validate.py

# テストで確認
python test_fafnir.py

# メインコマンドで確認
python main.py validate
```

## 元の requirements.txt が不完全だった理由

```txt
fastapi                          # ✓ 含まれていた
python-socketio                  # ✓ 含まれていた
aiohttp                          # ✓ 含まれていた
uvicorn                          # ✓ 含まれていた
python-socketio[asyncio_client]  # ✓ 含まれていた

❌ open-spiel がない！   ← サーバー実行には問題ないが
❌ numpy がない！        ← AIボット実行に必須
```

### なぜこれが起こったのか？

元の requirements.txt は **サーバー関連のパッケージのみ** を想定していました：
- `server.py` 実行用
- `python-socketio` は低レベル通信のため

しかし、新しい実装では：
- `fafnir_game.py` - OpenSpiel必須
- `mccfr_ai.py` - numpy必須  
- `ai_bot_mccfr.py` - OpenSpiel, numpy直接依存

## 推奨: 更新されたrequirements.txtを使用

ご提供いただいた requirements.txt から以下を追加してください：

```txt
open-spiel>=1.6.11
numpy>=1.21.0
pytest>=7.0.0  # テスト用
```

または、プロジェクト ディレクトリの新しい requirements.txt をそのまま使用してください。

## トラブルシューティング

### インストール失敗: "No module named 'pyspiel'"

```bash
# 確認
pip show open-spiel

# 再インストール
pip install --upgrade open-spiel
```

### インストール失敗: "No module named 'numpy'"

```bash
pip install --upgrade numpy
```

### 古いバージョンがインストールされている場合

```bash
# 強制アップデート
pip install --upgrade -r requirements.txt
```

### 完全な再インストール（推奨）

```bash
# 仮想環境をリセット
python -m venv venv_new
source venv_new/bin/activate  # Windows: venv_new\Scripts\activate

# 新規インストール
pip install -r requirements.txt

# 検証
python main.py validate
```

## まとめ

| 項目 | 元のrequirements.txt | 新しいrequirements.txt |
|------|-------------------|-------------------|
| open-spiel | ❌ | ✅ |
| numpy | ❌ | ✅ |
| fastapi | ✅ | ✅ |
| python-socketio | ✅ | ✅ |
| aiohttp | ✅ | ✅ |
| uvicorn | ✅ | ✅ |
| pytest | ❌ | ✅ |
| **結論** | **不完全** | **完全** |

新しい requirements.txt を使用してください！
