# GameInfo コンストラクタ引数修正

## エラー

```
TypeError: __init__(): incompatible constructor arguments. The following argument types are supported:
    1. pyspiel.GameInfo(num_distinct_actions: int, max_chance_outcomes: int, num_players: int, 
       min_utility: float, max_utility: float, utility_sum: float | None = None, max_game_length: int)

Invoked with: kwargs: min_utility=0.0, max_utility=1.0, utility_sum=1.0, max_game_length=10000
```

## 原因

`pyspiel.GameInfo` のコンストラクタには必須の位置引数があります：
1. `num_distinct_actions` - ゲーム内の個別アクション数
2. `max_chance_outcomes` - 最大チャンス結果数
3. `num_players` - プレイヤー数
4. その後、オプション引数を指定

キーワード引数だけでは不足していました。

## 修正内容

### 修正前（エラーの原因）

```python
game_info = pyspiel.GameInfo(
    min_utility=0.0,
    max_utility=1.0,
    utility_sum=1.0,
    max_game_length=10000,
)
```

### 修正後

```python
game_info = pyspiel.GameInfo(
    num_distinct_actions=2049,      # 手札11個: 2^11 + 1 (proceed)
    max_chance_outcomes=0,          # 決定的ゲーム
    num_players=2,                  # 2プレイヤー
    min_utility=0.0,
    max_utility=1.0,
    utility_sum=1.0,
    max_game_length=10000,
)
```

## GameInfo パラメータの詳細

### Fafnir固有の値

| パラメータ | 値 | 説明 |
|-----------|-----|------|
| `num_distinct_actions` | 2049 | 最大手札サイズが11個の場合、2^11 = 2048個の部分集合 + 1（次のプレイヤーへ）= 2049 |
| `max_chance_outcomes` | 0 | 決定的ゲーム（チャンスなし） |
| `num_players` | 2 | 2人プレイヤーゲーム |
| `min_utility` | 0.0 | 最小報酬（ゲームの敗者） |
| `max_utility` | 1.0 | 最大報酬（ゲームの勝者） |
| `utility_sum` | 1.0 | ゼロサムゲーム（合計が1.0） |
| `max_game_length` | 10000 | 最大ゲーム長（ステップ数） |

## なぜ2049なのか

Fafnirの手札管理：
- カスケーダーでない場合: 10個の石
- カスケーダーの場合: 11個の石

手札からのアクション：
- 手札の任意の部分集合を選択 → 2^11 = 2048通り
- または次のプレイヤーに進む → 1通り
- **合計**: 2048 + 1 = 2049

## 修正ファイル

- ✅ `fafnir_game.py` (行 503-513)

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
   Step 2: Action 0, Terminal: False
   Step 3: Action 0, Terminal: False
   Step 4: Action 0, Terminal: False
   Step 5: Action 0, Terminal: False

============================================================
ALL TESTS PASSED ✓
============================================================
```

## OpenSpiel GameInfo 初期化の正しい方法

OpenSpielの `Game` クラスを継承する場合、`GameInfo` は以下の署名が必須です：

```python
game_info = pyspiel.GameInfo(
    num_distinct_actions=N,      # 正の整数（必須）
    max_chance_outcomes=M,       # 非負の整数（必須）
    num_players=P,               # 正の整数（必須）
    min_utility=float,           # 浮動小数点数（必須）
    max_utility=float,           # 浮動小数点数（必須）
    utility_sum=float | None,    # オプション
    max_game_length=int,         # 正の整数（必須）
)
```

## 注意点

### num_distinct_actions の計算

ゲームによって異なります：

- **碁**: 361（19×19ボード）
- **チェス**: 複雑（駒の位置と手で決定）
- **Fafnir**: 2049（前述の通り）

`num_distinct_actions` は「ゲーム全体で可能なすべての異なるアクション」の数です。ゲームの各状態で使用可能なアクションが異なる場合でも、ここは「最大値」や「上限」を指定します。

## 次のステップ

修正後は以下を実行してください：

```bash
# クイックテスト
python quick_test.py

# 成功したら本テスト
python test_fafnir.py

# トレーニング実行
python main.py train --iterations 10
```
