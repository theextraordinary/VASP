from __future__ import annotations

import sys
import time
from dataclasses import dataclass


def _fmt_seconds(seconds: float) -> str:
    if seconds <= 0 or seconds == float("inf"):
        return "--:--"
    total = int(seconds)
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


@dataclass
class ProgressBar:
    total: int
    width: int = 28

    def __post_init__(self) -> None:
        self.total = max(1, int(self.total))
        self.current = 0
        self.started_at = time.time()
        self.last_message = ""

    def set_total(self, total: int) -> None:
        self.total = max(self.total, int(total), 1)
        self.render(self.last_message)

    def advance(self, message: str, step: int = 1) -> None:
        self.current = min(self.total, self.current + max(0, int(step)))
        self.render(message)

    def render(self, message: str) -> None:
        self.last_message = message
        elapsed = max(0.001, time.time() - self.started_at)
        ratio = min(1.0, max(0.0, self.current / self.total))
        filled = int(round(self.width * ratio))
        bar = "#" * filled + "-" * (self.width - filled)
        eta = (elapsed / ratio - elapsed) if ratio > 0 else 0.0
        line = f"\r[{bar}] {self.current:>3}/{self.total:<3} ETA {_fmt_seconds(eta)}  {message[:90]}"
        sys.stdout.write(line)
        sys.stdout.flush()

    def finish(self, message: str = "Done") -> None:
        self.current = self.total
        self.render(message)
        sys.stdout.write("\n")
        sys.stdout.flush()
