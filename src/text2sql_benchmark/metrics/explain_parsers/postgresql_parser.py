from __future__ import annotations

import re

from .base import ExplainParser, ExplainResult


class PostgreSQLExplainParser(ExplainParser):
    def parse(self, raw: str) -> ExplainResult:
        # Ex: "Seq Scan on orders  (cost=0.00..18.50 rows=850 width=16) (actual rows=850 ...)"
        scan_match = re.search(r"(Seq Scan|Index Scan|Index Only Scan|Bitmap Heap Scan)", raw)
        cost_match = re.search(r"cost=[\d.]+\.\.([\d.]+)", raw)
        rows_match = re.search(r"actual time=[\d.]+\.\.[\d.]+ rows=(\d+)", raw)

        scan_type = scan_match.group(1) if scan_match else "Unknown"
        total_cost = float(cost_match.group(1)) if cost_match else -1.0
        actual_rows = int(rows_match.group(1)) if rows_match else 0
        uses_index = "Index" in scan_type

        return ExplainResult(
            scan_type=scan_type,
            total_cost=total_cost,
            actual_rows=actual_rows,
            uses_index=uses_index,
            raw=raw,
        )
