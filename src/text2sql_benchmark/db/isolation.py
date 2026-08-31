"""Estrategias de isolamento para medir o efeito de indices.

Para comparar a performance antes e depois dos indices e preciso executar as
mesmas queries em dois estados do banco. Como obter o estado "com indices"
depende do SGBD:

- SQLite e um arquivo: copiar e indexar a copia e barato e isola perfeitamente.
- PostgreSQL e MariaDB sao servidores: nao ha arquivo para copiar. Clonar o
  database inteiro custaria caro (os bancos do BIRD somam ~1 GB), entao os
  indices sao criados no proprio banco e removidos ao final.

A segunda abordagem tem uma vantagem metodologica: mede no banco real, com as
estatisticas reais do otimizador. E tem um risco — se o processo morrer no
meio, os indices ficam no banco. Por isso os nomes criados sao registrados em
disco, permitindo limpeza posterior.
"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from .base import DBConnector

# Extrai o nome do indice de um CREATE INDEX, para poder derruba-lo depois.
_NOME_INDICE = re.compile(
    r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"']?(\w+)",
    re.IGNORECASE,
)


@dataclass
class AplicacaoIndice:
    """Resultado de aplicar um unico CREATE INDEX."""

    statement: str
    success: bool
    error: str | None = None


class EstrategiaIsolamento(ABC):
    """Prepara um banco indexado e devolve um conector para medi-lo."""

    @abstractmethod
    def preparar(
        self, db_id: str, statements: list[str]
    ) -> tuple[DBConnector, list[AplicacaoIndice]]:
        """Aplica os indices e devolve (conector_indexado, resultados)."""
        ...

    @abstractmethod
    def limpar(self, db_id: str) -> None:
        """Desfaz o estado indexado."""
        ...


class IsolamentoPorCopia(EstrategiaIsolamento):
    """SQLite: copia o arquivo e indexa a copia. O original nao e tocado."""

    def __init__(self, db_dir: Path, tmp_dir: Path) -> None:
        self._db_dir = Path(db_dir)
        self._tmp_dir = Path(tmp_dir)
        self._copia: Path | None = None
        self._conector: DBConnector | None = None

    def preparar(
        self, db_id: str, statements: list[str]
    ) -> tuple[DBConnector, list[AplicacaoIndice]]:
        from .sqlite_connector import SQLiteConnector

        origem = self._db_dir / db_id / f"{db_id}.sqlite"
        destino_dir = self._tmp_dir / db_id
        destino_dir.mkdir(parents=True, exist_ok=True)
        self._copia = destino_dir / f"{db_id}.sqlite"
        shutil.copy2(str(origem), str(self._copia))

        resultados: list[AplicacaoIndice] = []
        conn = sqlite3.connect(str(self._copia))
        try:
            for stmt in statements:
                try:
                    conn.execute(stmt)
                    conn.commit()
                    resultados.append(AplicacaoIndice(stmt, True))
                except Exception as exc:
                    resultados.append(AplicacaoIndice(stmt, False, str(exc)))
        finally:
            conn.close()

        # O conector aponta para o diretorio tmp, onde a copia mora.
        self._conector = SQLiteConnector(str(self._tmp_dir))
        return self._conector, resultados

    def limpar(self, db_id: str) -> None:
        if self._conector is not None:
            self._conector.close()
            self._conector = None
        if self._copia is not None:
            try:
                self._copia.unlink()
            except OSError:
                pass
            self._copia = None


class IsolamentoPorTransacao(EstrategiaIsolamento):
    """PostgreSQL e MariaDB: cria os indices no banco e os derruba ao final.

    Os nomes criados sao gravados em `registro` antes de qualquer medicao, para
    que uma queda no meio da rodada deixe rastro suficiente para limpeza.
    """

    def __init__(self, conector: DBConnector, registro: Path) -> None:
        self._conector = conector
        self._registro = Path(registro)
        self._criados: list[str] = []

    def preparar(
        self, db_id: str, statements: list[str]
    ) -> tuple[DBConnector, list[AplicacaoIndice]]:
        resultados: list[AplicacaoIndice] = []
        self._criados = []

        for stmt in statements:
            nome = _NOME_INDICE.search(stmt)
            try:
                self._conector.execute(stmt, db_id=db_id)
                resultados.append(AplicacaoIndice(stmt, True))
                if nome:
                    self._criados.append(nome.group(1))
                    self._gravar_registro(db_id)
            except Exception as exc:
                resultados.append(AplicacaoIndice(stmt, False, str(exc)))

        # Estatisticas atualizadas: sem isso o otimizador pode ignorar os
        # indices recem-criados e a medicao "depois" fica invalida.
        try:
            self._conector.execute("ANALYZE", db_id=db_id)
        except Exception:
            pass

        return self._conector, resultados

    def _gravar_registro(self, db_id: str) -> None:
        self._registro.parent.mkdir(parents=True, exist_ok=True)
        self._registro.write_text(
            json.dumps({"db_id": db_id, "indices": self._criados}, indent=2),
            encoding="utf-8",
        )

    def _tabela_do_indice(self, nome: str, db_id: str) -> str | None:
        """Descobre a qual tabela um indice pertence, via catalogo.

        O MariaDB exige `DROP INDEX <nome> ON <tabela>`; adivinhar a tabela
        pelo nome do indice quebraria com qualquer convencao diferente da
        sugerida no prompt.
        """
        try:
            linhas = self._conector.execute(
                "SELECT table_name FROM information_schema.statistics "
                f"WHERE index_name = '{nome}' LIMIT 1",
                db_id=db_id,
            )
            return linhas[0][0] if linhas else None
        except Exception:
            return None

    def limpar(self, db_id: str) -> None:
        for nome in reversed(self._criados):
            try:
                # PostgreSQL aceita a forma simples.
                self._conector.execute(f"DROP INDEX {nome}", db_id=db_id)
                continue
            except Exception:
                pass
            tabela = self._tabela_do_indice(nome, db_id)
            if tabela:
                try:
                    self._conector.execute(
                        f"DROP INDEX `{nome}` ON `{tabela}`", db_id=db_id
                    )
                except Exception:
                    pass
        self._criados = []
        try:
            self._registro.unlink()
        except OSError:
            pass
