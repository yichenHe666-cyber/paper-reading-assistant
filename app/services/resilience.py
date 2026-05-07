import time
import logging
import threading
from functools import wraps

logger = logging.getLogger("paper_reader")


def llm_retry(max_retries: int = 3, base_delay: float = 1.0):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    err_str = str(e)
                    if "Connection error" in err_str or "timeout" in err_str.lower():
                        wait = base_delay * (2 ** attempt)
                        logger.warning(f"LLM 调用失败 (尝试 {attempt+1}/{max_retries})，{wait}s 后重试: {err_str[:100]}")
                        time.sleep(wait)
                        continue
                    if "rate_limit" in err_str.lower() or "429" in err_str:
                        wait = base_delay * (4 ** attempt)
                        logger.warning(f"LLM 速率限制 (尝试 {attempt+1}/{max_retries})，{wait}s 后重试")
                        time.sleep(wait)
                        continue
                    raise
            raise RuntimeError(f"LLM 调用 {max_retries} 次后仍失败: {str(last_error)[:200]}") if last_error else None
        return wrapper
    return decorator


class RateLimiter:
    def __init__(self, min_interval: float = 3.0):
        self._min_interval = min_interval
        self._last_call = 0.0
        self._lock = threading.Lock()

    def wait(self):
        with self._lock:
            elapsed = time.time() - self._last_call
            if elapsed < self._min_interval:
                wait = self._min_interval - elapsed
                time.sleep(wait)
            self._last_call = time.time()

    def reset(self):
        with self._lock:
            self._last_call = 0.0


def safe_file_write(filepath, content: str, encoding: str = "utf-8"):
    import os
    tmp_path = str(filepath) + ".tmp"
    try:
        with open(tmp_path, "w", encoding=encoding) as f:
            f.write(content)
        os.replace(tmp_path, filepath)
    except PermissionError:
        import shutil
        shutil.copy2(tmp_path, filepath)
        os.remove(tmp_path)
    except Exception:
        raise
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
