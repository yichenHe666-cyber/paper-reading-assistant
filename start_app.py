import subprocess
import sys
import time
import urllib.request
import os
import webbrowser
import signal
import atexit

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON = os.path.join(PROJECT_DIR, ".venv", "Scripts", "python.exe")
if not os.path.exists(PYTHON):
    PYTHON = sys.executable

# Global process handles for cleanup
_backend_proc = None
_frontend_proc = None


def is_backend_ready():
    try:
        urllib.request.urlopen("http://127.0.0.1:8000/", timeout=2)
        return True
    except Exception:
        return False


def _terminate_process(proc: subprocess.Popen, name: str, timeout: float = 5.0):
    """Gracefully terminate a subprocess, fallback to kill if needed."""
    if proc is None:
        return
    try:
        if proc.poll() is not None:
            return
        # Try graceful terminate first
        proc.terminate()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2.0)
    except Exception as e:
        print(f"[WARN] 终止 {name} 时出错: {e}")


def cleanup_services():
    """Cleanup handler called on normal exit or signal."""
    global _backend_proc, _frontend_proc
    print("\n[INFO] 正在关闭服务...")
    _terminate_process(_frontend_proc, "前端")
    _terminate_process(_backend_proc, "后端")
    print("[INFO] 服务已关闭")


def signal_handler(signum, frame):
    """Handle Ctrl+C (SIGINT) and other termination signals reliably."""
    sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
    print(f"\n[INFO] 收到信号 {sig_name}，正在优雅退出...")
    cleanup_services()
    sys.exit(0)


def setup_signal_handlers():
    """Register signal handlers for graceful shutdown on Windows."""
    # SIGINT is raised on Ctrl+C in the console
    signal.signal(signal.SIGINT, signal_handler)
    # SIGTERM may be sent by task managers
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, signal_handler)
    # Register atexit as a fallback
    atexit.register(cleanup_services)


def main():
    global _backend_proc, _frontend_proc

    os.chdir(PROJECT_DIR)
    setup_signal_handlers()

    print()
    print("=" * 44)
    print("       经典论文精读助手 v0.2")
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

    print("[CHECK] 检查 Python 依赖...")
    try:
        subprocess.run(
            [PYTHON, "-c", "import fastapi"],
            capture_output=True, timeout=10, check=True,
        )
    except Exception:
        print("[INSTALL] 正在安装依赖包...")
        subprocess.run(
            [PYTHON, "-m", "pip", "install",
             "fastapi", "uvicorn[standard]", "httpx", "sqlalchemy",
             "pydantic", "pydantic-settings", "python-dotenv",
             "openai", "streamlit", "pyyaml", "markdown-it-py", "-q"],
            cwd=PROJECT_DIR,
        )
        print("[INSTALL] 依赖安装完成")

    if is_backend_ready():
        print("[INFO] 后端已在运行中，跳过启动")
    else:
        print("[START] 启动 FastAPI 后端 (端口 8000)...")
        _backend_proc = subprocess.Popen(
            [PYTHON, "-m", "uvicorn", "app.main:app",
             "--host", "127.0.0.1", "--port", "8000"],
            cwd=PROJECT_DIR,
            creationflags=subprocess.CREATE_NO_WINDOW
            if sys.platform == "win32" else 0,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        print("[START] 等待后端就绪 (最多15秒)...")
        for i in range(15):
            if is_backend_ready():
                print(f"[OK] 后端已就绪 ({i+1}s)")
                break
            print(f"  等待中... {i+1}/15")
            time.sleep(1)
        else:
            print("[WARN] 后端启动超时，继续尝试启动前端...")

    print("[START] 启动 Streamlit 前端 (端口 8501)...")
    _frontend_proc = subprocess.Popen(
        [PYTHON, "-m", "streamlit", "run", "streamlit_app/main.py",
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

    print()
    print("=" * 44)
    print("  启动完成！")
    print()
    print("  前端: http://localhost:8501")
    print("  API:  http://localhost:8000/docs")
    print()
    print("  正在打开浏览器...")
    print("=" * 44)
    print()

    time.sleep(3)
    webbrowser.open("http://localhost:8501")

    print()
    print("首次使用请先点击首页的「同步论文库」")
    print("使用 LLM 功能前请在 .env 中配置 LLM_API_KEY")
    print()
    print("提示: 按 Ctrl+C 可以优雅地关闭所有服务")
    print()

    # Keep the main thread alive so signal handlers work reliably.
    # Using a loop with short sleep allows signals to be caught promptly.
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        # This should be handled by signal_handler, but keep as fallback.
        signal_handler(signal.SIGINT, None)


if __name__ == "__main__":
    main()
