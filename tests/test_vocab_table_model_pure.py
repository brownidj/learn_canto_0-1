import pytest


# NOTE: This module intentionally fails until Step 2 introduces the model.
# It defines the UI-free contract for mapping:
#   (total_rows, page_rows, first_row) <-> slider_value
from models.table_scroll_model import TableScrollModel


def test_range_when_table_fits_on_one_page():
    m = TableScrollModel(total_rows=10, page_rows=10)
    assert m.max_first_row == 0
    assert m.slider_min == 0
    assert m.slider_max == 0

    assert m.first_row_from_slider(0) == 0
    assert m.slider_from_first_row(0) == 0


def test_range_when_table_is_larger_than_page():
    m = TableScrollModel(total_rows=100, page_rows=20)
    assert m.max_first_row == 80
    assert m.slider_min == 0
    assert m.slider_max == 80


@pytest.mark.parametrize(
    "total_rows,page_rows,requested,expected",
    [
        (0, 10, 0, 0),
        (0, 10, 5, 0),
        (10, 10, 0, 0),
        (10, 10, 9, 0),
        (11, 10, 0, 0),
        (11, 10, 1, 1),
        (11, 10, 2, 1),  # clamp to max_first_row=1
        (100, 20, -5, 0),
        (100, 20, 0, 0),
        (100, 20, 80, 80),
        (100, 20, 81, 80),
        (100, 20, 999, 80),
    ],
)
def test_first_row_clamps(total_rows, page_rows, requested, expected):
    m = TableScrollModel(total_rows=total_rows, page_rows=page_rows)
    assert m.clamp_first_row(requested) == expected


@pytest.mark.parametrize("val", [0, 1, 5, 17, 80])
def test_slider_round_trip_identity_for_valid_values(val):
    m = TableScrollModel(total_rows=100, page_rows=20)
    # When slider range is defined as 0..max_first_row, mapping is identity.
    first = m.first_row_from_slider(val)
    assert first == val
    assert m.slider_from_first_row(first) == val


def test_first_row_from_slider_clamps():
    m = TableScrollModel(total_rows=100, page_rows=20)
    assert m.first_row_from_slider(-1) == 0
    assert m.first_row_from_slider(999) == 80


def test_update_total_rows_recomputes_ranges():
    m = TableScrollModel(total_rows=50, page_rows=10)
    assert m.max_first_row == 40

    m2 = m.with_total_rows(12)
    assert m2.total_rows == 12
    assert m2.page_rows == 10
    assert m2.max_first_row == 2
    assert m2.slider_max == 2


def test_update_page_rows_recomputes_ranges():
    m = TableScrollModel(total_rows=50, page_rows=10)
    assert m.max_first_row == 40

    m2 = m.with_page_rows(25)
    assert m2.total_rows == 50
    assert m2.page_rows == 25
    assert m2.max_first_row == 25
    assert m2.slider_max == 25


def test_invalid_page_rows_is_treated_as_one_row_page():
    m = TableScrollModel(total_rows=10, page_rows=0)
    assert m.page_rows == 1
    assert m.max_first_row == 9

    m2 = TableScrollModel(total_rows=10, page_rows=-5)
    assert m2.page_rows == 1
    assert m2.max_first_row == 9