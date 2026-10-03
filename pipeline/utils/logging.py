"""Structured logging for FlightPrint pipeline stages."""

import logging
import sys
import time
import json
from pathlib import Path
from functools import wraps


def get_logger(stage_name: str, output_dir: Path | None = None) -> logging.Logger:
    """Create a structured logger for a pipeline stage.
    
    Logs to both console (human-readable) and a JSON file (machine-readable)
    for post-mortem debugging during demos.
    """
    logger = logging.getLogger(f"flightprint.{stage_name}")
    logger.setLevel(logging.DEBUG)

    # Check whether an existing FileHandler points to a different directory.
    # This matters on Windows where open handles block temp-dir cleanup in tests.
    if logger.handlers and output_dir is not None:
        target_log = (Path(output_dir) / f"{stage_name}.log").resolve()
        stale = [
            h for h in logger.handlers
            if isinstance(h, logging.FileHandler)
            and Path(h.baseFilename).resolve() != target_log
        ]
        for h in stale:
            h.close()
            logger.removeHandler(h)

    if logger.handlers:
        return logger

    # Console handler — concise, colored
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    fmt = logging.Formatter(
        f"[%(asctime)s] [{stage_name}] %(levelname)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    console.setFormatter(fmt)
    logger.addHandler(console)

    # File handler — JSON lines for structured debugging
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        log_path = output_dir / f"{stage_name}.log"
        file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)

        class JsonFormatter(logging.Formatter):
            def format(self, record):
                return json.dumps({
                    "ts": record.created,
                    "stage": stage_name,
                    "level": record.levelname,
                    "msg": record.getMessage(),
                })

        file_handler.setFormatter(JsonFormatter())
        logger.addHandler(file_handler)

    return logger


def log_stage(stage_name: str):
    """Decorator that logs stage entry/exit with timing."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = logging.getLogger(f"flightprint.{stage_name}")
            logger.info(f"[START] Starting stage: {stage_name}")
            t0 = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                elapsed = time.perf_counter() - t0
                logger.info(f"[PASS] Completed {stage_name} in {elapsed:.1f}s")
                return result
            except Exception as e:
                elapsed = time.perf_counter() - t0
                logger.error(f"[FAIL] Failed {stage_name} after {elapsed:.1f}s: {e}")
                raise
        return wrapper
    return decorator
