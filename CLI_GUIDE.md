# Fafnir MCCFR AI - CLI 使用ガイド

## インストール

### 依存関係のインストール

```bash
# 方法1: requirements.txt を使用
pip install -r requirements.txt

# 方法2: pyproject.toml からインストール
pip install -e .

# 方法3: uv を使用（推奨）
uv sync
```

## CLIコマンド

### 1. 検証 (validate)

実装が正しく動作するか確認します。

```bash
python main.py validate
```

**出力例**:
```
FAFNIR MCCFR IMPLEMENTATION VALIDATION
1. Testing imports...
   ✓ pyspiel imported
   ✓ fafnir_game imported
   ✓ mccfr_ai imported
...
ALL VALIDATIONS PASSED ✓
```

### 2. テスト (test)

テストスイートを実行します。

```bash
python main.py test
```

### 3. トレーニング (train)

モデルをトレーニングします。

#### 3.1 新規でトレーニング開始

```bash
python main.py train --iterations 1000
```

パラメータ:
- `--iterations N`: トレーニングイテレーション回数（デフォルト: 1000）
- `--model-path PATH`: モデル保存パス（デフォルト: fafnir_mccfr_model.pkl）

**出力例**:
```
[TRAIN] No existing model found, starting fresh training: fafnir_mccfr_model.pkl
[TRAIN] Initialized empty solver (no model at fafnir_mccfr_model.pkl)
[TRAIN] Use train() method to start training
[TRAIN] Training 1000 iterations...
[TRAIN] Current model state: 0 iterations completed
[MCCFR] Iteration 100/1000 - Nodes: 543 - P0 util: 0.4893, P1 util: 0.5107
[MCCFR] Iteration 200/1000 - Nodes: 1234 - P0 util: 0.5001, P1 util: 0.4999
...
[TRAIN] ✓ Training complete!
[TRAIN] Total iterations: 1000
[TRAIN] Learned states: 5123
[TRAIN] Model saved to: fafnir_mccfr_model.pkl
```

#### 3.2 既存モデルから継続学習

既存モデルから追加で学習します：

```bash
# 500イテレーション追加学習
python main.py train --iterations 500

# または明示的に --continue フラグを使用
python main.py train --iterations 500 --continue
```

**出力例**:
```
[TRAIN] Continuing from existing model: fafnir_mccfr_model.pkl
[TRAIN] Loading existing model from fafnir_mccfr_model.pkl
[TRAIN] Model loaded: 1000 iterations, 5123 states
[TRAIN] Training 500 iterations...
[TRAIN] Current model state: 1000 iterations completed
[MCCFR] Iteration 100/500 - Nodes: 5234 - P0 util: 0.5012, P1 util: 0.4988
...
[TRAIN] ✓ Training complete!
[TRAIN] Total iterations: 1500
[TRAIN] Learned states: 5456
[TRAIN] Model saved to: fafnir_mccfr_model.pkl
```

#### 3.3 リセットして新規トレーニング

既存モデルを削除して、新規に開始します：

```bash
python main.py train --iterations 1000 --reset
```

**出力例**:
```
[TRAIN] Starting fresh training (--reset flag)
[TRAIN] Model path: fafnir_mccfr_model.pkl
[TRAIN] Warning: Existing model at fafnir_mccfr_model.pkl will be overwritten
```

#### 3.4 カスタムモデルパスで学習

別のモデルファイルとして保存します：

```bash
python main.py train --iterations 2000 --model-path my_custom_model.pkl
```

### 4. プレイ (play)

トレーニング済みモデルを使用してゲームサーバーに接続します。

#### 4.1 デフォルト設定でプレイ

```bash
# サーバーは別ターミナルで実行: python server.py
python main.py play
```

#### 4.2 カスタムサーバーに接続

```bash
python main.py play \
  --url http://192.168.1.100:8765 \
  --room my_room \
  --name "Advanced-AI" \
  --model-path trained_models/best_model.pkl
```

パラメータ:
- `--url URL`: ゲームサーバーURL（デフォルト: http://127.0.0.1:8765）
- `--room ROOM_ID`: ゲームルームID（デフォルト: room1）
- `--name NAME`: プレイヤー名（デフォルト: MCCFR-AI）
- `--model-path PATH`: 使用するモデルファイル（デフォルト: fafnir_mccfr_model.pkl）

