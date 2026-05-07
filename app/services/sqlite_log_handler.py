import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from sqlalchemy.orm import Session
from app.database.session import SessionLocal


class SQLiteHandler(logging.Handler):
    def emit(self, record):
        try:
            db = SessionLocal()
            from app.models.system_log import SystemLog
            log_entry = SystemLog(
                level=record.levelname,
                component=getattr(record, "component", "system"),
                message=self.format(record),
                paper_id=getattr(record, "paper_id", None),
            )
            db.add(log_entry)
            db.commit()
            db.close()
        except Exception:
            self.handleError(record)


class _StderrFallbackHandler(logging.Handler):
    _fallback_triggered = False

    def emit(self, record):
        try:
            sys.stderr.write(self.format(record) + "\n")
            sys.stderr.flush()
        except Exception:
            pass


def _resolve_level(level_name: str) -> int:
    level_name = level_name.upper().strip()
    valid = {"DEBUG": logging.DEBUG, "INFO": logging.INFO, "WARNING": logging.WARNING,
             "WARN": logging.WARNING, "ERROR": logging.ERROR, "CRITICAL": logging.CRITICAL}
    return valid.get(level_name, logging.INFO)


def setup_logger(name: str = "paper_reader") -> logging.Logger:
    from app.config import get_settings
    settings = get_settings()

    logger = logging.getLogger(name)
    log_level = _resolve_level(settings.log_level)
    logger.setLevel(log_level)

    if logger.handlers:
        return logger

    detailed_formatter = logging.Formatter(
        "[%(asctime)s][%(levelname)s][%(filename)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_formatter = logging.Formatter("[%(levelname)s] %(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    log_dir = settings.log_dir
    os.makedirs(log_dir, exist_ok=True)
    log_file_path = os.path.join(log_dir, "paper_reader.log")

    try:
        file_handler = RotatingFileHandler(
            log_file_path,
            maxBytes=settings.log_file_max_bytes,
            backupCount=settings.log_file_backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(detailed_formatter)
        logger.addHandler(file_handler)
    except Exception:
        fallback = _StderrFallbackHandler()
        fallback.setLevel(log_level)
        fallback.setFormatter(detailed_formatter)
        logger.addHandler(fallback)
        logger.warning("文件日志写入失败（%s），已切换至 stderr fallback", log_file_path)

    sqlite_handler = SQLiteHandler()
    sqlite_handler.setLevel(log_level)
    sqlite_formatter = logging.Formatter("%(message)s")
    sqlite_handler.setFormatter(sqlite_formatter)
    logger.addHandler(sqlite_handler)

    return logger
