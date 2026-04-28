from app.rule.domain.scope_triple import normalize_scope_triple


def test_normalize_scope_triple_strips_and_empty_to_none() -> None:
    assert normalize_scope_triple("  a ", " b", "") == ("a", "b", None)
    assert normalize_scope_triple(None, None, None) == (None, None, None)
