# OpenSpiel パラメータ修正後の実行手順

## 修正内容

### 問題のあったコード（エラーが出ていた）
```python
pyspiel.GameType(
    ...,
    provides_information_state_as_normalized_vector=True,
    provides_factored_observation_as_normalized_vector=True,
)
```

### 修正後のコード
```python
pyspiel.GameType(
    ...,
    provides_information_state_string=False,
    provides_information_state_tensor=True,
    provides_observation_string=False,
    provides_observation_tensor=True,
)
```

## 修正箇所

- ✅ `fafnir_game.py` 行 487-503 (`FafnirGame.__init__`)
- ✅ `fafnir_game.py` 行 461-477 (`_register_fafnir`)

## 動作確認手順

### ステップ1: 簡単なテスト（推奨）

```bash
python quick_test.py
```

期待される出力：
```
==============================================================
Fafnir Game Initialization Test
==============================================================

1. Importing modules...
   ✓ FafnirGame imported

2. Creating game instance...
   ✓ Game created

3. Creating initial state...
   ✓ Initial state created
   State: Fafnir(round=1, turn=0, phase=0)

4. Testing basic game properties...
   - Is terminal: False
   - Current player: 0
   - Num players: 2
   - Legal actions: 2048

5. Testing game progression...
   Step 1: Action 0, Terminal: False
   Step 2: Action 0, Terminal: False
   Step 3: Action 0, Terminal: False
   Step 4: Action 0, Terminal: False
   Step 5: Action 0, Terminal: False

==============================================================
ALL TESTS PASSED ✓
==============================================================
```

**⚠️ 注意**: Legal actionsが2048個と多いです。これは正常な動作です。

### ステップ2: 完全なテストスイート

```bash
python test_fafnir.py
```

### ステップ3: トレーニング（小規模での不完全性テスト）

```bash
# 10イテレーション（テスト用）
python main.py train --iterations 10 --model-path test_model.pkl
```

期待される出力：
```
[TRAIN] No existing model found, starting fresh training: test_model.pkl
[TRAIN] Initialized empty solver (no model at test_model.pkl)
[TRAIN] Use train() method to start training
[TRAIN] Training 10 iterations...
[TRAIN] Current model state: 0 iterations completed
[MCCFR] Iteration 10/10 - Nodes: XXX - P0 util: 0.XXXX, P1 util: 0.XXXX
[TRAIN] ✓ Training complete!
[TRAIN] Total iterations: 10
[TRAIN] Learned states: XXX
[TRAIN] Model saved to: test_model.pkl
```

### ステップ4: 本格的なトレーニング

成功を確認したら、より大規模なトレーニングを実行：

```bash
python main.py train --iterations 100
```

## パフォーマンス予測

| イテレーション | 予想時間 | メモリ | 説明 |
|-------------|--------|--------|------|
| 10 | < 1分 | < 100MB | テスト用 |
| 100 | 5-10分 | < 200MB | 小規模 |
| 500 | 30-60分 | < 500MB | 中規模 |
| 1000 | 1-2時間 | < 1GB | 標準 |

※ マシンのスペックで大きく変動します

## 問題が発生した場合

### エラー1: "ModuleNotFoundError: No module named 'pyspiel'"

```bash
pip install --upgrade open-spiel
```

### エラー2: "Still getting TypeError"

OpenSpielのバージョンが古い可能性があります：

```bash
pip show open-spiel
# バージョンが 1.2.x などの場合は
pip install --upgrade 'open-spiel>=1.6.11'
```

### エラー3: ゲームが進まない（無限ループ）

ゲーム実装に潜在的なバグがある可能性があります。この場合はお知らせください。

### エラー4: メモリ不足

トレーニングを中断して、変数を削除：

```python
# Python内で
import gc
gc.collect()
```

## トレーニング後の確認

```bash
# 学習済みモデルで検証プレイ
python main.py play --name "Validator" --model-path test_model.pkl
```

## デバッグモード

より詳細なログを出力：

```python
# test_fafnir.py または quick_test.py の先頭に追加
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 次のステップ

1. ✅ quick_test.py で確認
2. ✅ test_fafnir.py で完全テスト
3. ✅ 10イテレーションで動作確認
4. ✅ 100イテレーション でトレーニング
5. ✅ main.py play でゲーム検証
6. ✅ 本格的なトレーニング

---

**修正は完了しました。quick_test.py を実行してください！**
