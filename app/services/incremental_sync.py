import time
import httpx
from typing import Optional

GITHUB_API_BASE = "https://api.github.com"


def get_topic_commits(topic_id: str, repo: str = "papers-we-love/papers-we-love", since: str = None) -> Optional[str]:
    url = f"{GITHUB_API_BASE}/repos/{repo}/commits"
    params = {"path": topic_id, "per_page": 1}
    if since:
        params["since"] = since
    try:
        resp = httpx.get(url, params=params, timeout=15, headers={"Accept": "application/vnd.github.v3+json"})
        if resp.status_code == 200:
            commits = resp.json()
            if commits:
                return commits[0]["sha"]
        elif resp.status_code == 403:
            _handle_rate_limit(resp)
    except Exception:
        pass
    return None


def get_last_fetch_sha(db_session, topic_id: str) -> Optional[str]:
    from app.models.topic import Topic
    topic = db_session.query(Topic).filter(Topic.id == topic_id).first()
    if topic and hasattr(topic, 'last_commit_sha'):
        return topic.last_commit_sha
    return None


def update_last_fetch_sha(db_session, topic_id: str, sha: str):
    from app.models.topic import Topic
    topic = db_session.query(Topic).filter(Topic.id == topic_id).first()
    if topic:
        topic.last_commit_sha = sha
        db_session.commit()


def should_sync_topic(db_session, topic_id: str, repo: str = "papers-we-love/papers-we-love") -> bool:
    last_sha = get_last_fetch_sha(db_session, topic_id)
    if not last_sha:
        return True
    current_sha = get_topic_commits(topic_id, repo)
    if not current_sha:
        return True
    return last_sha != current_sha


def retry_with_backoff(func, max_retries: int = 3, base_delay: float = 1.0):
    for attempt in range(max_retries):
        try:
            return func()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                wait = base_delay * (2 ** attempt)
                time.sleep(wait)
                continue
            if attempt == max_retries - 1:
                raise
        except (httpx.TimeoutException, httpx.ConnectError):
            if attempt == max_retries - 1:
                raise
            time.sleep(base_delay * (2 ** attempt))
    return None


def _handle_rate_limit(resp):
    remaining = resp.headers.get("X-RateLimit-Remaining", "0")
    if remaining == "0":
        reset_time = int(resp.headers.get("X-RateLimit-Reset", "0"))
        wait = max(reset_time - time.time() + 1, 10)
        if wait < 300:
            time.sleep(min(wait, 60))
