from __future__ import annotations

import re

from .base import ExplainParser, ExplainResult


class MariaDBExplainParser(ExplainParser):
    def parse(self, raw: str) -> ExplainResult:
        # EXPLAIN ANALYZE do MariaDB retorna texto com linhas tipo:
        # "-> Table scan on orders  (cost=85.75 rows=850) (actual rows=850 ...)"
        scan_match = re.search(r"(Table scan|Index scan|Index lookup|Full-index scan)", raw, re.IGNORECASE)
        cost_match = re.search(r"cost=([\d.]+)", raw)
        rows_match = re.search(r"actual rows=(\d+)", raw)

        scan_type = scan_match.group(1) if scan_match else "Unknown"
        total_cost = float(cost_match.group(1)) if cost_match else -1.0
        actual_rows = int(rows_match.group(1)) if rows_match else 0
        uses_index = "index" in scan_type.lower()

        return ExplainResult(
            scan_type=scan_type,
            total_cost=total_cost,
            actual_rows=actual_rows,
            uses_index=uses_index,
            raw=raw,
        )
