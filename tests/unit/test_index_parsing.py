from text2sql_benchmark.runner.index_runner import parse_index_statements


def test_basic_create_index():
    raw = "CREATE INDEX idx_member_name ON member(first_name, last_name);"
    result = parse_index_statements(raw)
    assert len(result) == 1
    assert "idx_member_name" in result[0]
    assert result[0].endswith(";")


def test_multiple_statements():
    raw = (
        "CREATE INDEX idx_a ON t1(col1);\n"
        "CREATE INDEX idx_b ON t2(col2, col3);\n"
        "CREATE UNIQUE INDEX idx_c ON t3(col4);"
    )
    result = parse_index_statements(raw)
    assert len(result) == 3


def test_strips_markdown_fences():
    raw = "```sql\nCREATE INDEX idx_a ON t1(col1);\n```"
    result = parse_index_statements(raw)
    assert len(result) == 1
    assert "idx_a" in result[0]


def test_strips_think_tags():
    raw = (
        "<think>Let me analyze the queries...</think>\n"
        "CREATE INDEX idx_a ON t1(col1);"
    )
    result = parse_index_statements(raw)
    assert len(result) == 1


def test_ignores_explanatory_text():
    raw = (
        "Here are my suggestions:\n\n"
        "CREATE INDEX idx_a ON t1(col1);\n\n"
        "This index will help with query 3.\n\n"
        "CREATE INDEX idx_b ON t2(col2);\n"
    )
    result = parse_index_statements(raw)
    assert len(result) == 2


def test_handles_missing_semicolon():
    raw = "CREATE INDEX idx_a ON t1(col1)"
    result = parse_index_statements(raw)
    assert len(result) == 1
    assert result[0].endswith(";")


def test_handles_if_not_exists():
    raw = "CREATE INDEX IF NOT EXISTS idx_a ON t1(col1);"
    result = parse_index_statements(raw)
    assert len(result) == 1
    assert "IF NOT EXISTS" in result[0]


def test_empty_response():
    result = parse_index_statements("")
    assert result == []


def test_no_create_index_in_response():
    raw = "I don't think any indexes are needed for these queries."
    result = parse_index_statements(raw)
    assert result == []


def test_think_tags_with_index_inside():
    raw = (
        "<think>Maybe CREATE INDEX idx_wrong ON t(c); would work</think>\n"
        "CREATE INDEX idx_right ON t1(col1);"
    )
    result = parse_index_statements(raw)
    assert len(result) == 1
    assert "idx_right" in result[0]


def test_composite_index():
    raw = "CREATE INDEX idx_member_name_zip ON member(first_name, last_name, zip);"
    result = parse_index_statements(raw)
    assert len(result) == 1
    assert "first_name, last_name, zip" in result[0]
