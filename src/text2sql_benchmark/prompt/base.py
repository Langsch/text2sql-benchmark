from __future__ import annotations

from abc import ABC, abstractmethod

from ..dataset.base import BirdInstance


class PromptBuilder(ABC):
    @abstractmethod
    def build(
        self,
        instance: BirdInstance,
        schema: str,
        dialect: str,
        use_evidence: bool = True,
    ) -> str: ...
