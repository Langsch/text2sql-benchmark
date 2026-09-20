from __future__ import annotations

from ..dataset.base import BirdInstance
from .base import PromptBuilder

_INSTRUCTION = (
    "Write only the SQL query. No explanations, no markdown code blocks. "
    "Start directly with SELECT, INSERT, UPDATE, or DELETE."
)


class BirdPromptBuilder(PromptBuilder):
    def build(
        self,
        instance: BirdInstance,
        schema: str,
        dialect: str,
        use_evidence: bool = True,
    ) -> str:
        parts: list[str] = []

        parts.append(schema)

        comment = f"-- Question: {instance.question}"
        if use_evidence and instance.evidence:
            comment += f"\n-- External Knowledge: {instance.evidence}"
        parts.append(comment)

        parts.append(f"Generate the {dialect} SQL for the above question after thinking step by step:")

        parts.append(_INSTRUCTION)

        return "\n\n".join(parts)
