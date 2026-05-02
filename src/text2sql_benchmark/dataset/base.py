from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass
class BirdInstance:
    instance_id: int
    db_id: str
    question: str
    evidence: str
    sql_gold: str
    difficulty: str  # "simple" | "moderate" | "challenging"


class DatasetLoader(ABC):
    @abstractmethod
    def load(self, path: Path) -> list[BirdInstance]: ...

    @abstractmethod
    def iter_instances(
        self,
        difficulty: str | None = None,
        limit: int | None = None,
        db_id: str | None = None,
    ) -> Iterator[BirdInstance]: ...
