from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from typing import Iterator
from dotenv import load_dotenv


_CONFIGURED = False


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    try:
        load_dotenv()
    except Exception:
        pass

    level_name = (os.getenv("BLIQ_LOG_LEVEL") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger("bylaws_iq")
    root.setLevel(level)

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    sh.setLevel(level)
    root.addHandler(sh)

    log_file = os.getenv("BLIQ_LOG_FILE")
    if log_file:
        fh = logging.FileHandler(log_file)
        fh.setFormatter(fmt)
        fh.setLevel(level)
        root.addHandler(fh)

    _CONFIGURED = True


@contextmanager
def span(logger: logging.Logger, step: str) -> Iterator[None]:
    start = time.time()
    logger.info("step.start: %s", step)
    try:
        yield
    finally:
        dur_ms = int((time.time() - start) * 1000)
        logger.info("step.end: %s | durationMs=%d", step, dur_ms)
