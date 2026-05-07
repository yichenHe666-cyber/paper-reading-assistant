import httpx
import json
import time
import logging

logger = logging.getLogger("paper_reader")

MIRROR_URL = "https://mirror-cn.clawhub.com"
FALLBACK_URL = "https://cn.clawhub-mirror.com"
TIMEOUT = 30
MAX_RETRIES = 2
RETRY_DELAY = 3


class ClawHubError(Exception):
    pass


class ClawHubClient:

    def __init__(self, base_url: str = None):
        self.base_url = base_url or MIRROR_URL

    def _request(self, method: str, path: str, **kwargs) -> dict:
        urls = [self.base_url, FALLBACK_URL] if self.base_url == MIRROR_URL else [self.base_url]
        last_error = None
        for url in urls:
            for attempt in range(MAX_RETRIES + 1):
                try:
                    resp = httpx.request(
                        method,
                        f"{url}{path}",
                        timeout=TIMEOUT,
                        **kwargs,
                    )
                    if resp.status_code == 200:
                        return resp.json()
                    if resp.status_code == 404:
                        return {"error": f"资源不存在: {path}"}
                    last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                except httpx.TimeoutException:
                    last_error = "请求超时"
                except httpx.ConnectError:
                    last_error = "无法连接服务器"
                except Exception as e:
                    last_error = str(e)
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
        raise ClawHubError(f"ClawHub 请求失败: {last_error}")

    def search_skills(self, keyword: str) -> list[dict]:
        try:
            result = self._request("GET", f"/api/skills/search?q={keyword}")
            if isinstance(result, list):
                return result
            if isinstance(result, dict) and "skills" in result:
                return result["skills"]
            if isinstance(result, dict) and "error" in result:
                return []
            return []
        except ClawHubError as e:
            logger.warning(f"ClawHub search failed: {e}")
            return []

    def get_skill_detail(self, slug: str) -> dict:
        try:
            return self._request("GET", f"/api/skills/{slug}")
        except ClawHubError as e:
            return {"error": str(e)}

    def download_skill(self, slug: str) -> dict:
        try:
            result = self._request("GET", f"/api/skills/{slug}/download")
            if "error" in result:
                detail = self.get_skill_detail(slug)
                if "error" not in detail:
                    return detail
                return result
            return result
        except ClawHubError as e:
            return {"error": str(e)}

    def get_featured_skills(self) -> list[dict]:
        try:
            result = self._request("GET", "/api/skills/featured")
            if isinstance(result, list):
                return result
            if isinstance(result, dict) and "skills" in result:
                return result["skills"]
            return []
        except ClawHubError as e:
            logger.warning(f"ClawHub featured failed: {e}")
            return []

    def check_updates(self, installed_skills: list[dict]) -> list[dict]:
        updates = []
        for skill in installed_skills:
            slug = skill.get("clawhub_slug") or skill.get("slug")
            if not slug:
                continue
            try:
                detail = self.get_skill_detail(slug)
                if "error" in detail:
                    continue
                remote_version = detail.get("version", "")
                local_version = skill.get("clawhub_version", "")
                if remote_version and remote_version != local_version:
                    updates.append({
                        "slug": slug,
                        "name": skill.get("name", slug),
                        "local_version": local_version,
                        "remote_version": remote_version,
                        "detail": detail,
                    })
            except Exception:
                continue
        return updates
