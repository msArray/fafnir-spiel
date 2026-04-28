# OpenSpiel パラメータ修正ガイド

## 問題
以下のエラーが発生していました：

```
TypeError: __init__(): incompatible constructor arguments. 
The following argument types are supported:
    1. pyspiel.GameType(short_name: str, ..., provides_information_state_string: bool, 
       provides_information_state_tensor: bool, provides_observation_string: bool, 
       provides_observation_tensor: bool, ...)
```

## 原因
OpenSpielのバージョンによって、`GameType` コンストラクタのパラメータ名が異なります。

### 古いパラメータ名（エラー）
```python
provides_information_state_as_normalized_vector=True
provides_factored_observation_as_normalized_vector=True
```

### 新しいパラメータ名（修正済み）
```python
provides_information_state_string=False
provides_information_state_tensor=True
provides_observation_string=False
provides_observation_tensor=True
```

## 修正適用ファイル
- ✅ `fafnir_game.py` - 2箇所修正
  - `_register_fafnir()` 関数
  - `FafnirGame.__init__()` メソッド

## 修正確認

### 方法1: クイックテスト
```bash
python quick_test.py
```

期待される出力：
```
Fafnir Game Initialization Test
============================================================

1. Importing modules...
   ✓ FafnirGame imported

2. Creating game instance...
   ✓ Game created

3. Creating initial state...
   ✓ Initial state created
   State: Fafnir(round=1, turn=0, phase=0)

...

ALL TESTS PASSED ✓
```

### 方法2: トレーニング実行
```bash
python main.py train --iterations 100
```

より詳細な進捗が表示されます。

## 新しいOpenSpiel互換性

修正後は以下のバージョンに対応します：
- open-spiel >= 1.6.11 （推奨）
- 最新の open-spiel

## 参考: GameType パラメータ一覧

| パラメータ | 型 | 説明 |
|-----------|-----|------|
| short_name | str | ゲームの短い名前 |
| long_name | str | ゲームの長い名前 |
| dynamics | Dynamics | 逐次ゲーム |
| chance_mode | ChanceMode | チャンスなし |
| information | Information | 完全情報 |
| utility | Utility | ゼロサム |
| reward_model | RewardModel | ターミナルでのみ報酬 |
| max_num_players | int | 最大プレイヤー数 |
| min_num_players | int | 最小プレイヤー数 |
| **provides_information_state_string** | bool | 情報状態を文字列で提供 |
| **provides_information_state_tensor** | bool | 情報状態をテンソルで提供 |
| **provides_observation_string** | bool | 観測を文字列で提供 |
| **provides_observation_tensor** | bool | 観測をテンソルで提供 |

## トラブルシューティング

### まだエラーが出る場合

1. OpenSpielバージョン確認
```bash
pip show open-spiel
```

2. 最新バージョンにアップデート
```bash
pip install --upgrade open-spiel
```

3. 仮想環境をリセット（推奨）
```bash
deactivate
rm -rf venv
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 別のエラーが発生した場合

エラーメッセージをコピーして、以下の手順で対応してください：
1. エラー行番号を確認
2. ファイルの該当箇所をチェック
3. OpenSpielの最新ドキュメントを参照
