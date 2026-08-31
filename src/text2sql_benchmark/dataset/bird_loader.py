from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from .base import BirdInstance, DatasetLoader


class BirdLoader(DatasetLoader):
    def __init__(self) -> None:
        self._instances: list[BirdInstance] = []

    # O BIRD distribui as queries como "mysql"; o projeto usa MariaDB, que le
    # o mesmo arquivo. Sem este mapa a busca por "mariadb.json" nao acha nada e
    # o benchmark roda com zero instancias, em silencio.
    _ARQUIVO_POR_DIALETO = {"mariadb": "mysql"}

    def load(self, path: Path, dialect: str = "sqlite") -> list[BirdInstance]:
        if path.is_dir():
            # carrega <path>/<db_id>/<dialect>.json para cada banco
            raw: list[dict] = []
            arquivo = self._ARQUIVO_POR_DIALETO.get(dialect, dialect)
            for json_file in sorted(path.glob(f"*/{arquivo}.json")):
                raw.extend(json.loads(json_file.read_text(encoding="utf-8")))
        else:
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
