from text2sql_benchmark.metrics import execution_accuracy, exact_match


def test_execution_accuracy_match():
    assert execution_accuracy([(1, "a"), (2, "b")], [(2, "b"), (1, "a")]) is True


def test_execution_accuracy_no_match():
    assert execution_accuracy([(1,)], [(2,)]) is False


def test_exact_match_normalized():
    assert exact_match("SELECT  id FROM `orders`", "select id from orders") is True


def test_exact_match_different():
    assert exact_match("SELECT id FROM orders", "SELECT name FROM orders") is False
