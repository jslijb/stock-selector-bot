import sys
import os

if sys.platform == "win32":
    import ctypes

    _STD_INPUT_HANDLE = -10
    _ENABLE_QUICK_EDIT_MODE = 0x0040
    _ENABLE_INSERT_MODE = 0x0020
    _ENABLE_EXTENDED_FLAGS = 0x0080

    _kernel32 = ctypes.windll.kernel32
    _handle = _kernel32.GetStdHandle(_STD_INPUT_HANDLE)
    _mode = ctypes.c_ulong()
    if _kernel32.GetConsoleMode(_handle, ctypes.byref(_mode)):
        _new_mode = (_mode.value & ~_ENABLE_QUICK_EDIT_MODE & ~_ENABLE_INSERT_MODE) | _ENABLE_EXTENDED_FLAGS
        _kernel32.SetConsoleMode(_handle, _new_mode)

from loguru import logger
from pathlib import Path

log_dir = Path(__file__).parent / "logs"
log_dir.mkdir(exist_ok=True)

_LOG_FMT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}"
)

logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
    level="INFO",
    colorize=True,
)
logger.add(
    log_dir / "stock_agent_{time:YYYY-MM-DD}.log",
    rotation="1 day",
    level="DEBUG",
    encoding="utf-8",
    format=_LOG_FMT,
    backtrace=True,
    diagnose=True,
)
logger.add(
    log_dir / "errors.log",
    rotation="10 MB",
    level="ERROR",
    encoding="utf-8",
    format=_LOG_FMT,
    backtrace=True,
    diagnose=True,
)
logger.add(
    log_dir / "trace.log",
    rotation="50 MB",
    level="TRACE",
    encoding="utf-8",
    format=_LOG_FMT,
    backtrace=True,
    diagnose=True,
)

from src.interface.cli import main

if __name__ == "__main__":
    main()
