"""O ANALYZE precisa cair para `ANALYZE TABLE` quando a forma nua falha.

Regressao de um defeito real: o MariaDB rejeita `ANALYZE` sem argumento com
erro 1064, e a excecao era engolida sem que estatistica alguma fosse
recalculada nas cinco celulas daquele SGBD.
"""
from pathlib import Path

from text2sql_benchmark.db.isolation import IsolamentoPorTransacao


class ConectorFalso:
    """Aceita CREATE INDEX e recusa `ANALYZE` nu, como o MariaDB."""

    def __init__(self, aceita_analyze_nu: bool) -> None:
        self.aceita_analyze_nu = aceita_analyze_nu
        self.executados: list[str] = []

    def execute(self, sql: str, db_id: str = "", **_):
        self.executados.append(sql)
        if sql.startswith("SELECT table_name"):
            return [("minha_tabela",)]
        if sql == "ANALYZE" and not self.aceita_analyze_nu:
            raise RuntimeError("1064: You have an error in your SQL syntax")
        return []


def _preparar(conector, tmp_path):
    estrategia = IsolamentoPorTransacao(conector, tmp_path / "registro.json")
    estrategia.preparar("meu_banco", ["CREATE INDEX idx_a ON minha_tabela(col);"])
    return conector.executados


def test_sqlite_e_postgres_usam_analyze_nu(tmp_path: Path) -> None:
    executados = _preparar(ConectorFalso(aceita_analyze_nu=True), tmp_path)
    assert "ANALYZE" in executados
    assert not any(s.startswith("ANALYZE TABLE") for s in executados)


def test_mariadb_cai_para_analyze_table(tmp_path: Path) -> None:
    executados = _preparar(ConectorFalso(aceita_analyze_nu=False), tmp_path)
    assert "ANALYZE TABLE `minha_tabela`" in executados, (
        "sem o fallback, nenhuma estatistica e recalculada no MariaDB"
    )
