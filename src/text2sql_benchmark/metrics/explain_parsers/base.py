from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ExplainResult:
    scan_type: str        # "SeqScan" | "IndexScan" | "FullScan" | etc.
    total_cost: float     # custo estimado (N/A para SQLite → -1.0)
    actual_rows: int      # linhas reais retornadas
    uses_index: bool
    raw: str              # saída original do EXPLAIN


class ExplainParser(ABC):
    @abstractmethod
    def parse(self, raw: str) -> ExplainResult: ...
