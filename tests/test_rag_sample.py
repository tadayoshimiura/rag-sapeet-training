import pytest
import os
from deepeval import assert_test
from deepeval.test_case import LLMTestCase
from deepeval.metrics import AnswerRelevancyMetric
from dotenv import load_dotenv, find_dotenv

# .env ファイルをプロジェクトルートから探して読み込む
load_dotenv(find_dotenv(usecwd=True))

def test_answer_relevancy():
    """
    RAGの回答関連性（Answer Relevancy）を評価するサンプルテスト
    """
    
    # 1. 評価データ（本来はRAGシステムから生成された値を使用）
    input_text = "DeepEvalとは何ですか？"
    actual_output = "DeepEvalは、LLMアプリケーションの評価を簡単に行うためのオープンソースフレームワークです。"
    retrieval_context = ["DeepEvalはPythonで書かれたLLM評価ツールです。"]

    # 2. テストケースの作成
    test_case = LLMTestCase(
        input=input_text,
        actual_output=actual_output,
        retrieval_context=retrieval_context
    )

    # 3. 評価指標の設定（閾値を0.5に設定）
    metric = AnswerRelevancyMetric(threshold=0.5)

    # 4. テスト実行（失敗するとAssertionErrorが発生）
    assert_test(test_case, [metric])

if __name__ == "__main__":
    # 直接実行された場合もpytest経由で実行
    pytest.main([__file__, "-s"])