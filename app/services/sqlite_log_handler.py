import logging
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


def setup_logger(name: str = "paper_reader") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter("[%(levelname)s] %(message)s")
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    sqlite_handler = SQLiteHandler()
    sqlite_handler.setLevel(logging.INFO)
    sqlite_formatter = logging.Formatter("%(message)s")
    sqlite_handler.setFormatter(sqlite_formatter)
    logger.addHandler(sqlite_handler)

    return logger
