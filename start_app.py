import subprocess
import sys
import time
import urllib.request
import os
import webbrowser
import signal
import atexit
import importlib.util

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON = os.path.join(PROJECT_DIR, ".venv", "Scripts", "python.exe")
if not os.path.exists(PYTHON):
    PYTHON = sys.executable

_BACKEND_PROC = None
_FRONTEND_PROC = None

_DEPS_MARKER = os.path.join(PROJECT_DIR, "data", ".deps_ok")

_REQUIRED_MODULES = [
    "fastapi", "uvicorn", "httpx", "sqlalchemy",
    "pydantic", "pydantic_settings", "dotenv",
    "openai", "streamlit", "yaml", "markdown_it",
]


def _check_deps_cached():
    if os.path.exists(_DEPS_MARKER):
        mtime = os.path.getmtime(_DEPS_MARKER)
        if time.time() - mtime < 86400:
            return True
    return False


def _check_deps_inproc():
    for mod in _REQUIRED_MODULES:
        if importlib.util.find_spec(mod) is None:
            return False
    return True


def _mark_deps_ok():
    os.makedirs(os.path.dirname(_DEPS_MARKER), exist_ok=True)
    with open(_DEPS_MARKER, "w", encoding="utf-8") as f:
        f.write("ok")


def ensure_deps():
    if _check_deps_cached():
        return
    if _check_deps_inproc():
        _mark_deps_ok()
        return
    print("[INSTALL] 正在安装依赖包...")
    subprocess.run(
        [PYTHON, "-m", "pip", "install",
         "fastapi", "uvicorn[standard]", "httpx", "sqlalchemy",
         "pydantic", "pydantic-settings", "python-dotenv",
         "openai", "streamlit", "pyyaml", "markdown-it-py", "-q"],
        cwd=PROJECT_DIR,
    )
    _mark_deps_ok()
    print("[INSTALL] 依赖安装完成")


def is_port_ready(port, timeout=1):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=timeout)
        return True
    except Exception:
        return False


def wait_for_port(port, max_wait=15, interval=0.3):
    elapsed = 0.0
    while elapsed < max_wait:
        if is_port_ready(port, timeout=0.5):
            return elapsed
        time.sleep(interval)
        elapsed += interval
    return None


def _terminate_process(proc, name, timeout=5.0):
    if proc is None:
        return
    try:
        if proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2.0)
    except Exception as e:
        print(f"[WARN] 终止 {name} 时出错: {e}")


def cleanup_services():
    global _BACKEND_PROC, _FRONTEND_PROC
    print("\n[INFO] 正在关闭服务...")
    _terminate_process(_FRONTEND_PROC, "前端")
    _terminate_process(_BACKEND_PROC, "后端")
    print("[INFO] 服务已关闭")


def signal_handler(signum, frame):
    sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
    print(f"\n[INFO] 收到信号 {sig_name}，正在优雅退出...")
    cleanup_services()
    sys.exit(0)


def setup_signal_handlers():
    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(cleanup_services)


def _start_backend():
    global _BACKEND_PROC
    if is_port_ready(8000, timeout=1):
        print("[INFO] 后端已在运行中，跳过启动")
        return
    print("[START] 启动 FastAPI 后端 (端口 8000)...")
    _BACKEND_PROC = subprocess.Popen(
        [PYTHON, "-O", "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", "8000"],
        cwd=PROJECT_DIR,
        creationflags=subprocess.CREATE_NO_WINDOW
        if sys.platform == "win32" else 0,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _start_frontend():
    global _FRONTEND_PROC
    print("[START] 启动 Streamlit 前端 (端口 8501)...")
    _FRONTEND_PROC = subprocess.Popen(
        [PYTHON, "-O", "-m", "streamlit", "run", "streamlit_app/main.py",
         "--server.port", "8501",
         "--server.address", "127.0.0.1",
         "--server.headless", "true",
         "--browser.gatherUsageStats", "false"],
        cwd=PROJECT_DIR,
        creationflags=subprocess.CREATE_NO_WINDOW
        if sys.platform == "win32" else 0,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main():
    global _BACKEND_PROC, _FRONTEND_PROC

    os.chdir(PROJECT_DIR)
    setup_signal_handlers()

    t0 = time.perf_counter()

    print()
    print("=" * 44)
    print("       核动力科研牛马 v0.2")
    print("   Papers We Love | AI 导航 | Obsidian")
    print("=" * 44)
    print()

    if not os.path.exists(".env"):
        print("[SETUP] 首次运行，复制 .env.example 为 .env ...")
        import shutil
        shutil.copy(".env.example", ".env")
        print("[SETUP] 请用记事本打开 .env 文件，填入 LLM_API_KEY 后重新运行。")
        print("[SETUP] 如果没有 API Key，可以先浏览论文库（不需要 LLM）。")
        print()
        os.startfile(".env")
        input("按回车键退出...")
        return

    os.makedirs("data", exist_ok=True)
    for d in ["01-论文精读", "02-概念卡片", "03-专业词汇"]:
        os.makedirs(os.path.join("C:\\Users\\Public\\Documents", d), exist_ok=True)

    t_deps = time.perf_counter()
    ensure_deps()
    deps_time = time.perf_counter() - t_deps
    if deps_time > 0.5:
        print(f"[CHECK] 依赖检查完成 ({deps_time:.1f}s)")
    else:
        print("[CHECK] 依赖检查完成")

    _start_backend()
    _start_frontend()

    print("[WAIT] 等待服务就绪...")

    backend_elapsed = wait_for_port(8000, max_wait=15, interval=0.3)
    if backend_elapsed is not None:
        print(f"[OK] 后端已就绪 ({backend_elapsed:.1f}s)")
    else:
        print("[WARN] 后端启动超时，继续尝试...")

    frontend_elapsed = wait_for_port(8501, max_wait=20, interval=0.3)
    if frontend_elapsed is None:
        frontend_elapsed = 5.0
        time.sleep(frontend_elapsed)

    total_time = time.perf_counter() - t0

    print()
    print("=" * 44)
    print("  启动完成！")
    print()
    print("  前端: http://localhost:8501")
    print("  API:  http://localhost:8000/docs")
    print()
    print(f"  总启动耗时: {total_time:.1f}s")
    print()
    print("  正在打开浏览器...")
    print("=" * 44)
    print()

    webbrowser.open("http://localhost:8501")

    print()
    print("首次使用请先点击首页的「同步论文库」")
    print("使用 LLM 功能前请在 .env 中配置 LLM_API_KEY")
    print()
    print("提示: 按 Ctrl+C 可以优雅地关闭所有服务")
    print()

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)


if __name__ == "__main__":
    main()
