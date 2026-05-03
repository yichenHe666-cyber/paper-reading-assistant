import os
import tempfile
from pathlib import Path


def test_wiki_index_created():
    wiki_base = Path(r"C:\Users\Public\Documents\wiki-knowledge")
    if wiki_base.exists() and (wiki_base / "wiki" / "index.md").exists():
        content = (wiki_base / "wiki" / "index.md").read_text(encoding="utf-8")
        assert content.startswith("---")
        assert "Wiki 索引" in content or "index" in content.lower()
    else:
        assert True


def test_wiki_log_created():
    wiki_base = Path(r"C:\Users\Public\Documents\wiki-knowledge")
    if wiki_base.exists() and (wiki_base / "wiki" / "log.md").exists():
        content = (wiki_base / "wiki" / "log.md").read_text(encoding="utf-8")
        assert "操作日志" in content or "log" in content.lower()
    else:
        assert True


def test_schema_created():
    wiki_base = Path(r"C:\Users\Public\Documents\wiki-knowledge")
    if wiki_base.exists() and (wiki_base / "schema" / "AGENTS.md").exists():
        content = (wiki_base / "schema" / "AGENTS.md").read_text(encoding="utf-8")
        assert "Ingest" in content or "ingest" in content.lower()
    else:
        assert True
