from __future__ import annotations

import json

from .base import ExplainParser, ExplainResult


class MariaDBExplainParser(ExplainParser):
    """Interpreta a saida de `ANALYZE FORMAT=JSON` do MariaDB.

    O MariaDB nao tem `EXPLAIN ANALYZE` (isso e MySQL 8). O `ANALYZE
    FORMAT=JSON` devolve uma arvore com `query_block` -> `nested_loop` ->
    `table`, onde cada tabela traz `access_type`, `cost`, `rows`, `r_rows` e
    `using_index`.
    """

    # access_type -> rotulo comparavel ao dos outros SGBDs
    _ACESSOS = {
        "ALL": "Table scan",
        "index": "Index scan",
        "range": "Index range scan",
        "ref": "Index lookup",
        "eq_ref": "Index lookup",
        "const": "Const",
        "system": "Const",
    }

    def parse(self, raw: str) -> ExplainResult:
        try:
            dados = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return ExplainResult(
                scan_type="Unknown", total_cost=-1.0, actual_rows=0,
                uses_index=False, raw=raw,
            )

        tabelas: list[dict] = []
        self._coletar_tabelas(dados, tabelas)

        if not tabelas:
            bloco = dados.get("query_block", {})
            return ExplainResult(
                scan_type="Unknown",
                total_cost=float(bloco.get("cost", -1.0) or -1.0),
                actual_rows=int(bloco.get("r_rows", 0) or 0),
                uses_index=False,
                raw=raw,
            )

        # A tabela mais cara domina o plano; e ela que caracteriza o acesso.
        principal = max(tabelas, key=lambda t: float(t.get("cost", 0) or 0))
        acesso = principal.get("access_type", "")
        usa_indice = any(
            t.get("using_index") or t.get("key") for t in tabelas
        ) or acesso in {"index", "range", "ref", "eq_ref"}

        return ExplainResult(
            scan_type=self._ACESSOS.get(acesso, acesso or "Unknown"),
            total_cost=float(dados.get("query_block", {}).get("cost", -1.0) or -1.0),
            actual_rows=int(principal.get("r_rows", 0) or 0),
            uses_index=usa_indice,
            raw=raw,
        )

    def _coletar_tabelas(self, no: object, saida: list[dict]) -> None:
        """Percorre a arvore recolhendo todo objeto `table`."""
        if isinstance(no, dict):
            for chave, valor in no.items():
                if chave == "table" and isinstance(valor, dict):
                    saida.append(valor)
                else:
                    self._coletar_tabelas(valor, saida)
        elif isinstance(no, list):
            for item in no:
                self._coletar_tabelas(item, saida)
