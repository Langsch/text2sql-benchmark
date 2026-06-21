from __future__ import annotations


_INSTRUCTION = (
    "Output ONLY the CREATE INDEX statements, one per line.\n"
    "No explanations, no markdown code blocks, no comments.\n"
    "Use the format: CREATE INDEX idx_<table>_<columns> ON <table>(<col1>, <col2>, ...);\n"
    "Do NOT create indexes on columns that are already PRIMARY KEYs."
)


class IndexPromptBuilder:
    """Builds a prompt asking the LLM to suggest CREATE INDEX statements."""

    def build(self, schema: str, queries: list[str], db_id: str) -> str:
        parts: list[str] = []

        parts.append(
            "You are a database performance expert. "
            "Given the following SQLite database schema and a set of SQL queries "
            "that run against this database, suggest CREATE INDEX statements "
            "that would improve the performance of these queries."
        )

        parts.append(f"-- Database: {db_id}\n\n{schema}")

        numbered = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(queries))
        parts.append(f"## Queries\n\n{numbered}")

        parts.append(
            "## Analysis guidelines\n"
            "- Look at columns used in WHERE, JOIN ON, ORDER BY, and GROUP BY clauses.\n"
            "- Consider composite indexes when multiple columns from the same table "
            "appear together in query conditions.\n"
            "- Prioritize indexes that benefit the most queries.\n"
            "- Use SQLite CREATE INDEX syntax."
        )

        parts.append(_INSTRUCTION)

        return "\n\n".join(parts)
