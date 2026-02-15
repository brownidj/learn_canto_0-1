"""
Hanzi label font auto-sizing controller.

This module handles dynamic font sizing for the Hanzi display label in the main window,
ensuring text fits within available space while maintaining readability.
"""
import logging
import re
from typing import Optional

from PySide6.QtCore import QObject, QEvent
from PySide6.QtWidgets import QLabel
from PySide6.QtGui import QFontMetrics

logger = logging.getLogger(__name__)


def parse_base_point_size_from_stylesheet(stylesheet: str) -> int:
    """Extract the base font-size from a stylesheet.

    Args:
        stylesheet: CSS stylesheet string

    Returns:
        Point size as integer, or 96 if not found
    """
    try:
        match = re.search(r'font-size\s*:\s*(\d+)\s*pt', stylesheet, re.IGNORECASE)
        if match:
            return int(match.group(1))
    except Exception:
        pass
    return 96


class HanziFontController:
    """Controls automatic font sizing for the Hanzi display label.

    This controller ensures that Hanzi text always fits within the label's
    available space by dynamically adjusting the font size based on:
    - Text length (both Hanzi and Jyutping)
    - Available label width/height
    - Device pixel ratio for HiDPI displays
    """

    def __init__(self, label: QLabel, window: QObject):
        """Initialize the font controller.

        Args:
            label: The QLabel widget displaying Hanzi text
            window: Parent window object for storing state
        """
        self.label = label
        self.window = window

        # Store baseline stylesheet
        self.window._hanzi_base_stylesheet = label.styleSheet() or ""
        self.window._hanzi_avail_w0 = None

        # Install event filter for resize handling
        self._sizer = _HanziResizer(self)
        label.installEventFilter(self._sizer)
        self.window._hanzi_sizer = self._sizer

    def capture_baseline(self):
        """Capture the initial available width after first layout pass."""
        label = self.label

        try:
            w_total = int(label.width())
        except Exception:
            w_total = -1
        try:
            w_contents = int(label.contentsRect().width())
        except Exception:
            w_contents = w_total
        try:
            win_w = int(self.window.width())
        except Exception:
            win_w = -1

        logger.debug("Initial sizes: window_w=%d labelHanzi_w=%d contentsRect_w=%d", 
                    win_w, w_total, w_contents)

        w0 = max(0, w_contents if w_contents is not None else w_total)
        if w0 > 0 and self.window._hanzi_avail_w0 is None:
            self.window._hanzi_avail_w0 = w0
            logger.debug("Hanzi baseline avail_w0 set to %d", w0)

    def update_font_now(self, jyut_text: str = ""):
        """Update the font size to fit current text.

        Args:
            jyut_text: Optional Jyutping text for width calculation
        """
        if not self.label:
            return

        hanzi_text = self.label.text()
        base_pt = self._parse_base_point_size()
        self._fit_font_to_label(hanzi_text, jyut_text, base_pt)

    def _parse_base_point_size(self) -> int:
        """Parse base point size from label's stylesheet."""
        try:
            ss = self.label.styleSheet() or ""
            return parse_base_point_size_from_stylesheet(ss)
        except Exception:
            return 96

    def _apply_pt_stylesheet(self, pt: int):
        """Apply font-size via stylesheet."""
        try:
            base = getattr(self.window, "_hanzi_base_stylesheet", self.label.styleSheet() or "")
            # Remove all font-size declarations
            cleaned = re.sub(r"font-size\s*:\s*\d+\s*pt\s*;?", "", base, flags=re.IGNORECASE)
            # Ensure trailing semicolon
            if cleaned and not cleaned.strip().endswith(";"):
                cleaned = cleaned.strip() + ";"
            self.label.setStyleSheet(f"{cleaned} font-size: {int(pt)}pt;")
        except Exception:
            # Fallback to QFont if stylesheet fails
            f = self.label.font()
            f.setPointSize(int(pt))
            self.label.setFont(f)

    def _measure_text_px(self, font, text: str) -> tuple[int, int]:
        """Measure text dimensions in pixels."""
        fm = QFontMetrics(font)
        try:
            rect = fm.tightBoundingRect(text)
            w_px = rect.width()
            h_px = rect.height()
        except Exception:
            rect = fm.boundingRect(text)
            w_px = rect.width()
            h_px = rect.height()
        return w_px, h_px

    def _compute_avail_width(self) -> int:
        """Compute available width for text, respecting baseline."""
        label = self.label

        try:
            avail = max(0, label.contentsRect().width())
        except Exception:
            avail = max(0, label.width())

        # Don't exceed baseline (prevents right-edge jump)
        b = getattr(self.window, "_hanzi_avail_w0", None)
        if isinstance(b, int) and b > 0:
            avail = min(avail, b)

        # Safety margin for glyph overhang, scaled for HiDPI
        try:
            dpr = max(1.0, float(label.devicePixelRatioF()))
        except Exception:
            dpr = 1.0
        safety = int(12 * dpr)

        return max(0, avail - safety)

    def _fit_font_to_label(self, hanzi_text: str, jyut_text: str, base_pt: int):
        """Fit font size to available space using binary search."""
        ht = hanzi_text or ""
        jt = jyut_text or ""

        # If BOTH <= 4 chars, honor stylesheet/base size
        if len(ht) <= 4 and len(jt) <= 4:
            self._apply_pt_stylesheet(base_pt)
            return

        avail_w = self._compute_avail_width()
        max_h = self.label.maximumHeight() if self.label.maximumHeight() > 0 else 10_000

        if avail_w < 10:
            # Retry after layout
            from ui.qt_timers import call_later
            call_later(lambda: self._fit_font_to_label(ht, jt, base_pt), delay_ms=0)
            return

        # Use Hanzi for sizing (conservative)
        display_txt = ht

        # Binary search for best point size
        f = self.label.font()
        lo, hi = 6, 200
        best = lo

        while lo <= hi:
            mid = (lo + hi) // 2
            f.setPointSize(mid)
            w_px, h_px = self._measure_text_px(f, display_txt)
            logger.debug("fit try: sz=%d text_px=%dx%d avail_w=%d max_h=%d", 
                        mid, w_px, h_px, avail_w, max_h)
            if w_px <= avail_w and h_px <= max_h:
                best = mid
                lo = mid + 1
            else:
                hi = mid - 1

        final_pt = max(6, best - 2)
        self._apply_pt_stylesheet(final_pt)

        # Measure with final font
        f.setPointSize(final_pt)
        fw, fh = self._measure_text_px(f, display_txt)
        logger.debug("fit final: applied_pt=%d (best=%d) text_px=%dx%d avail_w=%d", 
                    final_pt, best, fw, fh, avail_w)

        # Post-fit safeguards
        for _ in range(3):
            if fw <= avail_w and fh <= max_h:
                break
            final_pt = max(6, final_pt - 2)
            self._apply_pt_stylesheet(final_pt)
            f.setPointSize(final_pt)
            fw, fh = self._measure_text_px(f, display_txt)

        # Iterative adjustment for glyph overhangs
        safety_px = 2
        max_iters = 16
        iters = 0

        while iters < max_iters:
            try:
                curr_avail_w = self._compute_avail_width()
            except Exception:
                curr_avail_w = avail_w

            if fw <= max(0, curr_avail_w - safety_px) and fh <= max_h:
                break

            final_pt = max(6, final_pt - 1)
            self._apply_pt_stylesheet(final_pt)
            f.setPointSize(final_pt)
            fw, fh = self._measure_text_px(f, display_txt)
            iters += 1
            logger.debug("post-fit adjust: pt=%d text_px=%dx%d curr_avail_w=%d", 
                        final_pt, fw, fh, curr_avail_w)


class _HanziResizer(QObject):
    """Event filter for handling label resize events."""

    def __init__(self, controller: HanziFontController):
        super().__init__()
        self.controller = controller

    def eventFilter(self, obj, event):
        """Handle resize events for the Hanzi label."""
        if obj is self.controller.label and event.type() == QEvent.Type.Resize:
            # Allow baseline to shrink but never grow
            try:
                cw = max(0, self.controller.label.contentsRect().width())
            except Exception:
                cw = max(0, self.controller.label.width())

            if cw > 0 and isinstance(getattr(self.controller.window, "_hanzi_avail_w0", None), int):
                if self.controller.window._hanzi_avail_w0 is None or cw < self.controller.window._hanzi_avail_w0:
                    self.controller.window._hanzi_avail_w0 = cw
                    logger.debug("Hanzi baseline reduced to %d due to shrink", cw)

            # Trigger font update
            self.controller.update_font_now()

        return False
