from deadbot.canonical_import import (
    SelectionRows,
    read_selection_evidence,
    selection_evidence_rows,
)


def test_selection_rows_are_deterministic_and_shaped_for_insert():
    document = read_selection_evidence()
    first = selection_evidence_rows(document)
    second = selection_evidence_rows(document)
    assert isinstance(first, SelectionRows)
    assert first == second
    assert len(first.evidence) == len(document["entries"])
    assert all(len(row) == 8 for row in first.resources)
    assert all(len(row) == 8 for row in first.lists)
    assert all(len(row) == 13 for row in first.entries)
    assert all(len(row) == 6 for row in first.evidence)
    resource_ids = {row[0] for row in first.resources}
    assert {row[1] for row in first.evidence} <= resource_ids
