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


def get(endpoint: str):
    requests = _import_requests()
    resp = requests.get(f"{API_BASE}{endpoint}", timeout=10, headers=_headers())
    return resp.json()


def post(endpoint: str, data: dict = None):
    requests = _import_requests()
    resp = requests.post(f"{API_BASE}{endpoint}", json=data or {}, timeout=600, headers=_headers())
    return resp.json()


def patch(endpoint: str, data: dict):
    requests = _import_requests()
    resp = requests.patch(f"{API_BASE}{endpoint}", json=data, timeout=30, headers=_headers())
    return resp.json()


def put(endpoint: str, data: dict):
    requests = _import_requests()
    resp = requests.put(f"{API_BASE}{endpoint}", json=data, timeout=30, headers=_headers())
    return resp.json()


def delete(endpoint: str):
    requests = _import_requests()
    resp = requests.delete(f"{API_BASE}{endpoint}", timeout=30, headers=_headers())
    return resp.json()


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
