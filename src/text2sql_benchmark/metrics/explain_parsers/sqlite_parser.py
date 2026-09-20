from __future__ import annotations

import re

from .base import ExplainParser, ExplainResult


class SQLiteExplainParser(ExplainParser):
    def parse(self, raw: str) -> ExplainResult:
        # EXPLAIN QUERY PLAN retorna linhas como:
        # "(0, 0, 0, 'SCAN orders')" ou "(0, 0, 0, 'SEARCH orders USING INDEX ...')"
        uses_index = bool(re.search(r"USING INDEX|USING COVERING INDEX", raw, re.IGNORECASE))
        scan_type = "IndexScan" if uses_index else "SeqScan"

        return ExplainResult(
            scan_type=scan_type,
            total_cost=-1.0,  # SQLite não expõe custo estimado
            actual_rows=-1,   # SQLite não expõe linhas reais no QUERY PLAN
            uses_index=uses_index,
            raw=raw,
        )
