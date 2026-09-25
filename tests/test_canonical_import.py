from deadbot.canonical_import import (
    TABLE_SPECS,
    SelectionRows,
    read_selection_evidence,
    selection_evidence_rows,
)
from deadbot import postgres_import


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


def test_postgres_importer_reexports_the_shared_contract():
    assert postgres_import.TABLE_SPECS is TABLE_SPECS
    assert postgres_import.read_selection_evidence is read_selection_evidence
