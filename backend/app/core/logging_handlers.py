"""Windows-safe timed rotating file handlers for Minerva log sinks."""

from __future__ import annotations

import os
import shutil
import sys
import time
from logging.handlers import TimedRotatingFileHandler


class WindowsSafeTimedRotatingFileHandler(TimedRotatingFileHandler):
    """Timed rotating handler that avoids WinError 32 during rollover on Windows."""

    _WIN_ROTATE_RETRIES = 3
    _WIN_ROTATE_RETRY_DELAY_SEC = 0.05

    def rotate(self, source: str, dest: str) -> None:
        """Rotate the active log file, using copy-and-truncate when rename is blocked."""

        if not os.path.exists(source):
            return
        if os.path.exists(dest):
            os.remove(dest)

        if os.name != "nt":
            os.rename(source, dest)
            return

        for attempt in range(self._WIN_ROTATE_RETRIES):
            try:
                os.rename(source, dest)
                return
            except OSError:
                if attempt + 1 < self._WIN_ROTATE_RETRIES:
                    time.sleep(self._WIN_ROTATE_RETRY_DELAY_SEC)

        with open(source, "rb") as src, open(dest, "wb") as dst:
            shutil.copyfileobj(src, dst)
        with open(source, "w", encoding=self.encoding):
            pass

    def doRollover(self) -> None:
        """Perform rollover and keep the active stream usable when rotation fails."""

        try:
            super().doRollover()
        except OSError as exc:
            if self.stream is None and not self.delay:
                try:
                    self.stream = self._open()
                except OSError:
                    return
            print(
                f"Warning: log rotation failed for {self.baseFilename}: {exc}",
                file=sys.stderr,
            )
