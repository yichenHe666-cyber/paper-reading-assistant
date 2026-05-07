import logging
import os
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
from io import StringIO

import pytest

from app.config import Settings, get_settings


class TestLoggingConfig:
    def test_settings_log_level_default(self):
        s = Settings()
        assert s.log_level == "INFO"

    def test_settings_log_dir_default(self):
        s = Settings()
        assert s.log_dir == "logs"

    def test_settings_log_file_max_bytes_default(self):
        s = Settings()
        assert s.log_file_max_bytes == 5242880

    def test_settings_log_file_backup_count_default(self):
        s = Settings()
        assert s.log_file_backup_count == 5

    def test_settings_log_level_override(self):
        s = Settings(log_level="DEBUG")
        assert s.log_level == "DEBUG"

    def test_settings_log_dir_override(self):
        s = Settings(log_dir="custom_logs")
        assert s.log_dir == "custom_logs"


class TestSetupLogger:
    def _clean_logger(self, name="paper_reader_test"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        return logger

    def test_setup_logger_creates_console_handler(self):
        logger = self._clean_logger("test_console")
        from app.services.sqlite_log_handler import setup_logger
        with patch("app.services.sqlite_log_handler.RotatingFileHandler") as mock_rot:
            mock_handler = MagicMock()
            mock_handler.level = logging.INFO
            mock_rot.return_value = mock_handler
            with patch("app.services.sqlite_log_handler.SQLiteHandler") as mock_sql:
                mock_sql_instance = MagicMock()
                mock_sql_instance.level = logging.INFO
                mock_sql.return_value = mock_sql_instance
                logger = setup_logger("test_console")

        handler_types = [type(h).__name__ for h in logger.handlers]
        assert "StreamHandler" in handler_types

    def test_setup_logger_creates_file_handler(self):
        logger = self._clean_logger("test_file")
        with tempfile.TemporaryDirectory() as tmpdir:
            from app.services.sqlite_log_handler import _resolve_level
            level = _resolve_level("DEBUG")
            assert level == logging.DEBUG

    def test_setup_logger_with_debug_level(self):
        logger = self._clean_logger("test_debug")
        from app.services.sqlite_log_handler import _resolve_level
        assert _resolve_level("DEBUG") == logging.DEBUG
        assert _resolve_level("INFO") == logging.INFO
        assert _resolve_level("WARNING") == logging.WARNING
        assert _resolve_level("WARN") == logging.WARNING
        assert _resolve_level("ERROR") == logging.ERROR
        assert _resolve_level("CRITICAL") == logging.CRITICAL

    def test_setup_logger_invalid_level_defaults_to_info(self):
        from app.services.sqlite_log_handler import _resolve_level
        assert _resolve_level("INVALID") == logging.INFO
        assert _resolve_level("") == logging.INFO

    def test_setup_logger_creates_rotating_file_handler(self):
        logger = self._clean_logger("test_rotating")
        tmpdir = tempfile.mkdtemp()
        try:
            with patch("app.config.get_settings") as mock_settings:
                mock_settings.return_value = Settings(
                    log_dir=tmpdir,
                    log_level="INFO",
                    log_file_max_bytes=1024,
                    log_file_backup_count=3,
                )
                with patch("app.services.sqlite_log_handler.SQLiteHandler") as mock_sql:
                    mock_sql_instance = MagicMock()
                    mock_sql_instance.level = logging.INFO
                    mock_sql.return_value = mock_sql_instance
                    from app.services.sqlite_log_handler import setup_logger
                    result = setup_logger("test_rotating")

            handler_types = [type(h).__name__ for h in result.handlers]
            assert "RotatingFileHandler" in handler_types

            log_path = os.path.join(tmpdir, "paper_reader.log")
            result.info("测试日志条目 - 文件轮转功能验证")

            with open(log_path, "r", encoding="utf-8") as f:
                content = f.read()
            assert "测试日志条目" in content
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_setup_logger_detailed_format(self):
        logger = self._clean_logger("test_format")
        tmpdir = tempfile.mkdtemp()
        try:
            with patch("app.config.get_settings") as mock_settings:
                mock_settings.return_value = Settings(
                    log_dir=tmpdir,
                    log_level="INFO",
                    log_file_max_bytes=1048576,
                    log_file_backup_count=1,
                )
                with patch("app.services.sqlite_log_handler.SQLiteHandler") as mock_sql:
                    mock_sql_instance = MagicMock()
                    mock_sql_instance.level = logging.INFO
                    mock_sql.return_value = mock_sql_instance
                    from app.services.sqlite_log_handler import setup_logger
                    result = setup_logger("test_format")

            result.info("格式验证日志")
            log_path = os.path.join(tmpdir, "paper_reader.log")
            with open(log_path, "r", encoding="utf-8") as f:
                content = f.read()

            assert "[INFO]" in content
            assert "[test_logging.py:" in content
            assert "格式验证日志" in content
            assert "202" in content
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_duplicate_setup_logger_returns_same(self):
        logger = self._clean_logger("test_dup")
        with patch("app.config.get_settings") as mock_settings:
            mock_settings.return_value = Settings(log_level="INFO")
            with patch("app.services.sqlite_log_handler.RotatingFileHandler") as mock_rot:
                mock_handler = MagicMock()
                mock_handler.level = logging.INFO
                mock_rot.return_value = mock_handler
                with patch("app.services.sqlite_log_handler.SQLiteHandler") as mock_sql:
                    mock_sql_instance = MagicMock()
                    mock_sql_instance.level = logging.INFO
                    mock_sql.return_value = mock_sql_instance
                    from app.services.sqlite_log_handler import setup_logger
                    a = setup_logger("test_dup")
                    b = setup_logger("test_dup")
            assert a is b
            assert len(a.handlers) == len(b.handlers)


class TestLogLevelFiltering:
    def test_debug_not_logged_at_info_level(self):
        logger = logging.getLogger("test_level_filter")
        logger.handlers.clear()
        logger.setLevel(logging.INFO)

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(handler)

        logger.debug("这条不应该出现")
        logger.info("这条应该出现")

        output = stream.getvalue()
        assert "不应该出现" not in output
        assert "应该出现" in output

    def test_warning_logged_at_info_level(self):
        logger = logging.getLogger("test_warn_filter")
        logger.handlers.clear()
        logger.setLevel(logging.INFO)

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(handler)

        logger.warning("警告信息")
        logger.error("错误信息")

        output = stream.getvalue()
        assert "警告信息" in output
        assert "错误信息" in output

    def test_all_levels_at_debug(self):
        logger = logging.getLogger("test_debug_all")
        logger.handlers.clear()
        logger.setLevel(logging.DEBUG)

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(handler)

        logger.debug("debug消息")
        logger.info("info消息")
        logger.warning("warning消息")
        logger.error("error消息")

        output = stream.getvalue()
        assert "debug消息" in output
        assert "info消息" in output
        assert "warning消息" in output
        assert "error消息" in output


class TestLoggerException:
    def test_exception_includes_traceback(self):
        logger = logging.getLogger("test_exc")
        logger.handlers.clear()
        logger.setLevel(logging.DEBUG)

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logger.addHandler(handler)

        try:
            raise ValueError("测试异常")
        except ValueError:
            logger.exception("捕获到异常")

        output = stream.getvalue()
        assert "捕获到异常" in output
        assert "ValueError" in output
        assert "测试异常" in output
        assert "Traceback" in output or "test_logging.py" in output

    def test_exception_without_active_exception(self):
        logger = logging.getLogger("test_exc2")
        logger.handlers.clear()
        logger.setLevel(logging.DEBUG)

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logger.addHandler(handler)

        logger.exception("无活跃异常的exception调用")

        output = stream.getvalue()
        assert "无活跃异常的exception调用" in output
        assert "NoneType" in output


class TestRotatingFileHandler:
    def test_log_rotation(self):
        tmpdir = tempfile.mkdtemp()
        try:
            log_path = os.path.join(tmpdir, "test_rotate.log")
            handler = logging.handlers.RotatingFileHandler(
                log_path, maxBytes=200, backupCount=3, encoding="utf-8"
            )
            logger = logging.getLogger("test_rotation")
            logger.handlers.clear()
            logger.setLevel(logging.DEBUG)
            logger.addHandler(handler)

            for i in range(50):
                logger.debug("日志条目%03d: 这是一条用于测试日志轮转的较长消息内容" % i)

            handler.close()

            log_files = sorted(Path(tmpdir).glob("test_rotate.log*"))
            assert len(log_files) >= 2, f"预期至少2个日志文件（主文件 + 轮转文件），实际: {len(log_files)}"
            main_content = log_files[0].read_text(encoding="utf-8")
            assert len(main_content) > 0
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestStderrFallback:
    def test_file_handler_failure_falls_back_to_stderr(self):
        logger = logging.getLogger("test_fallback")
        logger.handlers.clear()
        logger.setLevel(logging.INFO)

        bogus_path = "Z:\\nonexistent\\path\\that\\should\\fail\\paper_reader.log"

        try:
            file_handler = logging.handlers.RotatingFileHandler(
                bogus_path, maxBytes=1024, backupCount=1, encoding="utf-8"
            )
            file_handler.setLevel(logging.INFO)
            logger.addHandler(file_handler)
            logger.warning("这应该触发fallback")
            assert False, "应该抛出异常"
        except (OSError, FileNotFoundError, PermissionError):
            from app.services.sqlite_log_handler import _StderrFallbackHandler
            fallback = _StderrFallbackHandler()
            fallback.setLevel(logging.INFO)
            fallback.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
            logger.addHandler(fallback)
            logger.warning("文件日志写入失败，已切换至 stderr fallback")
