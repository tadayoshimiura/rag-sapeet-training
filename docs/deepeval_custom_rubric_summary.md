# DeepEval 自作ルーブリック（要約版）

## 結論
DeepEvalの自作ルーブリックは、**G‑Evalで使う「点数レンジ（0〜10）＋期待される判定文」**を並べた採点表。  
これを渡すことで、採点LLMのスコアを指定レンジ内に**誘導・制限**できる。

---

## 自作ルーブリックとは
- **Rubric** の組み合わせ（採点基準表）
  - `score_range=(開始, 終了)`  
  - `expected_outcome="このレンジのときの説明"`
- ルール:
  - 0〜10（両端含む）
  - レンジ同士の重複は禁止
- DeepEvalは最終的に **0〜1スコア**に正規化し、`threshold` 以上でPass判定

---

## 公式の形（最小例）
```python
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCaseParams
from deepeval.metrics.g_eval import Rubric

correctness_metric = GEval(
    name="Correctness",
    criteria="Determine whether the actual output is factually correct based on the expected output.",
    evaluation_params=[
        LLMTestCaseParams.ACTUAL_OUTPUT,
        LLMTestCaseParams.EXPECTED_OUTPUT
    ],
    rubric=[
        Rubric(score_range=(0,2), expected_outcome="Factually incorrect."),
        Rubric(score_range=(3,6), expected_outcome="Mostly correct."),
        Rubric(score_range=(7,9), expected_outcome="Correct but missing minor details."),
        Rubric(score_range=(10,10), expected_outcome="100% correct."),
    ]
)
```

**点数表の意味づけ**
- 0〜2: 事実として誤り
- 3〜6: だいたい正しい
- 7〜9: 正しいが細部が欠ける
- 10: 完全に正しい

---

## 使い分けの実務ポイント
- **rubric を使う**: 点数レンジを固定し、スコアのブレを抑える  
- **evaluation_steps を明示**: 採点手順を固定し、さらに安定化  
- **完全に決定的にしたい**: G‑Evalは非決定的なため、DAGMetric等も検討

---

## 重要ポイント
- 自作ルーブリックは **「0〜10の点数レンジ＋期待結果文」** を並べた採点表  
- DeepEvalの最終判定は **0〜1スコア＋threshold** で行う
