from __future__ import annotations


# Nome do SGBD e nota de sintaxe especifica de cada dialeto. O restante do
# prompt e identico entre dialetos e entre modelos: so estes dois campos mudam,
# para que a comparacao entre modelos permaneca valida.
_DIALECTS: dict[str, tuple[str, str]] = {
    "sqlite": (
        "SQLite",
        (
            "- Use SQLite CREATE INDEX syntax.\n"
            "- SQLite creates indexes for PRIMARY KEY columns automatically."
        ),
    ),
    "postgresql": (
        "PostgreSQL",
        (
            "- Use PostgreSQL CREATE INDEX syntax.\n"
            "- PostgreSQL creates indexes for PRIMARY KEY and UNIQUE constraints "
            "automatically.\n"
            "- Default to B-tree indexes unless the query pattern clearly calls "
            "for another access method."
        ),
    ),
    "mariadb": (
        "MariaDB",
        (
            "- Use MariaDB CREATE INDEX syntax.\n"
            "- MariaDB creates indexes for PRIMARY KEY and UNIQUE constraints "
            "automatically.\n"
            "- Indexes on TEXT or BLOB columns require a prefix length, "
            "e.g. col(255)."
        ),
    ),
}

_INSTRUCTION = (
    "Output ONLY the CREATE INDEX statements, one per line.\n"
    "No explanations, no markdown code blocks, no comments.\n"
    "Use the format: CREATE INDEX idx_<table>_<columns> ON <table>(<col1>, <col2>, ...);\n"
    "Do NOT create indexes on columns that are already PRIMARY KEYs."
)


class IndexPromptBuilder:
    """Builds a prompt asking the LLM to suggest CREATE INDEX statements."""

    def build(
        self,
        schema: str,
        queries: list[str],
        db_id: str,
        dialect: str = "sqlite",
    ) -> str:
        key = dialect.lower()
        if key not in _DIALECTS:
            raise ValueError(
                f"Dialeto sem suporte no prompt de indices: {dialect!r}. "
                f"Suportados: {', '.join(sorted(_DIALECTS))}"
            )
        sgbd_name, syntax_notes = _DIALECTS[key]

        parts: list[str] = []

        parts.append(
            "You are a database performance expert. "
            f"Given the following {sgbd_name} database schema and a set of SQL queries "
            "that run against this database, suggest CREATE INDEX statements "
            "that would improve the performance of these queries."
        )

        parts.append(f"-- Database: {db_id} ({sgbd_name})\n\n{schema}")

        numbered = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(queries))
        parts.append(f"## Queries\n\n{numbered}")

        parts.append(
            "## Analysis guidelines\n"
            "- Look at columns used in WHERE, JOIN ON, ORDER BY, and GROUP BY clauses.\n"
            "- Consider composite indexes when multiple columns from the same table "
            "appear together in query conditions.\n"
            "- Prioritize indexes that benefit the most queries.\n"
            f"{syntax_notes}"
        )

        parts.append(_INSTRUCTION)

        return "\n\n".join(parts)
