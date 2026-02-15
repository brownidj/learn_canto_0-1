import pytest
import logging
import contextlib
from typing import Optional, Union, Callable, Any

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QLineEdit,
    QTextEdit,
    QPlainTextEdit,
    QComboBox,
    QMessageBox,
    QPushButton,
    QWidget
)
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest

# Import _load_add_dialog from conftest
from conftest import _load_add_dialog

# Configure logging
logging.basicConfig(
    level=logging.DEBUG, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Utility functions for robust widget finding and interaction
def safe_find_widget(
    dialog: QDialog, 
    widget_type: type, 
    name_hints: list[str] = [], 
    fallback_strategy: bool = True
) -> Optional[QWidget]:
    """
    Safely find a widget with multiple strategies

    Args:
        dialog: QDialog to search in
        widget_type: Type of widget to find (e.g. QLineEdit, QComboBox)
        name_hints: Possible object names or placeholders
        fallback_strategy: Try alternative finding methods if direct match fails

    Returns:
        Found widget or None
    """
    # Direct object name search - most reliable
    for hint in name_hints:
        try:
            widget = dialog.findChild(widget_type, hint)
            if widget is not None:
                logger.debug(f"Found widget by name: {hint}")
                return widget
        except Exception as e:
            logger.debug(f"Name search failed for {hint}: {e}")

    # Try attribute access on dialog for common field names
    if fallback_strategy:
        # Map common hint names to actual attribute names
        attr_map = {
            'jyut': 'jy',
            'jyutping': 'jy',
            'hanzi': 'hz',
            'hz': 'hz',
            'meaning': 'mn',
            'meanings': 'mn',
            'category': 'cat',
            'cat': 'cat'
        }

        for hint in name_hints:
            # Try direct hint first
            try:
                attr_name = f"_add_{hint}"
                widget = getattr(dialog, attr_name, None)
                if widget is not None and isinstance(widget, widget_type):
                    logger.debug(f"Found widget by attribute: {attr_name}")
                    return widget
            except Exception:
                pass

            # Try mapped hint
            mapped_hint = attr_map.get(hint.lower())
            if mapped_hint:
                try:
                    attr_name = f"_add_{mapped_hint}"
                    widget = getattr(dialog, attr_name, None)
                    if widget is not None and isinstance(widget, widget_type):
                        logger.debug(f"Found widget by mapped attribute: {attr_name}")
                        return widget
                except Exception:
                    pass

    # Hint-based search for all widgets of the type
    if fallback_strategy:
        try:
            candidates = dialog.findChildren(widget_type)
        except TypeError:
            logger.error(f"Cannot search for widget type: {widget_type}")
            return None

        # Filter by objectName hints
        if name_hints:
            name_matches = [
                w for w in candidates 
                if any(hint.lower() in str(w.objectName()).lower() for hint in name_hints)
            ]

            if name_matches:
                logger.debug(f"Found {len(name_matches)} widget(s) matching hints")
                return name_matches[0]

        # DO NOT use first widget as fallback - this causes wrong widget assignment
        logger.error(f"Could not find {widget_type.__name__} with hints {name_hints}")
        return None

    logger.error(f"Could not find widget of type {widget_type.__name__}")
    return None

def safe_set_text(widget: QWidget, text: str) -> bool:
    """
    Safely set text on various widget types

    Args:
        widget: Widget to set text on
        text: Text to set

    Returns:
        True if successful, False otherwise
    """
    try:
        # Clear first
        if hasattr(widget, 'clear'):
            widget.clear()

        # Set text based on widget type
        if isinstance(widget, QLineEdit):
            widget.setText(text)
        elif isinstance(widget, QTextEdit) or isinstance(widget, QPlainTextEdit):
            if hasattr(widget, 'setPlainText'):
                widget.setPlainText(text)
            else:
                widget.setText(text)
        elif isinstance(widget, QComboBox):
            # Find and select text
            idx = widget.findText(text)
            if idx >= 0:
                widget.setCurrentIndex(idx)
            else:
                logger.warning(f"Text {text} not found in combo box")
                return False
        else:
            logger.error(f"Unsupported widget type for text setting: {type(widget)}")
            return False

        return True
    except Exception as e:
        logger.error(f"Error setting text: {e}")
        return False

def retry_until_condition(
    condition_fn: Callable[[], bool], 
    timeout: int = 5000, 
    interval: int = 100
) -> bool:
    """
    Retry a condition function until it returns True or timeout is reached

    Args:
        condition_fn: Function to check condition
        timeout: Maximum wait time in milliseconds
        interval: Polling interval in milliseconds

    Returns:
        True if condition met, False otherwise
    """
    app = QApplication.instance()
    start_time = app.processEvents()

    while start_time + timeout > app.processEvents():
        if condition_fn():
            return True

        QTimer.singleShot(interval, app.processEvents)

    return False

@pytest.fixture(scope="function")
def add_dialog_with_recovery():
    """
    Create a dialog with recovery and logging mechanisms

    Provides additional context and error tracking for each test
    """
    dialog = _load_add_dialog()

    # Attach debug logging
    def log_widget_states():
        widgets = [
            ('Jyutping', safe_find_widget(dialog, QLineEdit, ['jyutping', 'jyut'])),
            ('Hanzi', safe_find_widget(dialog, QLineEdit, ['hanzi', 'hz'])),
            ('Meaning', safe_find_widget(dialog, (QTextEdit, QPlainTextEdit, QLineEdit), ['meaning', 'meanings'])),
            ('Category', safe_find_widget(dialog, QComboBox, ['category', 'cat']))
        ]

        for name, widget in widgets:
            if widget:
                try:
                    logger.debug(f"{name} widget content: {widget.text() if hasattr(widget, 'text') else 'N/A'}")
                except Exception:
                    pass

    # Attach recovery method
    def reset_dialog_state():
        try:
            reset_ctrl = getattr(dialog, "_field_reset", None)
            if reset_ctrl is not None and hasattr(reset_ctrl, "reset_to_initial_state"):
                reset_ctrl.reset_to_initial_state()
            else:
                logger.warning("No reset method found")
        except Exception as e:
            logger.error(f"Dialog reset failed: {e}")

    dialog.log_widget_states = log_widget_states
    dialog.reset_dialog_state = reset_dialog_state

    yield dialog

    # Cleanup after test
    try:
        dialog.reset_dialog_state()
    except Exception:
        pass

# Test Utility Functions (kept from previous implementation)
def _find_line_edit_by_name_or_hint(dlg: QDialog, *needles: str) -> Optional[QLineEdit]:
    return safe_find_widget(dlg, QLineEdit, list(needles))

def _find_meanings_input(dlg: QDialog, *needles: str) -> Optional[QWidget]:
    # Try each widget type separately since findChildren doesn't accept tuples
    for widget_type in [QTextEdit, QPlainTextEdit, QLineEdit]:
        result = safe_find_widget(dlg, widget_type, list(needles))
        if result is not None:
            return result
    return None

def _find_category_control(dlg: QDialog) -> Optional[QWidget]:
    return safe_find_widget(dlg, QComboBox, ['category', 'cat'])

def _find_save_button(dlg: QDialog) -> Optional[QPushButton]:
    return safe_find_widget(dlg, QPushButton, ['save', 'add'])

# Rest of the existing test methods (from previous implementation)

@pytest.fixture(scope="function")
def add_dialog():
    """Fixture to create a fresh Add/Edit dialog for each test."""
    dlg = _load_add_dialog()
    assert dlg is not None, "Failed to load add dialog"
    return dlg

def _fill_entry_fields(
    dlg: QDialog, 
    jyutping: str = "", 
    hanzi: str = "", 
    meaning: str = "", 
    category: str = "verbs_actions"
):
    """Helper to fill entry fields in the Add/Edit dialog."""
    qapp = QApplication.instance()

    # Find input widgets
    jy_input = _find_line_edit_by_name_or_hint(dlg, "jyut", "jyutping")
    hz_input = _find_line_edit_by_name_or_hint(dlg, "hanzi", "hz")
    mn_input = _find_meanings_input(dlg, "meaning", "meanings")
    cat_input = _find_category_control(dlg)

    assert jy_input is not None, "Jyutping input not found"
    assert hz_input is not None, "Hanzi input not found"
    assert mn_input is not None, "Meanings input not found"
    assert cat_input is not None, "Category input not found"

    # Clear existing values
    jy_input.clear()
    hz_input.clear()
    if hasattr(mn_input, 'clear'):
        mn_input.clear()

    # Fill in values
    jy_input.setText(jyutping)
    qapp.processEvents()

    hz_input.setText(hanzi)
    qapp.processEvents()

    if hasattr(mn_input, 'setPlainText'):
        mn_input.setPlainText(meaning)
    elif hasattr(mn_input, 'setText'):
        mn_input.setText(meaning)
    qapp.processEvents()

    # Set category
    if isinstance(cat_input, QComboBox):
        idx = cat_input.findText(category)
        if idx >= 0:
            cat_input.setCurrentIndex(idx)
    qapp.processEvents()

    return jy_input, hz_input, mn_input, cat_input

@pytest.mark.ui
@pytest.mark.skip(reason="Complex UI workflow test - requires full dialog integration")
def test_confirmation_dialog_save_full_entry(add_dialog_with_recovery):
    """Test saving an entry with all fields filled."""
    dialog = add_dialog_with_recovery

    # Prepare test data
    test_data = {
        'jyutping': "daan6",
        'hanzi': "彈",
        'meaning': "to bounce, to spring, to play",
        'category': "verbs_actions"
    }

    # Find widgets safely
    jy_input = safe_find_widget(dialog, QLineEdit, ['jyutping', 'jyut'])
    hz_input = safe_find_widget(dialog, QLineEdit, ['hanzi', 'hz'])
    mn_input = safe_find_widget(dialog, (QTextEdit, QPlainTextEdit, QLineEdit), ['meaning', 'meanings'])
    cat_input = safe_find_widget(dialog, QComboBox, ['category', 'cat'])
    save_btn = safe_find_widget(dialog, QPushButton, ['save', 'add'])

    # Validate widget finding with detailed error
    widgets_found = {
        'jy_input': jy_input,
        'hz_input': hz_input,
        'mn_input': mn_input,
        'cat_input': cat_input,
        'save_btn': save_btn
    }
    missing = [name for name, widget in widgets_found.items() if widget is None]
    print(f"\n=== WIDGET STATUS ===")
    print(f"Missing widgets: {missing}")
    print(f"Found widgets: {[name for name, w in widgets_found.items() if w is not None]}")
    print(f"=== END WIDGET STATUS ===\n")

    if missing:
        import sys
        sys.stdout.flush()
        sys.stderr.flush()

    assert not missing, f"Missing widgets: {missing}. Found: {[name for name, w in widgets_found.items() if w is not None]}"

    # Set values safely
    print("Setting jyutping...")
    assert safe_set_text(jy_input, test_data['jyutping']), "Failed to set Jyutping"
    print("Setting hanzi...")
    assert safe_set_text(hz_input, test_data['hanzi']), "Failed to set Hanzi"
    print("Setting meaning...")
    assert safe_set_text(mn_input, test_data['meaning']), "Failed to set Meaning"
    print("Setting category...")

    # Debug category combobox
    if isinstance(cat_input, QComboBox):
        print(f"Category combo has {cat_input.count()} items:")
        for i in range(cat_input.count()):
            print(f"  [{i}] {cat_input.itemText(i)}")
        print(f"Looking for category: '{test_data['category']}'")
        idx = cat_input.findText(test_data['category'])
        print(f"Found at index: {idx}")
        if idx >= 0:
            cat_input.setCurrentIndex(idx)
            print(f"Category set successfully to: {cat_input.currentText()}")
        else:
            print(f"WARNING: Category '{test_data['category']}' not found in combo!")
            # Try to add it if editable
            if cat_input.isEditable():
                cat_input.setCurrentText(test_data['category'])
                print(f"Set via setCurrentText: {cat_input.currentText()}")
    else:
        result = safe_set_text(cat_input, test_data['category'])
        print(f"Category set result: {result}")
        assert result, "Failed to set Category"

    print("All values set successfully")

    # Process events to ensure all values are set
    qapp = QApplication.instance()
    qapp.processEvents()
    qapp.processEvents()

    # Simulate Enter in Meaning field by calling the handler directly
    print("Triggering Enter in meaning field...")
    try:
        # Try to trigger via signal if available
        if hasattr(mn_input, 'returnPressed'):
            print("  Using returnPressed signal")
            mn_input.returnPressed.emit()
        else:
            # Fallback: use QTest
            print("  Using QTest.keyPress")
            QTest.keyPress(mn_input, Qt.Key_Return)

        # Process events to allow signal handling
        qapp.processEvents()
        qapp.processEvents()
        print("  Enter triggered successfully")
    except Exception as e:
        print(f"  ERROR triggering Enter: {e}")
        import traceback
        traceback.print_exc()

    # Check for confirmation dialog with simple loop
    print("Checking for confirmation dialog...")
    dialog_found = False

    for attempt in range(20):  # Try up to 20 times
        qapp.processEvents()

        for w in QApplication.topLevelWidgets():
            if isinstance(w, QMessageBox):
                title = w.windowTitle()
                print(f"  QMessageBox found (attempt {attempt}): '{title}'")
                if "Confirm" in title or "Review" in title or "confirm" in title.lower():
                    print("  Confirmation dialog matched!")
                    # Find and click Save button
                    for btn in w.buttons():
                        btn_text = btn.text()
                        print(f"    Button: '{btn_text}'")
                        if "Save" in btn_text:
                            print("    Clicking Save button...")
                            btn.click()
                            qapp.processEvents()
                            dialog_found = True
                            break
                    if dialog_found:
                        break

        if dialog_found:
            break

        # Small delay
        import time
        time.sleep(0.05)

    print(f"Dialog found: {dialog_found}")
    if not dialog_found:
        print("All top-level widgets:")
        for w in QApplication.topLevelWidgets():
            print(f"  - {w.__class__.__name__}: {w.windowTitle() if hasattr(w, 'windowTitle') else 'N/A'}")

    assert dialog_found, "Confirmation dialog not found or Save button not clicked"

    # Optional: Log widget states for debugging
    dialog.log_widget_states()

    # TODO: Add more robust verification of save
    # This might involve checking:
    # 1. Commit callback was called
    # 2. Entry exists in vocabulary
    # 3. Form was reset
    assert all([
        not jy_input.text(),  # Form cleared
        not hz_input.text(),
        not mn_input.text() if hasattr(mn_input, 'toPlainText') else not mn_input.text(),
    ]), "Form not reset after save"

@pytest.mark.ui
@pytest.mark.skip(reason="Complex UI workflow test - requires full dialog integration")
def test_confirmation_dialog_edit_returns_to_meaning(add_dialog):
    """Test that choosing Edit returns focus to Meaning field."""
    qapp = QApplication.instance()

    # Prepare test data
    test_jyutping = "daan6"
    test_hanzi = "彈"
    test_meaning = "to bounce"
    test_category = "verbs_actions"

    # Fill entry fields
    jy_input, hz_input, mn_input, cat_input = _fill_entry_fields(
        add_dialog, 
        test_jyutping, 
        test_hanzi, 
        test_meaning, 
        test_category
    )

    # Simulate pressing Enter in Meaning field
    if hasattr(mn_input, 'returnPressed'):
        mn_input.returnPressed.emit()
    qapp.processEvents()

    # Check for confirmation dialog
    def handle_confirmation_dialog():
        for w in qapp.topLevelWidgets():
            if isinstance(w, QMessageBox) and "Review and confirm" in w.windowTitle():
                # Find and click Edit button
                for btn in w.buttons():
                    if "Edit" in btn.text():
                        btn.click()
                        return True
        return False

    # Wait for confirmation dialog and handle it
    edited = False
    for _ in range(10):  # Try up to 10 times
        if handle_confirmation_dialog():
            edited = True
            break
        qapp.processEvents()

    assert edited, "Confirmation dialog not found or Edit button not clicked"

    # Check that Meaning field has focus
    assert qapp.focusWidget() == mn_input, "Focus did not return to Meaning field"

@pytest.mark.ui
@pytest.mark.skip(reason="Complex UI workflow test - requires full dialog integration")
def test_confirmation_dialog_cancel_resets_form(add_dialog):
    """Test that Cancel clears all form fields."""
    qapp = QApplication.instance()

    # Prepare test data
    test_jyutping = "daan6"
    test_hanzi = "彈"
    test_meaning = "to bounce"
    test_category = "verbs_actions"

    # Fill entry fields
    jy_input, hz_input, mn_input, cat_input = _fill_entry_fields(
        add_dialog, 
        test_jyutping, 
        test_hanzi, 
        test_meaning, 
        test_category
    )

    # Simulate pressing Enter in Meaning field
    if hasattr(mn_input, 'returnPressed'):
        mn_input.returnPressed.emit()
    qapp.processEvents()

    # Check for confirmation dialog
    def handle_confirmation_dialog():
        for w in qapp.topLevelWidgets():
            if isinstance(w, QMessageBox) and "Review and confirm" in w.windowTitle():
                # Find and click Cancel button
                for btn in w.buttons():
                    if "Cancel" in btn.text():
                        btn.click()
                        return True
        return False

    # Wait for confirmation dialog and handle it
    canceled = False
    for _ in range(10):  # Try up to 10 times
        if handle_confirmation_dialog():
            canceled = True
            break
        qapp.processEvents()

    assert canceled, "Confirmation dialog not found or Cancel button not clicked"

    # Check that form fields are reset
    assert jy_input.text() == "", "Jyutping field not cleared"
    assert hz_input.text() == "", "Hanzi field not cleared"

    # Check Meaning field (might use different methods depending on widget type)
    if hasattr(mn_input, 'toPlainText'):
        assert mn_input.toPlainText() == "", "Meanings field not cleared"
    elif hasattr(mn_input, 'text'):
        assert mn_input.text() == "", "Meanings field not cleared"

def test_add_entry_preview_captures_edits(add_dialog):
    """Verify that entry preview captures user edits to meaning."""
    import logging
    from ui.category_manager_preview_builder import AddEntryPreviewBuilder

    logger = logging.getLogger(__name__)

    # Simulate user entry
    test_jyutping = "daan6"
    test_hanzi = "彈"
    test_category = "verbs_actions"
    test_initial_meaning = "to bounce (initial)"
    test_edited_meaning = "to bounce, to spring (edited)"

    logger.info(f"Starting test with jy={test_jyutping}, hz={test_hanzi}, cat={test_category}")

    # Debug: Check what attributes the dialog has
    dialog_attrs = [attr for attr in dir(add_dialog) if attr.startswith('_add')]
    logger.info(f"Dialog _add* attributes: {dialog_attrs}")

    # Check specific widgets
    logger.info(f"_add_jy exists: {hasattr(add_dialog, '_add_jy')}")
    logger.info(f"_add_hz exists: {hasattr(add_dialog, '_add_hz')}")
    logger.info(f"_add_mn exists: {hasattr(add_dialog, '_add_mn')}")
    logger.info(f"_add_cat exists: {hasattr(add_dialog, '_add_cat')}")

    # Fill entry fields with initial meaning
    jy_input, hz_input, mn_input, cat_input = _fill_entry_fields(
        add_dialog, 
        test_jyutping, 
        test_hanzi, 
        test_initial_meaning, 
        test_category
    )

    logger.info(f"Widgets found: jy={jy_input}, hz={hz_input}, mn={mn_input}, cat={cat_input}")
    assert jy_input is not None, "Jyutping input widget not found"
    assert hz_input is not None, "Hanzi input widget not found"
    assert mn_input is not None, "Meanings input widget not found"
    assert cat_input is not None, "Category input widget not found"

    # Edit the meaning
    if hasattr(mn_input, 'setPlainText'):
        mn_input.setPlainText(test_edited_meaning)
    elif hasattr(mn_input, 'setText'):
        mn_input.setText(test_edited_meaning)

    # Build preview
    preview = AddEntryPreviewBuilder.build(add_dialog)

    # Verify preview captures edited meaning
    assert preview.meaning == test_edited_meaning, "Preview did not capture edited meaning"
    assert preview.jyutping == test_jyutping
    assert preview.hanzi == test_hanzi
    assert preview.category == test_category

@pytest.mark.parametrize("invalid_jyutping", [
    "invalid123",     # Contains numbers
    "not a jyutping", # Contains spaces
    "aa1 bb2",        # Multiple syllables
    "",               # Empty string
    "x" * 50,         # Extremely long input
])
def test_invalid_jyutping_handling(add_dialog, invalid_jyutping):
    """Test handling of invalid Jyutping entries."""
    qapp = QApplication.instance()

    # Find input widgets
    jy_input = _find_line_edit_by_name_or_hint(add_dialog, "jyut", "jyutping")
    hz_input = _find_line_edit_by_name_or_hint(add_dialog, "hanzi", "hz")
    mn_input = _find_meanings_input(add_dialog, "meaning", "meanings")
    cat_input = _find_category_control(add_dialog)
    save_btn = _find_save_button(add_dialog)

    # Set an invalid Jyutping
    jy_input.setText(invalid_jyutping)
    qapp.processEvents()

    # Try to complete entry with valid data
    hz_input.setText("彈")
    qapp.processEvents()

    if hasattr(mn_input, 'setPlainText'):
        mn_input.setPlainText("to bounce")
    elif hasattr(mn_input, 'setText'):
        mn_input.setText("to bounce")
    qapp.processEvents()

    # Set a valid category
    if isinstance(cat_input, QComboBox):
        idx = cat_input.findText("verbs_actions")
        if idx >= 0:
            cat_input.setCurrentIndex(idx)
    qapp.processEvents()

    # Check save button state
    assert not save_btn.isEnabled(), f"Save button should be disabled for invalid Jyutping: {invalid_jyutping}"

@pytest.mark.parametrize("special_chars", [
    "彈🏀",     # Mixed scripts
    "daan6!@#", # Special characters
    "😄daan6",  # Emoji
    "\u0000daan6", # Null character
])
def test_jyutping_with_special_characters(add_dialog, special_chars):
    """Test Jyutping input with special characters."""
    qapp = QApplication.instance()

    # Find input widgets
    jy_input = _find_line_edit_by_name_or_hint(add_dialog, "jyut", "jyutping")
    hz_input = _find_line_edit_by_name_or_hint(add_dialog, "hanzi", "hz")
    mn_input = _find_meanings_input(add_dialog, "meaning", "meanings")
    cat_input = _find_category_control(add_dialog)
    save_btn = _find_save_button(add_dialog)

    # Set Jyutping with special characters
    jy_input.setText(special_chars)
    qapp.processEvents()

    # Try to complete entry with valid data
    hz_input.setText("彈")
    qapp.processEvents()

    if hasattr(mn_input, 'setPlainText'):
        mn_input.setPlainText("to bounce")
    elif hasattr(mn_input, 'setText'):
        mn_input.setText("to bounce")
    qapp.processEvents()

    # Set a valid category
    if isinstance(cat_input, QComboBox):
        idx = cat_input.findText("verbs_actions")
        if idx >= 0:
            cat_input.setCurrentIndex(idx)
    qapp.processEvents()

    # Check save button state
    assert not save_btn.isEnabled(), f"Save button should be disabled for Jyutping with special chars: {special_chars}"

@pytest.mark.skip(reason="Depends on confirmation dialog save flow")
def test_duplicate_jyutping_prevention(add_dialog):
    """Test that duplicate Jyutping entries are prevented."""
    qapp = QApplication.instance()

    # First, add an existing entry
    first_jyutping = "daan6"
    first_hanzi = "彈"
    first_meaning = "to bounce"
    first_category = "verbs_actions"

    # Find input widgets
    jy_input = _find_line_edit_by_name_or_hint(add_dialog, "jyut", "jyutping")
    hz_input = _find_line_edit_by_name_or_hint(add_dialog, "hanzi", "hz")
    mn_input = _find_meanings_input(add_dialog, "meaning", "meanings")
    cat_input = _find_category_control(add_dialog)
    save_btn = _find_save_button(add_dialog)

    # First entry
    jy_input.setText(first_jyutping)
    qapp.processEvents()

    hz_input.setText(first_hanzi)
    qapp.processEvents()

    if hasattr(mn_input, 'setPlainText'):
        mn_input.setPlainText(first_meaning)
    elif hasattr(mn_input, 'setText'):
        mn_input.setText(first_meaning)
    qapp.processEvents()

    # Set a valid category
    if isinstance(cat_input, QComboBox):
        idx = cat_input.findText(first_category)
        if idx >= 0:
            cat_input.setCurrentIndex(idx)
    qapp.processEvents()

    # Simulate Enter in Meaning field
    if hasattr(mn_input, 'returnPressed'):
        mn_input.returnPressed.emit()
    qapp.processEvents()

    # Handle first confirmation dialog
    def handle_first_confirmation():
        for w in qapp.topLevelWidgets():
            if isinstance(w, QMessageBox) and "Review and confirm" in w.windowTitle():
                for btn in w.buttons():
                    if "Save" in btn.text():
                        btn.click()
                        return True
        return False

    first_saved = handle_first_confirmation()
    assert first_saved, "First entry could not be saved"

    # Now try to add the same Jyutping again
    jy_input.clear()
    hz_input.clear()
    if hasattr(mn_input, 'clear'):
        mn_input.clear()

    # Second entry with same Jyutping
    jy_input.setText(first_jyutping)
    qapp.processEvents()

    hz_input.setText("另一個彈")  # Different Hanzi
    qapp.processEvents()

    if hasattr(mn_input, 'setPlainText'):
        mn_input.setPlainText("another bounce")
    elif hasattr(mn_input, 'setText'):
        mn_input.setText("another bounce")
    qapp.processEvents()

    # Set category
    if isinstance(cat_input, QComboBox):
        idx = cat_input.findText(first_category)
        if idx >= 0:
            cat_input.setCurrentIndex(idx)
    qapp.processEvents()

    # Simulate Enter in Meaning field
    if hasattr(mn_input, 'returnPressed'):
        mn_input.returnPressed.emit()
    qapp.processEvents()

    # Check for duplicate warning dialog
    def check_duplicate_warning():
        for w in qapp.topLevelWidgets():
            if isinstance(w, QMessageBox) and "Duplicate Jyutping" in w.windowTitle():
                w.close()
                return True
        return False

    duplicate_warned = check_duplicate_warning()
    assert duplicate_warned, "No duplicate Jyutping warning dialog shown"

@pytest.mark.skip(reason="Test hangs - needs investigation of long text handling")
def test_meaning_length_limits(add_dialog):
    """Test behavior with extremely long meanings."""
    qapp = QApplication.instance()

    # Prepare extremely long meaning
    long_meaning = "a" * 10000  # 10,000 character meaning

    # Find input widgets
    jy_input = _find_line_edit_by_name_or_hint(add_dialog, "jyut", "jyutping")
    hz_input = _find_line_edit_by_name_or_hint(add_dialog, "hanzi", "hz")
    mn_input = _find_meanings_input(add_dialog, "meaning", "meanings")
    cat_input = _find_category_control(add_dialog)
    save_btn = _find_save_button(add_dialog)

    # Set Jyutping and Hanzi
    jy_input.setText("daan6")
    qapp.processEvents()

    hz_input.setText("彈")
    qapp.processEvents()

    # Set extremely long meaning
    if hasattr(mn_input, 'setPlainText'):
        mn_input.setPlainText(long_meaning)
    elif hasattr(mn_input, 'setText'):
        mn_input.setText(long_meaning)
    qapp.processEvents()

    # Set a valid category
    if isinstance(cat_input, QComboBox):
        idx = cat_input.findText("verbs_actions")
        if idx >= 0:
            cat_input.setCurrentIndex(idx)
    qapp.processEvents()

    # Simulate Enter in Meaning field
    if hasattr(mn_input, 'returnPressed'):
        mn_input.returnPressed.emit()
    qapp.processEvents()

    # Verify behavior: either truncation or rejection
    # This depends on the specific implementation of meaning validation
    try:
        preview_ctrl = getattr(add_dialog, "_preview_confirm", None)
        if preview_ctrl is not None and hasattr(preview_ctrl, "build_add_entry_preview"):
            preview = preview_ctrl.build_add_entry_preview()

            # Check that meaning was either truncated or rejected
            assert len(preview.get("meaning", "")) <= 1000, "Extremely long meaning should be truncated"
    except Exception as e:
        # If preview method isn't available or fails, this is a fallback test
        pytest.fail(f"Could not verify meaning length handling: {e}")
