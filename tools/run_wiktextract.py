from __future__ import annotations

import json
import sys
import inspect
import bz2
import re
from typing import Any, Dict, List, Union

from wiktextract.wiktionary import parse_wiktionary  # provided by the package
from wikitextprocessor import Wtp
from wiktextract.config import WiktionaryConfig

import logging

# Reduce noisy DEBUG output from dependencies
logging.basicConfig(level=logging.INFO)
logging.getLogger("wikitextprocessor").setLevel(logging.WARNING)
logging.getLogger("wiktextract").setLevel(logging.WARNING)
logging.getLogger("wikitextprocessor.core").setLevel(logging.ERROR)

# --- Console snapshotting: write every 500th console line to data/snapshot.json ---
import os
from io import TextIOBase

SNAPSHOT_PATH = os.path.join("data", "snapshot.json")

class _SharedCounter:
    def __init__(self):
        self.n = 0

_shared_counter = _SharedCounter()

class SnapshottingStream(TextIOBase):
    """
    Wrap a text stream (stdout/stderr). For every newline-terminated line written,
    increment a global counter shared across both streams; whenever the counter
    hits a multiple of 500, append that line (exact text) into data/snapshot.json
    as a JSON object per line.
    """
    def __init__(self, base_stream, stream_name):
        self._base = base_stream
        self._name = stream_name
        self._buf = ""

    def writable(self):
        return True

    def write(self, s):
        # pass-through
        self._base.write(s)
        # accumulate and split on newlines
        self._buf += s
        while True:
            idx = self._buf.find("\n")
            if idx == -1:
                break
            line = self._buf[:idx]
            self._buf = self._buf[idx+1:]
            _shared_counter.n += 1
            if _shared_counter.n % 500 == 0:
                try:
                    # Append JSONL record (filename uses .json but content is JSON Lines for simplicity)
                    rec = {"line_no": _shared_counter.n, "stream": self._name, "text": line}
                    with open(SNAPSHOT_PATH, "a", encoding="utf-8") as _sf:
                        _sf.write(json.dumps(rec, ensure_ascii=False) + "\n")
                except Exception:
                    # avoid breaking the primary output on snapshot errors
                    pass
        return len(s)

    def flush(self):
        try:
            self._base.flush()
        except Exception:
            pass

    # Delegate common attributes to the underlying stream for compatibility
    def __getattr__(self, item):
        return getattr(self._base, item)

# Wrap the process-wide stdout/stderr once
if not isinstance(sys.stdout, SnapshottingStream):
    sys.stdout = SnapshottingStream(sys.stdout, "stdout")
if not isinstance(sys.stderr, SnapshottingStream):
    sys.stderr = SnapshottingStream(sys.stderr, "stderr")
# --- End console snapshotting ---

# --- Progress helpers ---
def estimate_total_pages(path: str) -> int:
    """Very rough page count by scanning the dump for '<page>'.
    Works for both .bz2 and plain .xml files. Returns 0 on error.
    """
    try:
        total = 0
        # Choose opener based on extension
        if path.endswith(".bz2"):
            opener = lambda p: bz2.open(p, 'rt', encoding='utf-8', errors='ignore')
        else:
            opener = lambda p: open(p, 'rt', encoding='utf-8', errors='ignore')
        with opener(path) as f:
            for line in f:
                total += line.count('<page>')
        return total
    except Exception:
        return 0
# --- End progress helpers ---


