from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from .base import BirdInstance, DatasetLoader


class BirdLoader(DatasetLoader):
    def __init__(self) -> None:
        self._instances: list[BirdInstance] = []

    def load(self, path: Path) -> list[BirdInstance]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        self._instances = [
            BirdInstance(
                instance_id=i,
                db_id=entry["db_id"],
                question=entry["question"],
                evidence=entry.get("evidence", ""),
                sql_gold=entry["SQL"],
                difficulty=entry.get("difficulty", "moderate"),
            )
            for i, entry in enumerate(raw)
        ]
        return self._instances

    def iter_instances(
        self,
        difficulty: str | None = None,
        limit: int | None = None,
        db_id: str | None = None,
    ) -> Iterator[BirdInstance]:
        instances = self._instances
        if difficulty:
            instances = [i for i in instances if i.difficulty == difficulty]
        if db_id:
            instances = [i for i in instances if i.db_id == db_id]
        if limit:
            instances = instances[:limit]
        yield from instances
