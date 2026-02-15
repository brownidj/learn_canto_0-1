"""
CategoryManager typography and geometry helpers extracted for maintainability.

Handles font sizing, widget geometry, and debug logging for layout issues.
"""

import logging
from typing import TYPE_CHECKING

from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QFormLayout, QGroupBox, QLabel
from ui.category_manager_dialog_adapter import CategoryManagerDialogAdapter
from ui.category_manager_widgets import resolve_category_manager_widgets

if TYPE_CHECKING:
    from category_manager import CategoryManagerDialog

logger = logging.getLogger(__name__)


class CategoryManagerTypographyController:
    """Manages typography and geometry for CategoryManagerDialog."""

    def __init__(self, dialog: "CategoryManagerDialog"):
        self.dialog = dialog
        self._dlg = CategoryManagerDialogAdapter(dialog)

    def apply_add_edit_typography(
        self,
        *,
        group_entry: QGroupBox,
        form_entry: QFormLayout,
        group_hanzi: QGroupBox,
        form_hanzi: QFormLayout,
    ) -> None:
        """Apply the Add/Edit panel typography in one place.

        - Labels: +_LABEL_FONT_DELTA_PT
        - Input fields (Jyutping, Meanings, Hanzi): +_INPUT_FONT_DELTA_PT
        - Form vertical spacing: _FORM_VERTICAL_SPACING_PX

        Best-effort only: this must never break dialog construction.
        """
        try:
            from PySide6.QtCore import Qt
        except (ImportError, ModuleNotFoundError):
            Qt = None

        # Spacing
        try:
            form_entry.setVerticalSpacing(int(self._dlg.get("_FORM_VERTICAL_SPACING_PX")))
        except (TypeError, ValueError, AttributeError):
            pass
        try:
            form_hanzi.setVerticalSpacing(int(self._dlg.get("_FORM_VERTICAL_SPACING_PX")))
        except (TypeError, ValueError, AttributeError):
            pass

        base_entry = group_entry.font()
        base_hanzi = group_hanzi.font()

        label_entry = QFont(base_entry)
        label_entry.setPointSize(label_entry.pointSize() + int(self._dlg.get("_LABEL_FONT_DELTA_PT")))

        label_hanzi = QFont(base_hanzi)
        label_hanzi.setPointSize(label_hanzi.pointSize() + int(self._dlg.get("_LABEL_FONT_DELTA_PT")))

        input_entry = QFont(base_entry)
        input_entry.setPointSize(input_entry.pointSize() + int(self._dlg.get("_INPUT_FONT_DELTA_PT")))

        input_hanzi = QFont(base_hanzi)
        input_hanzi.setPointSize(int(self._dlg.get("_HANZI_TEXT_DELTA_PT")))

        # Apply label fonts
        for _r in range(form_hanzi.rowCount()):
            _it = form_hanzi.itemAt(_r, QFormLayout.ItemRole.LabelRole)
            _w = _it.widget() if _it is not None else None
            if isinstance(_w, QLabel):
                try:
                    _w.setFont(label_hanzi)
                except (RuntimeError, TypeError, AttributeError):
                    pass

        # Apply input fonts
        widgets = resolve_category_manager_widgets(self._dlg)
        jy = widgets.get("add_jy")
        if jy is not None:
            try:
                jy.setFont(input_entry)
            except (RuntimeError, TypeError, AttributeError):
                pass

        mn = widgets.get("add_mn")
        if mn is not None:
            try:
                mn.setFont(input_entry)
            except (RuntimeError, TypeError, AttributeError):
                pass

        hz = widgets.get("add_hz")
        if hz is not None:
            try:
                hz.setFont(input_hanzi)
            except (RuntimeError, TypeError, AttributeError):
                pass

            # Ensure tall enough for glyphs
            try:
                m = QFontMetrics(input_hanzi)
                target_h = int(m.height() * 1.25) + 12
                hz.setMinimumHeight(target_h)
                try:
                    hz.setTextMargins(10, 6, 10, 6)
                except (TypeError, AttributeError, RuntimeError):
                    pass
                if Qt is not None:
                    hz.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            except (TypeError, AttributeError, RuntimeError, ValueError):
                pass

        # Candidate combobox: leave platform defaults
        combo = widgets.get("cand_combo")
        if combo is not None:
            try:
                combo.setStyleSheet("")
            except (RuntimeError, TypeError, AttributeError):
                pass

        try:
            self.debug_hanzi_panel_geometry("after _apply_add_edit_typography")
        except (TypeError, AttributeError, RuntimeError, ValueError):
            pass

    def debug_hanzi_panel_geometry(self, reason: str = "") -> None:
        """Debug geometry/fonts for the Hanzi panel.

        Temporary diagnostic for clipping / sizing issues. Must never raise.
        """
        try:
            widgets = resolve_category_manager_widgets(self._dlg)
            hz = widgets.get("add_hz")
            combo = widgets.get("cand_combo")
            btn = widgets.get("btn_custom_hz")

            grp = None
            try:
                if hz is not None:
                    grp = hz.parent()
            except (TypeError, AttributeError, RuntimeError):
                grp = None

            def _g(w):
                if w is None:
                    return "None"
                try:
                    g = w.geometry()
                    return "x={0} y={1} w={2} h={3}".format(
                        int(g.x()), int(g.y()), int(g.width()), int(g.height())
                    )
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    return "?"

            def _cr(w):
                if w is None:
                    return "None"
                try:
                    r = w.contentsRect()
                    return "x={0} y={1} w={2} h={3}".format(
                        int(r.x()), int(r.y()), int(r.width()), int(r.height())
                    )
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    return "?"

            def _font(w):
                if w is None:
                    return "None"
                try:
                    f = w.font()
                    return "family={0} pt={1} px={2}".format(
                        str(f.family()), int(f.pointSize()), int(f.pixelSize())
                    )
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    return "?"

            def _sh(w):
                if w is None:
                    return "None"
                try:
                    s = w.sizeHint()
                    return "w={0} h={1}".format(int(s.width()), int(s.height()))
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    return "?"

            def _minmax(w):
                if w is None:
                    return "None"
                try:
                    return "min={0}x{1} max={2}x{3}".format(
                        int(w.minimumWidth()),
                        int(w.minimumHeight()),
                        int(w.maximumWidth()),
                        int(w.maximumHeight()),
                    )
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    return "?"

            view = None
            try:
                view = combo.view() if combo is not None else None
            except (TypeError, AttributeError, RuntimeError):
                view = None

            logger.debug("HANZI-GEO %s", str(reason or "").strip())
            logger.debug("  grp:   geo=%s cr=%s sh=%s %s font=%s", _g(grp), _cr(grp), _sh(grp), _minmax(grp), _font(grp))
            ro = False
            try:
                ro = bool(hz.isReadOnly()) if hz is not None else False
            except Exception:
                ro = False
            try:
                align = str(hz.alignment()) if hz is not None else "?"
            except Exception:
                align = "?"
            logger.debug(
                "  hz:    geo=%s cr=%s sh=%s %s ro=%s align=%s font=%s",
                _g(hz),
                _cr(hz),
                _sh(hz),
                _minmax(hz),
                ro,
                align,
                _font(hz),
            )
            logger.debug(
                "  combo: geo=%s cr=%s sh=%s %s vis=%s font=%s",
                _g(combo),
                _cr(combo),
                _sh(combo),
                _minmax(combo),
                bool(combo.isVisible()) if combo is not None else False,
                _font(combo),
            )

            try:
                ss = combo.styleSheet() if combo is not None else ""
            except (TypeError, AttributeError, RuntimeError):
                ss = ""
            if ss:
                logger.debug("  combo stylesheet: %s", ss)

            logger.debug(
                "  view:  geo=%s cr=%s sh=%s %s vis=%s font=%s",
                _g(view),
                _cr(view),
                _sh(view),
                _minmax(view),
                bool(view.isVisible()) if view is not None else False,
                _font(view),
            )

            logger.debug(
                "  btn:   geo=%s cr=%s sh=%s %s text=%r font=%s",
                _g(btn),
                _cr(btn),
                _sh(btn),
                _minmax(btn),
                str(btn.text()) if btn is not None else "",
                _font(btn),
            )

            # Font metrics
            try:
                if hz is not None:
                    fm = QFontMetrics(hz.font())
                    logger.debug(
                        "  hz metrics: h=%d asc=%d desc=%d lead=%d",
                        int(fm.height()),
                        int(fm.ascent()),
                        int(fm.descent()),
                        int(fm.leading()),
                    )
            except (TypeError, AttributeError, RuntimeError, ValueError):
                pass

            try:
                if combo is not None:
                    fm2 = QFontMetrics(combo.font())
                    logger.debug(
                        "  combo metrics: h=%d asc=%d desc=%d lead=%d",
                        int(fm2.height()),
                        int(fm2.ascent()),
                        int(fm2.descent()),
                        int(fm2.leading()),
                    )
            except (TypeError, AttributeError, RuntimeError, ValueError):
                pass

        except (TypeError, AttributeError, RuntimeError, ValueError):
            return

    def ensure_combo_closed_height(self, combo) -> None:
        """Ensure the *closed* combobox height is compact.

        Avoids QStyleOption/initStyleOption calls that trigger macOS headless segfaults.
        """
        try:
            if combo is None:
                return

            fm = combo.fontMetrics()
            text_h = 0
            try:
                text_h = int(fm.lineSpacing())
            except (TypeError, AttributeError, RuntimeError, ValueError):
                try:
                    text_h = int(fm.height())
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    text_h = 0

            # Empirical padding for macOS/Aqua
            target = max(34, text_h + 14)

            try:
                combo.setMinimumHeight(target)
                combo.setMaximumHeight(target)
            except (TypeError, AttributeError, RuntimeError, ValueError):
                try:
                    combo.setFixedHeight(target)
                except (TypeError, AttributeError, RuntimeError, ValueError):
                    pass

            try:
                combo.updateGeometry()
            except (TypeError, AttributeError, RuntimeError, ValueError):
                pass

        except Exception as e:
            try:
                logger.debug("_ensure_combo_closed_height skipped (%s)", e)
            except (TypeError, AttributeError, RuntimeError, ValueError):
                pass
