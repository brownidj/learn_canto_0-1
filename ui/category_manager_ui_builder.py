"""
CategoryManager UI builder extracted for maintainability.

Handles widget creation, layout construction, and initial setup.
"""

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt as _Qt
from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QGroupBox,
    QFormLayout,
    QLineEdit,
    QComboBox, QLabel,
)

if TYPE_CHECKING:
    from category_manager import CategoryManagerDialog

logger = logging.getLogger(__name__)


class CategoryManagerUIBuilder:
    """Builds UI components for CategoryManagerDialog."""

    def __init__(self, dialog: "CategoryManagerDialog"):
        self.dialog = dialog

    def build_ui(self) -> None:
        """Build the complete UI for the dialog."""
        self._create_root_layout()
        self._create_header()
        self._create_entry_group()
        self._create_hanzi_group()
        self._create_table_panel()

    def _create_root_layout(self) -> None:
        """Create root layout."""
        self.dialog._root = QVBoxLayout(self.dialog)
        self.dialog._root.setContentsMargins(12, 12, 12, 12)
        self.dialog._root.setSpacing(10)

    def _create_header(self) -> None:
        """Create header with Close button."""
        header = QHBoxLayout()
        header.addStretch(1)

        btn_close = QPushButton("Close", self.dialog)
        btn_close.setDefault(False)
        btn_close.setAutoDefault(False)
        btn_close.clicked.connect(self.dialog.accept)

        header.addWidget(btn_close, 0, _Qt.AlignmentFlag.AlignTop | _Qt.AlignmentFlag.AlignRight)
        self.dialog._root.addLayout(header)

    def _create_save_header(self) -> None:
        """Create save button header."""
        header_row = QHBoxLayout()

        self.dialog.btn_save = QPushButton("Save")
        self.dialog.btn_save.setObjectName("btn_save")

        try:
            save_ctrl = getattr(self.dialog, "_save_commit", None)
        except (TypeError, AttributeError, RuntimeError):
            save_ctrl = None
        if save_ctrl is not None and hasattr(save_ctrl, "on_save_clicked"):
            self.dialog.btn_save.clicked.connect(save_ctrl.on_save_clicked)

        self.dialog.btn_save.setDefault(False)
        self.dialog.btn_save.setAutoDefault(False)
        self.dialog.btn_save.setEnabled(False)
        self.dialog.btn_save.setToolTip("Save Hanzi + Jyutping + Category")

        # Hide by default
        try:
            preview_ctrl = getattr(self.dialog, "_preview_confirm", None)
            if preview_ctrl is not None:
                preview_ctrl.set_save_button_visible(False)
        except (AttributeError, TypeError, ValueError, RuntimeError):
            pass

        header_row.addStretch(1)
        header_row.addWidget(self.dialog.btn_save, 0, _Qt.AlignmentFlag.AlignRight)
        self.dialog._root.addLayout(header_row)

    def _create_entry_group(self) -> None:
        """Create Entry group (Jyutping, Meanings, Notes, Category)."""
        # Save header first
        self._create_save_header()

        # Main row for Entry + Hanzi groups
        row = QHBoxLayout()
        row.setSpacing(12)

        # Entry group
        group_entry = QGroupBox("Entry", self.dialog)
        form_entry = QFormLayout(group_entry)
        form_entry.setLabelAlignment(_Qt.AlignmentFlag.AlignRight | _Qt.AlignmentFlag.AlignVCenter)
        form_entry.setFormAlignment(_Qt.AlignmentFlag.AlignLeft | _Qt.AlignmentFlag.AlignTop)
        form_entry.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        # Set vertical spacing between form rows to 18pt for comfortable layout
        form_entry.setVerticalSpacing(18)

        # Jyutping field
        from PySide6.QtWidgets import QSizePolicy
        self.dialog._add_jy = QLineEdit(group_entry)
        self.dialog._add_jy.setPlaceholderText("e.g. nei5 hou2")
        self.dialog._add_jy.setClearButtonEnabled(True)
        self.dialog._add_jy.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        # Meanings field
        self.dialog._add_mn = QLineEdit(group_entry)
        self.dialog._add_mn.setPlaceholderText("comma-separated meanings, e.g. hello, hi")
        self.dialog._add_mn.setClearButtonEnabled(True)
        self.dialog._add_mn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        # Notes field
        self.dialog._add_notes = QLineEdit(group_entry)
        self.dialog._add_notes.setReadOnly(True)
        self.dialog._add_notes.setPlaceholderText("Notes (auto; shown only when ambiguous)")
        self.dialog._add_notes.setToolTip(
            "Shown only when an entry is ambiguous or needs confirmation. "
            "Auto-default entries never keep notes."
        )
        self.dialog._add_notes.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        # Create labels with 16pt font
        from PySide6.QtGui import QFont
        from PySide6.QtWidgets import QSizePolicy
        label_font = QFont()
        label_font.setPointSize(16)

        # Create labels with proper height
        label_jy = QLabel("Jyutping:")
        label_jy.setFont(label_font)
        label_jy.setMinimumHeight(40)
        label_jy.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        label_mn = QLabel("Meanings:")
        label_mn.setFont(label_font)
        label_mn.setMinimumHeight(40)
        label_mn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        label_notes = QLabel("Notes:")
        label_notes.setFont(label_font)
        label_notes.setMinimumHeight(40)
        label_notes.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        form_entry.addRow(label_jy, self.dialog._add_jy)
        form_entry.addRow(label_mn, self.dialog._add_mn)
        form_entry.addRow(label_notes, self.dialog._add_notes)

        # Category combobox
        from PySide6.QtWidgets import QSizePolicy
        self.dialog._add_cat = QComboBox(group_entry)
        self.dialog._add_cat.setObjectName("comboAddCategories")
        self.dialog._add_cat.setEditable(True)
        self.dialog._add_cat.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.dialog._add_cat.addItems(self.dialog._all_cats)
        self.dialog._add_cat.setCurrentIndex(-1)
        self.dialog._add_cat.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        try:
            from PySide6.QtWidgets import QListView
            from PySide6.QtCore import Qt
            cat_view = QListView(self.dialog._add_cat)
            cat_view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.dialog._add_cat.setView(cat_view)
        except Exception:
            pass

        le_cat = self.dialog._add_cat.lineEdit()
        if le_cat is not None:
            le_cat.setPlaceholderText("Type category")
            le_cat.setClearButtonEnabled(True)

        # Wire category controller
        try:
            from ui.category_combo import CategoryComboController
            _on_cat_commit = None
            try:
                ops = getattr(self.dialog, "_category_ops", None)
                if ops is not None and hasattr(ops, "on_add_category_committed"):
                    _on_cat_commit = ops.on_add_category_committed
            except (TypeError, AttributeError, RuntimeError):
                _on_cat_commit = None
            _on_add_new = None
            try:
                ops = getattr(self.dialog, "_category_ops", None)
                if ops is not None and hasattr(ops, "add_new_category"):
                    _on_add_new = ops.add_new_category
            except (TypeError, AttributeError, RuntimeError):
                _on_add_new = None
            self.dialog._cat_combo_ctrl = CategoryComboController(
                combo=self.dialog._add_cat,
                on_commit=_on_cat_commit if callable(_on_cat_commit) else None,
            )
            try:
                from ui.category_combo_add import CategoryComboAddController
                self.dialog._cat_combo_add_ctrl = CategoryComboAddController(
                    combo_ctrl=self.dialog._cat_combo_ctrl,
                    on_add_new=_on_add_new if callable(_on_add_new) else None,
                )
            except Exception:
                self.dialog._cat_combo_add_ctrl = None
        except (ImportError, TypeError, AttributeError, RuntimeError):
            self.dialog._cat_combo_ctrl = None
            self.dialog._cat_combo_add_ctrl = None

        # Category label with 16pt font
        from PySide6.QtGui import QFont
        label_font_cat = QFont()
        label_font_cat.setPointSize(16)

        label_cat = QLabel("Category:")
        label_cat.setFont(label_font_cat)
        label_cat.setMinimumHeight(40)
        label_cat.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        form_entry.addRow(label_cat, self.dialog._add_cat)

        # Back-compat aliases
        self.dialog.editJyut = self.dialog._add_jy
        self.dialog.editMeanings = self.dialog._add_mn
        self.dialog.comboCategory = self.dialog._add_cat

        # Store for typography
        self._group_entry = group_entry
        self._form_entry = form_entry

        # Set 16pt font for Entry panel input fields
        from PySide6.QtGui import QFont
        entry_font = QFont()
        entry_font.setPointSize(16)

        # Apply font to all Entry panel fields
        self.dialog._add_jy.setFont(entry_font)
        self.dialog._add_jy.setMinimumHeight(40)

        self.dialog._add_mn.setFont(entry_font)
        self.dialog._add_mn.setMinimumHeight(40)

        self.dialog._add_notes.setFont(entry_font)
        self.dialog._add_notes.setMinimumHeight(40)

        # Set font for Category combobox
        self.dialog._add_cat.setFont(entry_font)
        self.dialog._add_cat.setMinimumHeight(40)

        # Also set font for the combobox's line edit (when editable)
        le_cat = self.dialog._add_cat.lineEdit()
        if le_cat is not None:
            le_cat.setFont(entry_font)

        # Set Entry panel width to 550px to accommodate wider Category combobox
        group_entry.setMinimumWidth(550)

        # Add to layout with stretch factor (Entry:Hanzi = 2:1 ratio)
        row.addWidget(group_entry, 2)

    def _create_hanzi_group(self) -> None:
        """Create Hanzi group (display, candidates, manual button)."""
        from ui.category_manager_constants import HANZI_CANDIDATE_TOOLTIP

        row = self.dialog._root.itemAt(self.dialog._root.count() - 1)
        if not isinstance(row, QHBoxLayout):
            return

        group_hanzi = QGroupBox("Hanzi", self.dialog)
        form_hanzi = QFormLayout(group_hanzi)

        # Set vertical spacing to 18pt to match Entry panel
        form_hanzi.setVerticalSpacing(18)

        # Hanzi display field
        from PySide6.QtWidgets import QSizePolicy
        self.dialog._add_hz = QLineEdit(group_hanzi)
        self.dialog._add_hz.setReadOnly(False)
        self.dialog._add_hz.setPlaceholderText("Auto, after reverse lookup")
        self.dialog._add_hz.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        form_hanzi.addRow(self.dialog._add_hz)

        # Candidate combo
        from ui.category_manager_combo_styles import HanziComboBoxProxyStyle
        self.dialog._cand_combo = QComboBox(group_hanzi)
        try:
            self.dialog._cand_combo.setStyle(HanziComboBoxProxyStyle())
        except Exception:
            pass
        self.dialog._cand_combo.setObjectName("comboHanziCandidates")
        self.dialog._cand_combo.setVisible(False)
        self.dialog._cand_combo.setToolTip(HANZI_CANDIDATE_TOOLTIP)
        try:
            from PySide6.QtWidgets import QListView
            from PySide6.QtCore import Qt
            cand_view = QListView(self.dialog._cand_combo)
            cand_view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.dialog._cand_combo.setView(cand_view)
        except Exception:
            pass
        if self.dialog._cand_combo.view() is not None:
            self.dialog._cand_combo.view().setToolTip(HANZI_CANDIDATE_TOOLTIP)

        # Candidates label with 16pt font
        from PySide6.QtGui import QFont
        label_font_cand = QFont()
        label_font_cand.setPointSize(16)

        label_cand = QLabel("Candidates:")
        label_cand.setFont(label_font_cand)

        form_hanzi.addRow(label_cand, self.dialog._cand_combo)

        # Manual Hanzi button
        self.dialog._btn_custom_hz = QPushButton("Enter my own Hanzi", self.dialog)
        self.dialog._btn_custom_hz.setDefault(False)
        self.dialog._btn_custom_hz.setAutoDefault(False)

        try:
            self.dialog._btn_custom_hz.clicked.connect(self.dialog._on_btn_custom_hz_clicked)
        except (TypeError, AttributeError, RuntimeError):
            pass

        form_hanzi.addWidget(self.dialog._btn_custom_hz)

        # Back-compat alias
        self.dialog.comboCandidates = self.dialog._cand_combo

        # Store for typography
        self._group_hanzi = group_hanzi
        self._form_hanzi = form_hanzi

        # Set Hanzi panel width to 350px (matching Entry panel)
        group_hanzi.setMinimumWidth(350)

        # Increase groupbox heights to 280px to accommodate 40px vertical spacing
        group_entry = self._group_entry
        if group_entry is not None:
            group_entry.setMinimumHeight(280)
        group_hanzi.setMinimumHeight(280)

        # Add to layout with stretch factor (Entry:Hanzi = 2:1 ratio)
        row.addWidget(group_hanzi, 1)

        # Add the row to root layout with stretch factor to ensure vertical space
        # This prevents the Entry+Hanzi row from collapsing to zero height
        self.dialog._root.addLayout(row, 0)

        # Apply typography
        try:
            self.dialog._typography_ctrl.apply_add_edit_typography(
                group_entry=self._group_entry,
                form_entry=self._form_entry,
                group_hanzi=group_hanzi,
                form_hanzi=form_hanzi,
            )
        except (TypeError, AttributeError, RuntimeError):
            pass

    def _create_table_panel(self) -> None:
        """Create vocabulary table panel."""
        try:
            from ui.table_scroll_slider_controller import TableScrollSliderController
        except (ImportError, ModuleNotFoundError):
            TableScrollSliderController = None

        self.dialog._table_panel_ctrl = None
        self.dialog._table_panel = None
        self.dialog._vocab_table_ctrl = None

        if TableScrollSliderController is not None:
            try:
                create_fn = getattr(TableScrollSliderController, "create", None)
                if callable(create_fn):
                    self.dialog._table_panel_ctrl = create_fn(parent=self.dialog)
                else:
                    self.dialog._table_panel_ctrl = TableScrollSliderController(parent=self.dialog)

                self.dialog._table_panel = getattr(self.dialog._table_panel_ctrl, "widget", None)

                if self.dialog._table_panel is not None:
                    self.dialog._root.addWidget(self.dialog._table_panel, 1)

                    # Back-compat aliases
                    try:
                        self.dialog._search = self.dialog._table_panel.findChild(QLineEdit, "editTableSearch")
                    except Exception:
                        self.dialog._search = None

                    try:
                        self.dialog._table = self.dialog._table_panel.findChild(object, "tableVocab")
                    except Exception:
                        self.dialog._table = None

                    # Wire search handler
                    try:
                        fn_search = getattr(self.dialog, "_on_search_changed", None)
                        if callable(fn_search) and self.dialog._search is not None:
                            self.dialog._search.textChanged.connect(fn_search)
                    except (TypeError, AttributeError, RuntimeError):
                        pass

                    # Initialize table controller
                    if self.dialog._table is not None:
                        try:
                            from ui.vocabulary_table_controller import VocabularyTableController
                            self.dialog._vocab_table_ctrl = VocabularyTableController(
                                table=self.dialog._table,
                                vocab=self.dialog._vocab,
                                categories=self.dialog._cats,
                            )
                            self.dialog._vocab_table_ctrl.populate()
                        except (TypeError, AttributeError, RuntimeError):
                            self.dialog._vocab_table_ctrl = None

            except (TypeError, AttributeError, RuntimeError):
                self.dialog._table_panel_ctrl = None
                self.dialog._table_panel = None

        # Fallback: legacy widgets
        if self.dialog._table_panel is None:
            self._create_legacy_table()

        # Ensure attributes exist
        if not hasattr(self.dialog, "_search"):
            self.dialog._search = None
        if not hasattr(self.dialog, "_table"):
            self.dialog._table = None

    def _create_legacy_table(self) -> None:
        """Create legacy search + table (fallback)."""
        from PySide6.QtWidgets import QTableWidget, QAbstractItemView

        self.dialog._search = QLineEdit(self.dialog)
        self.dialog._search.setPlaceholderText("Search (Hanzi / Jyutping / meaning)…")
        self.dialog._search.setClearButtonEnabled(True)

        try:
            fn_search = getattr(self.dialog, "_on_search_changed", None)
            if callable(fn_search):
                self.dialog._search.textChanged.connect(fn_search)
        except (TypeError, AttributeError, RuntimeError):
            pass

        self.dialog._root.addWidget(self.dialog._search)

        self.dialog._table = QTableWidget(self.dialog)
        self.dialog._table.setColumnCount(4)
        self.dialog._table.setHorizontalHeaderLabels(["Hanzi", "Jyutping", "Meanings", "Categories"])
        self.dialog._table.horizontalHeader().setStretchLastSection(True)
        self.dialog._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.dialog._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.dialog._root.addWidget(self.dialog._table, 1)

        # Initialize table controller
        try:
            from ui.vocabulary_table_controller import VocabularyTableController
            self.dialog._vocab_table_ctrl = VocabularyTableController(
                table=self.dialog._table,
                vocab=self.dialog._vocab,
                categories=self.dialog._cats,
            )
            self.dialog._vocab_table_ctrl.populate()
        except (TypeError, AttributeError, RuntimeError):
            self.dialog._vocab_table_ctrl = None
