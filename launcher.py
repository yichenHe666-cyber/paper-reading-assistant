import subprocess
import webbrowser
import time
import sys
import os
import signal

os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("Starting services...")

backend = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)

time.sleep(3)

frontend = subprocess.Popen(
    [sys.executable, "-m", "streamlit", "run", "streamlit_app/main.py",
     "--server.port", "8501", "--server.address", "127.0.0.1",
     "--server.headless", "true", "--browser.gatherUsageStats", "false"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)

time.sleep(3)

webbrowser.open("http://localhost:8501")

print("App is running at http://localhost:8501")
print("Close this window to stop all services.")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    frontend.terminate()
    backend.terminate()
    frontend.wait()
    backend.wait()
    print("Services stopped.")
