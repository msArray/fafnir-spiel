# super().__init__() 呼び出し修正

## エラー

```
TypeError: pyspiel.Game.__init__() must be called when overriding __init__
```

## 原因

`FafnirGame` クラスで `pyspiel.Game` の初期化メソッドを呼び出していませんでした。

## 修正内容

### 修正前（エラーの原因）

```python
class FafnirGame(pyspiel.Game):
    def __init__(self, params=None):
        self.game_type = pyspiel.GameType(...)  # ← super().__init__() がない！
```

### 修正後

```python
class FafnirGame(pyspiel.Game):
    def __init__(self, params=None):
        game_type = pyspiel.GameType(...)
        super().__init__(game_type)  # ← 追加されました
```

## 修正ポイント

1. **変数の変更**: `self.game_type` → `game_type`
   - 親クラスのコンストラクタに直接渡すため、ローカル変数に変更

2. **super().__init__() の呼び出し追加**: 
   - `super().__init__(game_type)` を明示的に呼び出す
   - これにより `pyspiel.Game` の初期化が実行される

## 修正ファイル

- ✅ `fafnir_game.py` (行 483-502)

## 検証方法

```bash
# クイックテスト
python quick_test.py

# または
python -c "from fafnir_game import FafnirGame; game = FafnirGame(); print('OK')"
```

期待される出力：
```
OK
```

## OpenSpielの親クラス初期化要件

OpenSpielの `Game` クラスを継承する場合、以下が必須です：

```python
class CustomGame(pyspiel.Game):
    def __init__(self, params=None):
        # 1. GameType を作成
        game_type = pyspiel.GameType(...)
        
        # 2. 親クラスを初期化
        super().__init__(game_type)  # ← 必須
        
        # 3. その他の初期化
        ...
```

## 関連する実装

`FafnirGameState` はすでに正しく実装されています：

```python
class FafnirGameState(pyspiel.State):
    def __init__(self, game):
        super().__init__(game)  # ✓ 正しく呼ばれている
        ...
```

## 次のステップ

修正後は以下のコマンドを実行してください：

```bash
python quick_test.py
```