**出力例**:
```
[PLAY] Starting AI bot: Advanced-AI
[PLAY] Connecting to http://192.168.1.100:8765/my_room
[PLAY] Using model: trained_models/best_model.pkl
[MCCFR-AI] Initializing MCCFR AI engine...
[MCCFR-AI] Loading existing model from trained_models/best_model.pkl
[MCCFR-AI] Model loaded: 5000 iterations, 12543 states
[MCCFR-AI] AI engine ready: 5000 iterations trained
[MCCFR-AI] Learned states: 12543
[MCCFR-AI] Connecting to http://192.168.1.100:8765
[MCCFR-AI] connected to server
```

## トレーニング戦略

### 推奨される学習プロセス

```bash
# ステップ1: 初期トレーニング（1000イテレーション）
python main.py train --iterations 1000

# ステップ2: 追加トレーニング（500イテレーション）
python main.py train --iterations 500

# ステップ3: 追加トレーニング（500イテレーション）
python main.py train --iterations 500

# ステップ4: 最終トレーニング（1000イテレーション）
python main.py train --iterations 1000

# ステップ5: サーバーで検証
python main.py play
```

**合計**: 3000イテレーション

### 複数モデルの比較

異なる設定でモデルをトレーニングし、比較します：

```bash
# モデルA: 1000イテレーション
python main.py train --iterations 1000 --model-path model_a.pkl

# モデルB: 2000イテレーション
python main.py train --iterations 2000 --model-path model_b.pkl

# モデルA と play して検証
python main.py play --model-path model_a.pkl --name "Model-A"

# モデルB と play して検証
python main.py play --model-path model_b.pkl --name "Model-B"
```

## 進捗の監視

トレーニング中の主要な指標：

- **Iterations**: 完了したイテレーション数
- **Nodes**: 発見された情報状態（ゲーム局面）の数
- **P0 util / P1 util**: 各プレイヤーの平均報酬
  - 理想値: 0.5 に近い（Nash平衡）

**学習の収束の样子**:
```
Iteration 100 - Nodes: 500 - P0: 0.4234, P1: 0.5766
Iteration 200 - Nodes: 1100 - P0: 0.4876, P1: 0.5124
Iteration 300 - Nodes: 1650 - P0: 0.4998, P1: 0.5002  ← ほぼ均衡
Iteration 400 - Nodes: 2050 - P0: 0.5012, P1: 0.4988
...
```

## トラブルシューティング

### エラー: ModuleNotFoundError: No module named 'pyspiel'

```bash
pip install open-spiel
```

### エラー: Connection refused when running `play` command

サーバーが起動していることを確認：
```bash
# 別のターミナルで
python server.py
```

### モデルが見つからない

```bash
# 現在のディレクトリを確認
ls *.pkl

# または明示的に絶対パスを指定
python main.py train --iterations 1000 --model-path /path/to/model.pkl
```

### トレーニングが遅い

トレーニングイテレーション数を減らして試す：
```bash
python main.py train --iterations 100
```

推奨値：
- テスト用: 100-500イテレーション
- 実験用: 500-2000イテレーション
- 本番用: 3000-10000イテレーション

## 高度な使用例

### 段階的トレーニング（推奨）

```bash
#!/bin/bash
# train_progressive.sh

echo "Starting progressive training..."

for i in {1..5}; do
  iterations=$((i * 500))
  total=$((i * 500))
  echo "Pass $i: Training $iterations more iterations (Total: $total)"
  python main.py train --iterations $iterations
  
  # 検証ゲームを1回実行
  echo "Validating model..."
  timeout 30 python main.py play --name "Validator-Pass-$i" || true
  
  echo ""
done

echo "Training complete!"
```

実行方法：
```bash
bash train_progressive.sh
```

### バッチ処理

複数の異なる設定でモデルをトレーニング：

```bash
#!/bin/bash
# train_batch.sh

for model_num in {1..3}; do
  model_path="model_v${model_num}.pkl"
  iterations=$((model_num * 1000))
  
  echo "Training model $model_num..."
  python main.py train --iterations $iterations --model-path $model_path --reset
done

echo "All models trained!"
```

## パフォーマンス最適化

### トレーニング時間の短縮

1. イテレーション数を適切に設定
2. マシンのメモリを確認（大規模モデルで重要）

### メモリ使用量の削減

モデルサイズが大きい場合：
```python
# mccfr_ai.py を編集して定期的にNodeをクリーンアップ
# または小分けするモデルを使用
```

## 次のステップ

トレーニングが完了したら：

1. **ゲームサーバーで検証**
   ```bash
   python server.py &
   python main.py play
   ```

2. **複数AEONプレイ**
   - サーバーで複数のボットを同時実行

3. **統計分析**
   - 勝率、ポイント分布などを分析

4. **さらに高度なトレーニング**
   - 最適なハイパーパラメータを探索
   - 異なるゲーム設定でテスト
