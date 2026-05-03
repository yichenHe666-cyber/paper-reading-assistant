import hashlib
import json
from sqlalchemy.orm import Session
from app.models.llm_cache import LLMCache


def get_cache(db: Session, paper_id: str, call_type: str) -> dict:
    key = _make_key(paper_id, call_type)
    row = db.query(LLMCache).filter(LLMCache.cache_key == key).first()
    if row:
        row.hit_count = (row.hit_count or 0) + 1
        db.commit()
        return json.loads(row.result_json)
    return None


def set_cache(db: Session, paper_id: str, call_type: str, result: object, token_count: int = 0):
    from datetime import date

    key = _make_key(paper_id, call_type)
    existing = db.query(LLMCache).filter(LLMCache.cache_key == key).first()
    if existing:
        existing.result_json = json.dumps(result, ensure_ascii=False)
        existing.token_count = token_count
        existing.created_at = str(date.today())
    else:
        db.add(LLMCache(
            cache_key=key,
            result_json=json.dumps(result, ensure_ascii=False),
            token_count=token_count,
        ))
    db.commit()


def clear_cache_for_paper(db: Session, paper_id: str):
    db.query(LLMCache).filter(LLMCache.cache_key.like(f"{paper_id}%")).delete()
    db.commit()


def _make_key(paper_id: str, call_type: str) -> str:
    raw = f"{paper_id}|{call_type}"
    return hashlib.md5(raw.encode()).hexdigest()
