import pytest

from ui.vocab_table_rows import TableRow, build_rows_from_vocab


def test_table_row_to_list():
    row = TableRow(
        hanzi="開會",
        jyutping="hoi1 wui6",
        meanings="to meet",
        categories=["work", "admin"],
    )
    assert row.to_list() == ["開會", "hoi1 wui6", "to meet", "work, admin"]


def test_build_rows_flattens_meanings_and_categories():
    vocab = {
        "開會": [["to meet", "hold a meeting"], "hoi1 wui6"],
        "晚": ["late", "maan5"],
    }
    cats = {"work": ["開會"], "time": ["晚", "開會"]}

    rows = build_rows_from_vocab(vocab, cats)
    by_hz = {r.hanzi: r for r in rows}

    assert by_hz["開會"].meanings == "to meet, hold a meeting"
    assert by_hz["開會"].categories == ["time", "work"]
    assert by_hz["晚"].categories == ["time"]
