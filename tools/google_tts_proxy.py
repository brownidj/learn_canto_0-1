#!/usr/bin/env python3
"""Local Google TTS proxy for mobile clients.

Uses Application Default Credentials on the server side and returns
audio + timepoints for SSML marks.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_GOOGLE_TTS_PATH = os.path.join(_ROOT, "services", "google_tts_service.py")
if os.path.exists(_GOOGLE_TTS_PATH):
    import importlib.util

    spec = importlib.util.spec_from_file_location("google_tts_service", _GOOGLE_TTS_PATH)
    if spec is None or spec.loader is None:
        raise ImportError("Failed to load google_tts_service module spec")
    _mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_mod)
    GoogleTTSService = _mod.GoogleTTSService
else:
    from services.google_tts_service import GoogleTTSService


def _escape_html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _build_ssml(text: str) -> str:
    parts = ["<speak>"]
    for i, ch in enumerate(text):
        parts.append(f"<mark name='s{i}'/>{_escape_html(ch)}")
    parts.append("</speak>")
    return "".join(parts)


class _Handler(BaseHTTPRequestHandler):
    server_version = "LearnCantoTTS/1.0"

    def _send_json(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/voices":
            self._send_json(404, {"error": "not_found"})
            return
        try:
            service = self.server.tts_service  # type: ignore[attr-defined]
            voices = getattr(service, "available_voices", []) or []
            out = []
            for name, locale, label in voices:
                if not str(locale).startswith("yue"):
                    continue
                short = name.split("-")[-1] if name else ""
                display = short or label or name
                out.append({"name": name, "locale": locale, "label": display})
            self._send_json(200, {"voices": out})
        except Exception as exc:
            self._send_json(500, {"error": "voices_failed", "detail": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/tts":
            self._send_json(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except Exception:
            length = 0
        raw = self.rfile.read(length) if length > 0 else b""
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            self._send_json(400, {"error": "invalid_json"})
            return
        text = str(payload.get("text") or "").strip()
        voice = payload.get("voice")
        rate = payload.get("rate")
        print(f"[proxy] request text_len={len(text)} voice={voice!r} rate={rate!r}")
        if not text:
            self._send_json(400, {"error": "missing_text"})
            return
        try:
            if voice:
                v = str(voice)
                # Accept only known Google Cloud voice name patterns for yue-HK.
                if not v.startswith("yue-HK-Standard-") and not v.startswith("yue-HK-Wavenet-"):
                    voice = None
            service = self.server.tts_service  # type: ignore[attr-defined]
            ssml = _build_ssml(text)
            audio, timepoints = service.synthesize_ssml_with_timepoints(
                ssml=ssml,
                voice=str(voice) if voice else None,
                rate=int(rate) if isinstance(rate, int) else None,
            )
            print(f"[proxy] response audio_bytes={len(audio)} timepoints={len(timepoints)}")
            if not audio:
                self._send_json(
                    502,
                    {
                        "error": "tts_empty",
                        "audio_bytes": len(audio),
                        "timepoints": len(timepoints),
                    },
                )
                return
            audio_b64 = base64.b64encode(audio).decode("utf-8")
            tp_payload = [
                {"markName": name, "timeSeconds": ts} for name, ts in timepoints
            ]
            self._send_json(200, {"audioContent": audio_b64, "timepoints": tp_payload})
        except Exception as exc:
            self._send_json(500, {"error": "tts_failed", "detail": str(exc)})


def main() -> None:
    parser = argparse.ArgumentParser(description="Local Google TTS proxy.")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=8765, help="Bind port")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), _Handler)
    server.tts_service = GoogleTTSService()  # type: ignore[attr-defined]
    print(f"TTS proxy running on http://{args.host}:{args.port}/tts")
    server.serve_forever()


if __name__ == "__main__":
    main()
