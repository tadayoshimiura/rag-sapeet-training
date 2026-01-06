"""RAG基盤のプロンプト処理。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

try:  # pragma: no cover - fallback for older langchain
    from langchain_core.prompts import PromptTemplate
except ImportError:  # pragma: no cover
    from langchain.prompts import PromptTemplate

from ..config import PromptConfig, PromptProfile
from ..providers.bedrock import BedrockLLM

SYSTEM_PROMPT = (
    "あなたはRAG回答エージェントです。\n"
    "必ずCONTEXTに書かれている情報だけで回答してください。推測は禁止です。\n"
    "CONTEXTに根拠がない場合は『不明』と答えてください。"
)

USER_PROMPT_TEMPLATE = (
    "# CONTEXT\n"
    "{context}\n\n"
    "# QUESTION\n"
    "{question}\n\n"
    "CONTEXTだけを根拠に答えてください。\n"
    "根拠は source を付けて箇条書きで示してください。"
)


@dataclass
class PromptSettings:
    """
    System/Userプロンプト文字列を保持し、LangChainテンプレートを構築する。
    """

    system: str = SYSTEM_PROMPT
    user: str = USER_PROMPT_TEMPLATE
    profile_name: Optional[str] = None

    @classmethod
    def from_config(
        cls,
        config: PromptConfig | None,
        system_override: str | None = None,
        profile_name: str | None = None,
    ) -> "PromptSettings":
        """
        Configの上書きを反映したPromptSettingsを生成する。

        Args:
            config (PromptConfig | None): JSONから読み込んだ設定。Noneならデフォルトを使う。
            system_override (str | None): プロファイル選択などで上書きするSystem Prompt。
            profile_name (str | None): 選択済みプロファイル名。Noneの場合は未指定。

        Returns:
            PromptSettings: System/User文字列を格納した設定オブジェクト。

        Example:
            >>> cfg = PromptConfig(system="SYS", user="USER")
            >>> PromptSettings.from_config(cfg)  # doctest: +SKIP
        """
        variables = dict(config.variables) if config else {}
        base_system = system_override or (config.system.strip() if config and config.system else SYSTEM_PROMPT)
        base_user = (config.user.strip() if config and config.user else USER_PROMPT_TEMPLATE)
        system = _apply_variables(base_system, variables)
        user = _apply_variables(base_user, variables)
        return cls(system=system, user=user, profile_name=profile_name)

    def build_template(self, include_history: bool) -> PromptTemplate:
        """
        LangChainのPromptTemplateを作成する。必要に応じて履歴プレースホルダを含める。

        Args:
            include_history (bool): TrueならHISTORYブロックをテンプレートへ追加。

        Returns:
            PromptTemplate: LangChain互換のテンプレート。

        Example:
            >>> PromptSettings().build_template(include_history=False)  # doctest: +SKIP
        """
        history_block = "\n\n# HISTORY\n{history}" if include_history else ""
        template = f"{self.system}{history_block}\n\n{self.user}"
        variables = ["context", "question"]
        if include_history:
            variables.append("history")
        return PromptTemplate(
            input_variables=variables,
            template=template,
        )


class PromptProfileSelector:
    """
    ユーザー質問に応じて最適なSystem PromptをLLMに選ばせる。
    """

    SYSTEM_PROMPT = (
        "You are an assistant that selects the best system prompt for a question.\n"
        "Return only one profile name from the list."
    )

    def __init__(self, llm: BedrockLLM) -> None:
        """
        プロンプト選択器を初期化する。

        Args:
            llm (BedrockLLM): System Prompt判定に利用するBedrock LLM。

        Example:
            >>> selector = PromptProfileSelector(llm)  # doctest: +SKIP
        """
        self._llm = llm

    def select(self, question: str, profiles: Iterable[PromptProfile], variables: Dict[str, str]) -> Optional[PromptProfile]:
        """
        質問と候補プロファイルを元に最適なSystem Promptを選ぶ。

        Args:
            question (str): ユーザー質問。
            profiles (Iterable[PromptProfile]): 候補プロファイル一覧。
            variables (Dict[str, str]): System Promptへ埋め込む変数。

        Returns:
            Optional[PromptProfile]: 選ばれたプロファイル。無ければNone。

        Example:
            >>> selector.select("質問", [PromptProfile(...)], {})  # doctest: +SKIP
        """
        profile_list: List[PromptProfile] = list(profiles)
        if not profile_list:
            return None
        request = self._build_prompt(question, profile_list)
        response = self._llm.generate(system_prompt=self.SYSTEM_PROMPT, user_prompt=request)
        name = response.text.strip().splitlines()[0]
        for profile in profile_list:
            if profile.name.lower() == name.lower():
                return PromptProfile(
                    name=profile.name,
                    description=profile.description,
                    system=_apply_variables(profile.system, variables),
                )
        first = profile_list[0]
        return PromptProfile(
            name=first.name,
            description=first.description,
            system=_apply_variables(first.system, variables),
        )

    def _build_prompt(self, question: str, profiles: List[PromptProfile]) -> str:
        """
        プロファイル選択用のLLMプロンプトを構築する。

        Args:
            question (str): ユーザー質問。
            profiles (List[PromptProfile]): 候補プロファイル。

        Returns:
            str: Bedrockに送るプロンプト文字列。

        Example:
            >>> selector._build_prompt("Q", [])  # doctest: +SKIP
        """
        lines = [f"QUESTION:\n{question.strip()}\n", "AVAILABLE PROFILES:"]
        for profile in profiles:
            lines.append(f"- {profile.name}: {profile.description}")
        lines.append("\nRespond with exactly one profile name from the list.")
        return "\n".join(lines)


class _PartialFormatter(dict):
    """Missingキーを波括弧付きでそのまま返すFormatter。"""

    def __missing__(self, key):  # pragma: no cover - simple passthrough
        """
        format_map内で未定義キーに遭遇した際の挙動を定義する。

        Args:
            key (str): 見つからなかったキー名。

        Returns:
            str: "{key}" 形式で未展開のまま残す文字列。

        Example:
            >>> formatter = _PartialFormatter()
            >>> formatter["missing"]  # doctest: +SKIP
        """
        return "{" + key + "}"


def _apply_variables(template: str, variables: Dict[str, str]) -> str:
    """
    フォーマット変数をテンプレートへ適用する。missingキーはそのまま残す。

    Args:
        template (str): 置換対象テンプレート。
        variables (Dict[str, str]): 埋め込み用のキーと値。

    Returns:
        str: 置換結果。

    Example:
        >>> _apply_variables("Hello {name}", {"name": "RAG"})  # doctest: +SKIP
    """
    formatter = _PartialFormatter(**variables)
    return template.format_map(formatter)
