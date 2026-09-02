from __future__ import annotations

import shutil
import subprocess
from typing import Protocol

from .errors import LexphonError


class Fallback(Protocol):
    def phonemize(self, text: str, language: str) -> str | None: ...


class EspeakFallback:
    """Optional eSpeak/eSpeak-NG IPA fallback. It is never enabled implicitly."""

    def __init__(self, executable: str | None = None):
        self.executable = executable or shutil.which("espeak-ng") or shutil.which("espeak")
        if not self.executable:
            raise LexphonError("eSpeak fallback requested but espeak-ng/espeak is not installed")

    def phonemize(self, text: str, language: str) -> str | None:
        voice = language.lower().replace("_", "-")
        completed = subprocess.run(
            [self.executable, "-q", "--ipa=3", "-v", voice, text],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if completed.returncode != 0:
            return None
        value = " ".join(completed.stdout.split())
        return value or None