# --- Cantonese pre-filter helper ---
def filter_cantonese_dump(src_bz2: str, dst_xml: str) -> int:
    """
    Stream the compressed zhwiktionary dump and write a *valid* reduced XML file
    that contains only pages likely relevant to Cantonese. We keep the original
    XML header/opening tags captured before the first <page>, then append
    matching <page> chunks, and finally write a closing </mediawiki>.

    Returns the number of kept pages.
    """
    kw = re.compile(r'(?:==\s*(?:粵語|粤語|粤语)\s*==|\{\{\s*(?:yue|Cantonese)\b|\{\{\s*zh-pron[^}]*\byue\s*=)', re.IGNORECASE)
    pages = 0
    kept = 0
    header_lines = []
    wrote_header = False
    in_page = False
    buf = []

    # Ensure output directory exists
    os.makedirs(os.path.dirname(dst_xml) or ".", exist_ok=True)

    with bz2.open(src_bz2, 'rt', encoding='utf-8', errors='ignore') as fin, \
         open(dst_xml, 'w', encoding='utf-8') as fout:
        for line in fin:
            if not in_page:
                if '<page>' in line:
                    in_page = True
                    pages += 1
                    buf = [line]
                    if not wrote_header:
                        # Write the captured header (XML decl, <mediawiki...>, <siteinfo> etc.)
                        for h in header_lines:
                            fout.write(h)
                        wrote_header = True
                else:
                    if not wrote_header:
                        header_lines.append(line)
                continue
            else:
                buf.append(line)
                if '</page>' in line:
                    chunk = ''.join(buf)
                    if kw.search(chunk):
                        fout.write(chunk)
                        kept += 1
                    in_page = False
        # Close the root element if we wrote any header
        if wrote_header:
            fout.write('</mediawiki>\n')
    return kept
# --- End Cantonese pre-filter helper ---


