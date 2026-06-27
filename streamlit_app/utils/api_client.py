import os

API_BASE = "http://127.0.0.1:8000"

_REQUESTS_AVAILABLE = None


def _import_requests():
    global _REQUESTS_AVAILABLE
    if _REQUESTS_AVAILABLE is None:
        try:
            import requests as _req
            _REQUESTS_AVAILABLE = _req
        except ImportError:
            _REQUESTS_AVAILABLE = False
    return _REQUESTS_AVAILABLE


def _headers():
    api_key = os.getenv("API_KEY", "")
    if api_key:
        return {"X-API-Key": api_key}
    return {}


def health_check() -> bool:
    requests = _import_requests()
    if not requests:
        return False
    try:
        resp = requests.get(f"{API_BASE}/api/system/health", timeout=3, headers=_headers())
        return resp.status_code == 200
    except Exception:
        return False


def _handle_response(resp):
    if not (200 <= resp.status_code < 300):
        try:
            detail = resp.json()
        except Exception:
            return {"error": f"HTTP {resp.status_code}"}
        if isinstance(detail, dict):
            return {"error": detail.get("detail", f"HTTP {resp.status_code}")}
        return {"error": detail if detail else f"HTTP {resp.status_code}"}
    try:
        return resp.json()
    except Exception:
        return {"error": "响应非 JSON"}


def get(endpoint: str):
    requests = _import_requests()
    if not requests:
        return {"error": "requests 库未安装"}
    try:
        resp = requests.get(f"{API_BASE}{endpoint}", timeout=10, headers=_headers())
    except Exception as e:
        return {"error": str(e)}
    return _handle_response(resp)


def post(endpoint: str, data: dict = None):
    requests = _import_requests()
    if not requests:
        return {"error": "requests 库未安装"}
    try:
        resp = requests.post(f"{API_BASE}{endpoint}", json=data or {}, timeout=600, headers=_headers())
    except Exception as e:
        return {"error": str(e)}
    return _handle_response(resp)


def patch(endpoint: str, data: dict):
    requests = _import_requests()
    if not requests:
        return {"error": "requests 库未安装"}
    try:
        resp = requests.patch(f"{API_BASE}{endpoint}", json=data, timeout=30, headers=_headers())
    except Exception as e:
        return {"error": str(e)}
    return _handle_response(resp)


def put(endpoint: str, data: dict):
    requests = _import_requests()
    if not requests:
        return {"error": "requests 库未安装"}
    try:
        resp = requests.put(f"{API_BASE}{endpoint}", json=data, timeout=30, headers=_headers())
    except Exception as e:
        return {"error": str(e)}
    return _handle_response(resp)


def delete(endpoint: str):
    requests = _import_requests()
    if not requests:
        return {"error": "requests 库未安装"}
    try:
        resp = requests.delete(f"{API_BASE}{endpoint}", timeout=30, headers=_headers())
    except Exception as e:
        return {"error": str(e)}
    return _handle_response(resp)


def upload_pdf(endpoint: str, paper_id: str, file_bytes: bytes, filename: str = "upload.pdf"):
    """Upload a PDF file via multipart/form-data."""
    requests = _import_requests()
    files = {"file": (filename, file_bytes, "application/pdf")}
    data = {"paper_id": paper_id}
    resp = requests.post(
        f"{API_BASE}{endpoint}",
        files=files,
        data=data,
        timeout=120,
        headers=_headers(),
    )
    if resp.status_code == 200:
        return resp.json()
    try:
        return {"error": resp.json().get("detail", f"HTTP {resp.status_code}")}
    except Exception:
        return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
