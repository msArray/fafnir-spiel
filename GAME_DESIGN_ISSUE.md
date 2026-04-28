"""
エラー対応チュートリアル：OpenSpielゲーム設計

Fafnir実装で発生した主な問題：

1. **legal_actions() が空のリストを返す**
   - 原因: フェーズトランジションのロジックが複雑で、
     プレイヤーのアクションが制限されるケースが生じている

2. **current_player() の実装が不正確**
   - 原因: RESULT フェーズでプレイヤー 0 固定になり、
     プレイヤー 1 がアクションできない

## 解決策

OpenSpielの標準ゲームフローに対応するために、ゲーム設計を簡略化する必要があります。

### 推奨アプローチ1: MCCFRを独立实装（推奨）

OpenSpielの複雑さを避け、独立した MCCFR 実装を使用：

- ゲーム状態を自作クラスで管理
- MCCFR ソルバーに state インターフェースを提供
- OpenSpiel の制約に縛られない

### 推奨アプローチ2: ゲーム設計の大幅な簡略化

OpenSpielの標準フロー（特に `current_player()` と `legal_actions()` の関係）を厳密に守る：

```python
# 各ターンで1人のプレイヤーのみがアクション
def current_player() -> int:
    if is_terminal():
        return TERMINAL
    return current_acting_player  # 常に1人

# legal_actions() は必ず非空を返す
def legal_actions() -> List[int]:
    if is_terminal():
        return []
    return compute_legal_actions(current_player())
```

## 早急な修正案

fafnir_game.py の以下を修正：

1. BIDDING フェーズを同期化（両プレイヤーが順番にアクション）
2. RESULT フェーズをシンプル化（自動遷移）  
3. legal_actions() が常に非空を保証

## 実装方針

current_player() の簡略化：
- BIDDING フェーズ：`self._current_player` (0 または 1)
- RESULT フェーズ：自動遷移
- ROUND_END フェーズ：自動遷移
- GAME_END フェーズ：終了

legal_actions() をシンプル化：
- BIDDING かつ未提出：ビッドアクション生成
- そ以外：空でなく、何らかのアクション  

または：
- フェーズ終了時に自動的に次フェーズへ遷移
- 各フェーズで常に1人のプレイヤーがアクション
"""

# より簡潔な実装例：
# BIDDING フェーズ → GAME_END フェーズへ
# 各ターンで両プレイヤーが交互にビッド
# ビッドが完了したら GAME_END へ自動遷移

print(__doc__)
