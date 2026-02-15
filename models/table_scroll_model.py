from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TableScrollModel:
    """
    UI-free model for mapping:
        (total_rows, page_rows, first_row) <-> slider_value

    Contract (per tests):
      - slider range is 0..max_first_row
      - mapping is identity (slider value == first_row), with clamping
      - page_rows <= 0 is treated as 1
    """
    total_rows: int
    page_rows: int

    def __post_init__(self) -> None:
        tr = int(self.total_rows) if self.total_rows is not None else 0
        pr = int(self.page_rows) if self.page_rows is not None else 1
        if tr < 0:
            tr = 0
        if pr <= 0:
            pr = 1
        object.__setattr__(self, "total_rows", tr)
        object.__setattr__(self, "page_rows", pr)

    @property
    def max_first_row(self) -> int:
        # last possible first row such that a full page fits (or as much as possible)
        # when total_rows <= page_rows, max_first_row = 0
        m = self.total_rows - self.page_rows
        return m if m > 0 else 0

    @property
    def slider_min(self) -> int:
        return 0

    @property
    def slider_max(self) -> int:
        return self.max_first_row

    def clamp_first_row(self, first_row: int) -> int:
        try:
            fr = int(first_row)
        except Exception:
            fr = 0
        if fr < 0:
            return 0
        mx = self.max_first_row
        if fr > mx:
            return mx
        return fr

    def first_row_from_slider(self, slider_value: int) -> int:
        return self.clamp_first_row(slider_value)

    def slider_from_first_row(self, first_row: int) -> int:
        return self.clamp_first_row(first_row)

    def with_total_rows(self, total_rows: int) -> "TableScrollModel":
        return TableScrollModel(total_rows=total_rows, page_rows=self.page_rows)

    def with_page_rows(self, page_rows: int) -> "TableScrollModel":
        return TableScrollModel(total_rows=self.total_rows, page_rows=page_rows)