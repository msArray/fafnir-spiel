# GameInfo パラメータ追加修正

## エラー

```
TypeError: __init__(): incompatible constructor arguments. 
The following argument types are supported:
    1. pyspiel.Game(arg0: pyspiel.GameType, arg1: pyspiel.GameInfo, arg2: collections.abc.Mapping[str, GameParameter])

Invoked with: <GameType 'fafnir'>
```

## 原因

`pyspiel.Game.__init__()` には3つの必須引数が必要です：
1. `GameType` - ゲーム定義
2. `GameInfo` - ゲーム情報（ユーティリティ範囲、最大ゲーム長など）
3. `GameParameter` - ゲームパラメータ（通常は空の dict）

しかし、修正前はマッピングされていたのは `GameType` だけでした。

## 修正内容

### 修正前（エラーの原因）

```python
def __init__(self, params=None):
    game_type = pyspiel.GameType(...)
    super().__init__(game_type)  # ← GameInfo と params がない
```

### 修正後

```python
def __init__(self, params=None):
    game_type = pyspiel.GameType(...)
    
    game_info = pyspiel.GameInfo(
        min_utility=0.0,
        max_utility=1.0,
        utility_sum=1.0,
        max_game_length=10000,
    )
    
    super().__init__(game_type, game_info, params or {})
```

## 修正のポイント

### 1. GameInfo の作成

```python
game_info = pyspiel.GameInfo(
    min_utility=0.0,      # ゲームの最小報酬
    max_utility=1.0,      # ゲームの最大報酬
    utility_sum=1.0,      # ゼロサムゲーム
    max_game_length=10000,  # 最大ゲーム長
)
```

### 2. GameParameter の作成

```python
params or {}  # params がない場合は空の dict
```

## 修正ファイル

- ✅ `fafnir_game.py` (行 483-507)

## 検証方法

```bash
python quick_test.py
```

期待される出力：

```
============================================================
Fafnir Game Initialization Test
============================================================

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
   ...

============================================================
ALL TESTS PASSED ✓
============================================================
```

## OpenSpiel Game クラスの初期化要件

OpenSpielの `Game` クラスを正しく継承するために、以下が必須です：

```python
class CustomGame(pyspiel.Game):
    def __init__(self, params=None):
        # 1. GameType を作成
        game_type = pyspiel.GameType(...)
        
        # 2. GameInfo を作成
        game_info = pyspiel.GameInfo(
            min_utility=...,
            max_utility=...,
            utility_sum=...,
            max_game_length=...
        )
        
        # 3. 親クラスを初期化（3つの引数すべてが必須）
        super().__init__(game_type, game_info, params or {})
```

## GameInfo パラメータの詳細

| パラメータ | 型 | 説明 | 例 |
|-----------|-----|------|-----|
| `min_utility` | float | ゲーム内で獲得可能な最小報酬 | 0.0 |
| `max_utility` | float | ゲーム内で獲得可能な最大報酬 | 1.0 |
| `utility_sum` | float | プレイヤー全体の報酬の合計（ゼロサムなら0、ただしOpenSpielは通常1.0を使用） | 1.0 |
| `max_game_length` | int | ゲームが終了するまでの最大ステップ数 | 10000 |

## 関連する実装

### 同様に修正が必要だった部分

実装全体で以下のメソッドで各パラメータが返されています：

```python
def min_utility(self) -> float:
    return 0.0

def max_utility(self) -> float:
    return 1.0

def utility_sum(self) -> float:
    return 1.0

def max_game_length(self) -> int:
    return 10000
```

これらは `GameInfo` のデータと一致すべきです（この実装では一致しています）。

## 次のステップ

修正後は以下を実行してください：

```bash
# クイックテスト
python quick_test.py

# 完全なテスト
python test_fafnir.py

# トレーニング
python main.py train --iterations 10