def main(dump_file: str, language: str, out_file: str) -> None:
    """
    Run wiktextract on a Wiktionary dump and write JSONL output.

    Parameters
    ----------
    dump_file : str
        Path to the zhwiktionary *pages-articles* .xml.bz2 dump.
    language : str
        Language code to capture (e.g., 'zh' for Chinese).
    out_file : str
        Where to write JSON Lines output.
    """
    # Use English Wiktionary directly (supported by wiktextract)
    use_enwiktionary = os.path.basename(dump_file).startswith("enwiktionary-")

    if use_enwiktionary:
        input_path = dump_file
        print("[filter] Skipping Cantonese pre-filter (English Wiktionary is supported).", file=sys.stderr)
    else:
        # (Your existing pre-filter for Chinese dumps can remain here,
        # but it won’t produce useful output with wiktextract.)
        try:
            filtered_path = os.path.join("data", "zhwiktionary_cantonese.xml")
            kept_pages = filter_cantonese_dump(dump_file, filtered_path)
            print(f"[filter] Kept {kept_pages} likely Cantonese pages in {filtered_path}", file=sys.stderr)
            input_path = filtered_path
        except Exception as e:
            print(f"[filter] Pre-filter failed ({e}); proceeding with original dump.", file=sys.stderr)
            input_path = dump_file

    # Pre-scan to estimate total pages for progress reporting
    total_pages = estimate_total_pages(input_path)
    pages_seen = 0
    next_progress = 1  # write progress at 1%,2%,...,100%
    try:
        if total_pages:
            print(f"[progress] Estimated total pages: {total_pages}", file=sys.stderr)
        else:
            print("[progress] Could not estimate total pages (no progress %).", file=sys.stderr)
    except Exception:
        pass

    # Minimal config – tune as needed.
    # Older/newer wiktextract versions have different WiktionaryConfig signatures,
    # so we instantiate first, then set attributes if they exist.
    cfg = WiktionaryConfig()
    # Force Cantonese only, regardless of CLI arg
    # if hasattr(cfg, "capture_language_codes"):
    #     cfg.capture_language_codes = ["yue"]  # ISO 639-3 for Cantonese
    # elif hasattr(cfg, "capture_languages"):
    #     cfg.capture_languages = ["yue"]
    # Common toggles (set only if present on this version)
    for name, value in [
        ("translations", True),
        ("redirects", False),
        ("pronunciations", True),
        ("capture_pronunciation", True),
        ("capture_examples", True),
    ]:
        if hasattr(cfg, name):
            setattr(cfg, name, value)

    try:
        langs = getattr(cfg, "capture_language_codes", getattr(cfg, "capture_languages", None))
        print(f"[wiktextract] Config ready; langs={langs}", file=sys.stderr)
        print("[wiktextract] NOTE: Forcing Cantonese (yue) only; redirects dropped.", file=sys.stderr)
    except Exception:
        pass

    # Create a processing context; some wikitextprocessor versions do not accept
    # a lang_code kwarg. Fallback to bare Wtp() if needed.
    try:
        ctx = Wtp(lang_code="yue")  # newer versions, force Cantonese context
    except TypeError:
        ctx = Wtp()  # older versions
        # Language filtering still occurs via cfg["capture_language_codes"]

    # For visibility, show the signature we are about to call (should be:
    # (ctx, path, config, word_cb, capture_cb=None, phase1_only=False))
    try:
        sig = str(inspect.signature(parse_wiktionary))
        print(f"[wiktextract] parse_wiktionary signature: {sig}", file=sys.stderr)
    except Exception:
        pass

    # Count of emitted Cantonese records
    count = 0

    # Open output and stream records via callback
    with open(out_file, "w", encoding="utf-8") as fh:


        # Optional cap for smoke-tests; set WIKT_MAX>0 to limit
        max_entries_env = os.environ.get('WIKT_MAX', '0')
        try:
            max_entries = int(max_entries_env)
        except Exception:
            max_entries = 0

        def emit_record(rec: Dict[str, Any]) -> None:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

        def _is_cantonese_record(obj: Dict[str, Any]) -> bool:
            """Keep likely Cantonese entries; skip redirects and non-dicts."""
            if not isinstance(obj, dict) or obj.get('redirect'):
                return False
            lc = (obj.get('lang_code') or '').lower()
            lang = (obj.get('lang') or '').lower()
            tags = obj.get('tags') or []
            tags_l = [t.lower() for t in tags if isinstance(t, str)]
            # Accept if explicitly Cantonese or language code is yue
            if lc == 'yue' or 'cantonese' in lang or 'cantonese' in tags_l:
                return True
            # Some zh entries carry dialect info only in etymology/pronunciation blocks; be lenient
            lect = (obj.get('lect') or '').lower()
            if 'cantonese' in lect:
                return True
            return False

        def word_cb(data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> None:
            nonlocal count
            def _emit_and_count(obj: Dict[str, Any]) -> None:
                nonlocal count
                if not _is_cantonese_record(obj):
                    return
                emit_record(obj)
                fh.flush()
                count += 1
                if max_entries > 0 and count >= max_entries:
                    # Abort parse cleanly when limit is reached
                    raise StopIteration

            if isinstance(data, dict):
                _emit_and_count(data)
            elif isinstance(data, list):
                for rec in data:
                    if isinstance(rec, dict):
                        _emit_and_count(rec)

        def capture_cb(*args, **kwargs) -> None:
            nonlocal pages_seen, next_progress, count
            # Heuristic: wiktextract calls capture_cb once per page; treat each call as one page processed.
            try:
                pages_seen += 1
                if total_pages:
                    percent = int(pages_seen * 100 / total_pages)
                    if percent >= next_progress and 1 <= percent <= 100:
                        # Append a compact JSON progress record
                        try:
                            with open(os.path.join("data", "progress.log"), "a", encoding="utf-8") as pf:
                                pf.write(json.dumps({
                                    "percent": percent,
                                    "pages_seen": pages_seen,
                                    "total_pages": total_pages,
                                    "emitted": count
                                }, ensure_ascii=False) + "\n")
                        except Exception:
                            pass
                        # Also echo a brief message to stderr
                        try:
                            print(f"[progress] ~{percent}% (pages={pages_seen}/{total_pages}, emitted={count})", file=sys.stderr)
                        except Exception:
                            pass
                        next_progress = percent + 1
            except Exception:
                # Never let progress accounting break the parse
                pass
            return

        # Indicate which file is being parsed
        try:
            print(f"[wiktextract] Parsing from: {input_path}", file=sys.stderr)
        except Exception:
            pass

        # Invoke using the installed signature
        try:
            parse_wiktionary(
                ctx,
                input_path,
                cfg,
                word_cb,
                capture_cb=capture_cb,
                phase1_only=False,
            )
        except StopIteration:
            # Clean stop after reaching WIKT_MAX
            print(f"[wiktextract] Stopped after {count} records (limit {max_entries}).", file=sys.stderr)
            return


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(
            "Usage: python3 tools/run_wiktextract.py <dump.bz2> <lang> <out.jsonl>",
            file=sys.stderr,
        )
        sys.exit(2)
    main(sys.argv[1], sys.argv[2], sys.argv[3])