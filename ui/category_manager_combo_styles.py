"""ComboBox styles and behaviors used by CategoryManager."""

from PySide6.QtWidgets import QProxyStyle, QStyle


class HanziComboBoxProxyStyle(QProxyStyle):
    """
    Proxy style to prevent macOS combo edit-field rect from collapsing vertically.

    Some Qt/macOS styles compute SC_ComboBoxEditField with a very small height,
    which forces the internal line edit / paint rect to be tiny, causing clipped CJK glyphs.
    """

    def subControlRect(self, control, option, subControl, widget=None):  # noqa: N802
        rect = super().subControlRect(control, option, subControl, widget)
        try:
            if (
                    control == QStyle.ComplexControl.CC_ComboBox
                    and subControl == QStyle.SubControl.SC_ComboBoxEditField
            ):
                full = option.rect
                inset = 2  # keep a little breathing room for the border
                rect.setY(int(full.y() + inset))
                rect.setHeight(int(max(0, full.height() - (inset * 2))))
        except (TypeError, AttributeError, ValueError, RuntimeError):
            pass
        return rect
