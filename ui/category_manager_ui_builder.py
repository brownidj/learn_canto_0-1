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
    QComboBox, QLabel, QWidget,
)

if TYPE_CHECKING:
    from category_manager import CategoryManagerDialog

logger = logging.getLogger(__name__)


class CategoryManagerUIBuilder:
    """Builds UI components for CategoryManagerDialog."""

    def __init__(self, dialog: "CategoryManagerDialog"):
        self.dialog = dialog
        self._dialog_data = getattr(dialog, "__dict__", {})

    def build_ui(self) -> None:
        """Build the complete UI for the dialog."""
        self._create_root_layout()
        self._create_entry_group()
        self._create_hanzi_group()
        self._create_close_row()
        self._create_table_panel()

    def _create_root_layout(self) -> None:
        """Create root layout."""
        self.dialog._root = QVBoxLayout(self.dialog)
        self.dialog._root.setContentsMargins(12, 12, 12, 12)
        self.dialog._root.setSpacing(10)

    def _create_close_row(self) -> None:
        """Create Close button row below the Entry/Hanzi panels."""
        row = QHBoxLayout()
        row.addStretch(1)

        btn_close = QPushButton("Close", self.dialog)
        btn_close.setDefault(False)
        btn_close.setAutoDefault(False)
        btn_close.clicked.connect(self.dialog.accept)

        row.addWidget(btn_close, 0, _Qt.AlignmentFlag.AlignRight)
        self.dialog._root.addLayout(row)

    def _create_save_header(self) -> None:
        """Create save button header."""
        header_row = QHBoxLayout()

        self.dialog.btn_save = QPushButton("Save")
        self.dialog.btn_save.setObjectName("btn_save")

        try:
            save_ctrl = self._dialog_data.get("_save_commit")
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
            preview_ctrl = self._dialog_data.get("_preview_confirm")
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
        row.setAlignment(_Qt.AlignmentFlag.AlignTop)
        self._entry_row = row

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

        # Category combobox
        from PySide6.QtWidgets import QSizePolicy
        self.dialog._add_cat = QComboBox(group_entry)
        self.dialog._add_cat.setObjectName("comboAddCategories")
        self.dialog._add_cat.setEditable(False)
        self.dialog._add_cat.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.dialog._add_cat.addItems(self.dialog._all_cats)
        self.dialog._add_cat.setCurrentIndex(-1)
        self.dialog._add_cat.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.dialog._cat_multi_select = True

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
                ops = self._dialog_data.get("_category_ops")
                if ops is not None and hasattr(ops, "on_add_category_committed"):
                    _on_cat_commit = ops.on_add_category_committed
            except (TypeError, AttributeError, RuntimeError):
                _on_cat_commit = None
            _on_add_new = None
            try:
                ops = self._dialog_data.get("_category_ops")
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

        # Add Category action button
        from PySide6.QtWidgets import QToolButton
        btn_add_cat = QToolButton(group_entry)
        btn_add_cat.setObjectName("btnAddCategory")
        btn_add_cat.setText("Add Category")
        btn_add_cat.setToolTip("Create a new category immediately")
        btn_add_cat.setAutoRaise(True)

        def _on_add_category_clicked():
            try:
                cat = str(self.dialog._add_cat.currentText() or "").strip()
            except Exception:
                cat = ""
            if not cat:
                try:
                    from PySide6.QtWidgets import QInputDialog
                    cat, ok = QInputDialog.getText(
                        self.dialog,
                        "Add Category",
                        "Category name:",
                    )
                    if not ok:
                        return
                    cat = str(cat or "").strip()
                except Exception:
                    return
            if not cat:
                return

            try:
                self.dialog._add_cat.setEditText(cat)
            except Exception:
                pass

            added = False
            add_ctrl = getattr(self.dialog, "_cat_combo_add_ctrl", None)
            if add_ctrl is not None and hasattr(add_ctrl, "confirm_or_add_new_category"):
                try:
                    added = bool(add_ctrl.confirm_or_add_new_category(text=cat))
                except Exception:
                    added = False
            if not added:
                try:
                    ops = self._dialog_data.get("_category_ops")
                    if ops is not None and hasattr(ops, "add_new_category"):
                        added = bool(ops.add_new_category(cat))
                except Exception:
                    added = False

            if added:
                try:
                    all_cats = getattr(self.dialog, "_all_cats", None)
                    if isinstance(all_cats, list) and cat not in all_cats:
                        all_cats.append(cat)
                        all_cats.sort(key=lambda s: str(s).lower())
                except Exception:
                    pass
                try:
                    from ui.category_manager_vocab_categories import CategoryManagerVocabCategories
                    CategoryManagerVocabCategories.refresh_category_dropdown_from_cats(
                        self.dialog, selected=cat
                    )
                except Exception:
                    pass
                try:
                    self.dialog._add_cat.setCurrentText(cat)
                except Exception:
                    pass
                # If multi-select, check the newly added item
                try:
                    if getattr(self.dialog, "_cat_multi_select", False):
                        from PySide6.QtCore import Qt
                        model = self.dialog._add_cat.model()
                        for i in range(model.rowCount()):
                            item = model.item(i) if hasattr(model, "item") else None
                            if item is not None and str(item.text() or "") == cat:
                                item.setData(Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
                                break
                        # Sync selection state after change
                        sync_fn = getattr(self.dialog, "_sync_selected_categories", None)
                        if callable(sync_fn):
                            sync_fn()
                except Exception:
                    pass

        try:
            btn_add_cat.clicked.connect(_on_add_category_clicked)
        except Exception:
            pass

        cat_row = QWidget(group_entry)
        cat_row_layout = QHBoxLayout(cat_row)
        cat_row_layout.setContentsMargins(0, 0, 0, 0)
        cat_row_layout.setSpacing(8)
        cat_row_layout.addWidget(self.dialog._add_cat, 1)
        cat_row_layout.addWidget(btn_add_cat, 0)

        # Selected categories chips preview
        label_selected = QLabel("")
        label_selected.setObjectName("labelSelectedCategories")
        label_selected.setWordWrap(True)
        label_selected.setStyleSheet(
            "QLabel { color: #444; font-size: 12pt; }"
        )
        self.dialog._cat_selected_label = label_selected

        # Category label with 16pt font
        from PySide6.QtGui import QFont
        label_font_cat = QFont()
        label_font_cat.setPointSize(16)

        label_cat = QLabel("Category:")
        label_cat.setFont(label_font_cat)
        label_cat.setMinimumHeight(40)
        label_cat.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        form_entry.addRow(label_cat, cat_row)
        form_entry.addRow(QLabel(""), label_selected)
        form_entry.addRow(label_mn, self.dialog._add_mn)
        form_entry.addRow(label_notes, self.dialog._add_notes)

        # Install checkable category list + selection wiring
        self._wire_category_multiselect()

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
            le_cat.setMinimumHeight(40)

        # Set Entry panel width to 550px to accommodate wider Category combobox
        group_entry.setMinimumWidth(550)

        # Add to layout with stretch factor (Entry:Hanzi = 2:1 ratio)
        row.addWidget(group_entry, 2)
        row.setAlignment(group_entry, _Qt.AlignmentFlag.AlignTop)

    def _wire_category_multiselect(self) -> None:
        combo = getattr(self.dialog, "_add_cat", None)
        if combo is None:
            return
        try:
            from PySide6.QtGui import QStandardItemModel, QStandardItem
            from PySide6.QtCore import Qt
        except Exception:
            return

        cats = self._dialog_data.get("_all_cats", []) if isinstance(self._dialog_data, dict) else []
        model = QStandardItemModel()
        for cat in (cats or []):
            item = QStandardItem(str(cat))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setData(Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
            model.appendRow(item)
        combo.setModel(model)

        def _current_selected() -> list[str]:
            out = []
            for row in range(model.rowCount()):
                item = model.item(row)
                if item is None:
                    continue
                try:
                    state = item.data(Qt.ItemDataRole.CheckStateRole)
                except Exception:
                    state = None
                if state == Qt.CheckState.Checked:
                    out.append(str(item.text() or "").strip())
            return [c for c in out if c]

        def _set_selected_label(cats_list: list[str]) -> None:
            label = getattr(self.dialog, "_cat_selected_label", None)
            if label is None:
                return
            if not cats_list:
                label.setText("No categories selected")
                return
            chips = " ".join(
                (
                    "<span style='background:#F2F2F2; border:1px solid #DDD; padding:2px 6px; "
                    f"border-radius:10px;'>{c}</span>"
                )
                for c in cats_list
            )
            label.setText(chips)

        def _sync_selected_state() -> None:
            cats_list = _current_selected()
            try:
                self.dialog._selected_categories = list(cats_list)
            except Exception:
                pass
            _set_selected_label(cats_list)
            # Update state machine with first selected category (if any)
            try:
                cat_first = cats_list[0] if cats_list else ""
            except Exception:
                cat_first = ""
            try:
                self.dialog._update_add_edit_state(category=cat_first, cat_ok=bool(cat_first))
            except Exception:
                pass
            # If Jyutping already present, refresh candidates using first category
            try:
                flow = getattr(self.dialog, "_add_edit_flow", None)
                jy_widget = getattr(self.dialog, "_add_jy", None)
                jy_val = str(jy_widget.text() or "").strip() if jy_widget is not None else ""
                if flow is not None and hasattr(flow, "fill_hanzi_candidates") and jy_val:
                    try:
                        flow.fill_hanzi_candidates(jy_val, category=cat_first or None)
                    except TypeError:
                        flow.fill_hanzi_candidates(jy_val)
            except Exception:
                pass
            try:
                self.dialog._update_save_enabled()
            except Exception:
                pass

        def _on_view_pressed(index):
            try:
                item = model.itemFromIndex(index)
            except Exception:
                item = None
            if item is None:
                return
            try:
                state = item.data(Qt.ItemDataRole.CheckStateRole)
                new_state = Qt.CheckState.Unchecked if state == Qt.CheckState.Checked else Qt.CheckState.Checked
                item.setData(new_state, Qt.ItemDataRole.CheckStateRole)
            except Exception:
                return
            _sync_selected_state()

        try:
            combo.view().pressed.connect(_on_view_pressed)
        except Exception:
            pass

        try:
            self.dialog._sync_selected_categories = _sync_selected_state
            self.dialog._cat_on_view_pressed = _on_view_pressed
        except Exception:
            pass

        _sync_selected_state()

    def _create_hanzi_group(self) -> None:
        """Create Hanzi group (display, candidates, manual button)."""
        from ui.category_manager_constants import HANZI_CANDIDATE_TOOLTIP

        row = getattr(self, "_entry_row", None)
        if not isinstance(row, QHBoxLayout):
            # Fallback to last layout if entry row wasn't captured.
            row = self.dialog._root.itemAt(self.dialog._root.count() - 1)
            if not isinstance(row, QHBoxLayout):
                return

        group_hanzi = QGroupBox("Hanzi", self.dialog)
        form_hanzi = QFormLayout(group_hanzi)

        # Set vertical spacing to 18pt to match Entry panel
        form_hanzi.setVerticalSpacing(18)
        form_hanzi.setFormAlignment(_Qt.AlignmentFlag.AlignLeft | _Qt.AlignmentFlag.AlignTop)
        form_hanzi.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

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
        self.dialog._cand_combo.setVisible(True)
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

        # Manual Hanzi button
        self.dialog._btn_custom_hz = QPushButton("Enter my own Hanzi", self.dialog)
        self.dialog._btn_custom_hz.setDefault(False)
        self.dialog._btn_custom_hz.setAutoDefault(False)

        try:
            self.dialog._btn_custom_hz.clicked.connect(self.dialog._on_btn_custom_hz_clicked)
        except (TypeError, AttributeError, RuntimeError):
            pass

        from PySide6.QtWidgets import QSizePolicy
        cand_row = QWidget(group_hanzi)
        cand_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        cand_row_layout = QHBoxLayout(cand_row)
        cand_row_layout.setContentsMargins(0, 0, 0, 0)
        cand_row_layout.addWidget(self.dialog._cand_combo, 1)
        cand_row_layout.addStretch(1)
        cand_row_layout.addWidget(self.dialog._btn_custom_hz, 0, _Qt.AlignmentFlag.AlignRight)
        cand_row_layout.setAlignment(_Qt.AlignmentFlag.AlignRight)

        form_hanzi.addRow(label_cand, cand_row)

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
        row.setAlignment(group_hanzi, _Qt.AlignmentFlag.AlignTop)

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

                self.dialog._table_panel = self._dialog_data.get("_table_panel")
                if self.dialog._table_panel is None:
                    try:
                        self.dialog._table_panel = self.dialog._table_panel_ctrl.widget
                    except Exception:
                        self.dialog._table_panel = None

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
                    try:
                        logger.debug("Vocab table type=%s", type(self.dialog._table).__name__)
                    except Exception:
                        pass
                    try:
                        from PySide6.QtWidgets import QAbstractItemView
                        if self.dialog._table is not None:
                            try:
                                if hasattr(self.dialog._table, "setColumnCount"):
                                    self.dialog._table.setColumnCount(4)
                                    self.dialog._table.setHorizontalHeaderLabels(
                                        ["Hanzi", "Jyutping", "Meanings", "Categories"]
                                    )
                                    try:
                                        header = self.dialog._table.horizontalHeader()
                                        header.setStretchLastSection(False)
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                            self.dialog._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
                            self.dialog._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
                            try:
                                self.dialog._table.setAlternatingRowColors(False)
                            except Exception:
                                pass
                            try:
                                logger.debug(
                                    "Table debug: altRows=%s selBehavior=%s selMode=%s ss_len=%d",
                                    bool(self.dialog._table.alternatingRowColors()),
                                    int(self.dialog._table.selectionBehavior()),
                                    int(self.dialog._table.selectionMode()),
                                    len(self.dialog._table.styleSheet() or ""),
                                )
                            except Exception:
                                pass
                            try:
                                self.dialog._table.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers)
                            except Exception:
                                self.dialog._table.setEditTriggers(
                                    QAbstractItemView.EditTrigger.EditKeyPressed
                                    | QAbstractItemView.EditTrigger.DoubleClicked
                                    | QAbstractItemView.EditTrigger.SelectedClicked
                                )
                    except Exception:
                        pass

                    # Wire search handler
                    try:
                        fn_search = self._dialog_data.get("_on_search_changed")
                        if callable(fn_search) and self.dialog._search is not None:
                            from ui.vocab_table_searching import wire_search_field
                            wire_search_field(self.dialog._search, fn_search)
                            if self.dialog._table_panel_ctrl is not None:
                                try:
                                    self.dialog._table_panel_ctrl.set_external_search_handler(fn_search)
                                except Exception:
                                    pass
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
                                on_category_changed=self._make_table_category_handler(),
                            )
                            self.dialog._vocab_table_ctrl.populate()
                            try:
                                self.dialog._table.clearSelection()
                            except Exception:
                                pass
                            self._ensure_table_sort_indicator(self.dialog._table)
                            self._defer_table_sort_indicator(self.dialog._vocab_table_ctrl)
                            try:
                                if self.dialog._table_panel_ctrl is not None:
                                    self.dialog._table_panel_ctrl.refresh_snapshot()
                            except Exception:
                                pass
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

        try:
            fn_search = self._dialog_data.get("_on_search_changed")
            if callable(fn_search):
                from ui.vocab_table_searching import wire_search_field
                wire_search_field(self.dialog._search, fn_search)
        except (TypeError, AttributeError, RuntimeError):
            pass

        self.dialog._root.addWidget(self.dialog._search)

        self.dialog._table = QTableWidget(self.dialog)
        self.dialog._table.setColumnCount(4)
        self.dialog._table.setHorizontalHeaderLabels(["Hanzi", "Jyutping", "Meanings", "Categories"])
        self.dialog._table.horizontalHeader().setStretchLastSection(True)
        try:
            header = self.dialog._table.horizontalHeader()
            header.setStretchLastSection(False)
        except Exception:
            pass
        self.dialog._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.dialog._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        try:
            self.dialog._table.setEditTriggers(QAbstractItemView.EditTrigger.AllEditTriggers)
        except Exception:
            try:
                self.dialog._table.setEditTriggers(
                    QAbstractItemView.EditTrigger.EditKeyPressed
                    | QAbstractItemView.EditTrigger.DoubleClicked
                    | QAbstractItemView.EditTrigger.SelectedClicked
                )
            except Exception:
                pass
        try:
            logger.debug("Vocab table type=%s", type(self.dialog._table).__name__)
        except Exception:
            pass
        self.dialog._root.addWidget(self.dialog._table, 1)

        # Initialize table controller
        try:
            from ui.vocabulary_table_controller import VocabularyTableController
            self.dialog._vocab_table_ctrl = VocabularyTableController(
                table=self.dialog._table,
                vocab=self.dialog._vocab,
                categories=self.dialog._cats,
                on_category_changed=self._make_table_category_handler(),
            )
            self.dialog._vocab_table_ctrl.populate()
            self._ensure_table_sort_indicator(self.dialog._table)
            self._defer_table_sort_indicator(self.dialog._vocab_table_ctrl)
        except (TypeError, AttributeError, RuntimeError):
            self.dialog._vocab_table_ctrl = None

    def _ensure_table_sort_indicator(self, table) -> None:
        if table is None:
            return
        try:
            if hasattr(table, "setSortingEnabled"):
                table.setSortingEnabled(True)
            header = getattr(table, "horizontalHeader", None)
            header = header() if callable(header) else None
            if header is not None:
                header.setSortIndicatorShown(True)
                header.setSortIndicator(0, 0)
        except Exception:
            pass

    def _defer_table_sort_indicator(self, ctrl) -> None:
        if ctrl is None or not hasattr(ctrl, "ensure_sort_indicator"):
            return
        try:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, ctrl.ensure_sort_indicator)
            QTimer.singleShot(50, ctrl.ensure_sort_indicator)
            QTimer.singleShot(150, ctrl.ensure_sort_indicator)
        except Exception:
            pass

    def _make_table_category_handler(self):
        dlg = self.dialog

        def _handler(hanzi: str, categories: list[str]) -> None:
            hz = str(hanzi or "").strip()
            if not hz:
                return

            new_set = {str(c).strip() for c in categories if str(c).strip()}

            cats_map = dlg.__dict__.get("_cats")
            if not isinstance(cats_map, dict):
                return

            repo = dlg.__dict__.get("_cat_repo")
            if repo is None and dlg.__dict__.get("_cat_commit_svc") is not None:
                repo = dlg.__dict__.get("_cat_repo")

            # Remove from categories not in new_set
            for cat, members in list(cats_map.items()):
                if not isinstance(members, list):
                    continue
                if hz in members and cat not in new_set:
                    if repo is not None and hasattr(repo, "remove_hanzi"):
                        try:
                            repo.remove_hanzi(cat, hz)
                        except Exception:
                            pass
                    else:
                        try:
                            members[:] = [x for x in members if x != hz]
                        except Exception:
                            pass

            # Add to new categories
            for cat in sorted(new_set, key=lambda s: s.lower()):
                if repo is not None and hasattr(repo, "ensure_category"):
                    try:
                        repo.ensure_category(cat)
                    except Exception:
                        pass
                if cat not in cats_map:
                    cats_map[cat] = []
                members = cats_map.get(cat)
                if isinstance(members, list) and hz not in members:
                    members.append(hz)

            try:
                from services.vocab_loader import update_entry_categories, persist_categories_block
                update_entry_categories(hanzi=hz, categories=sorted(new_set, key=lambda s: s.lower()))
                persist_categories_block(cats_map)
            except Exception:
                pass

            try:
                from ui.category_manager_vocab_categories import CategoryManagerVocabCategories
                CategoryManagerVocabCategories.refresh_category_dropdown_from_cats(dlg)
            except Exception:
                pass

        return _handler
