import re
from pathlib import Path
from sqlalchemy.orm import Session
from app.config import get_settings
from app.models.paper import Paper


def scan_read_status(db: Session) -> dict:
    settings = get_settings()
    vault_path = Path(settings.obsidian_vault_path)
    paper_dir = vault_path / "01-论文精读"

    if not paper_dir.exists():
        return {"updated": 0, "total": 0, "new_read": 0, "error": "Vault 目录不存在"}

    updated = 0
    new_read = 0
    total = 0

    for md_file in paper_dir.rglob("*.md"):
        total += 1
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception:
            continue

        status_match = re.search(r"read_status:\s*(\S+)", content)
        if not status_match:
            continue
        status = status_match.group(1)

        title_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
        if not title_match:
            continue
        title = title_match.group(1).strip()

        paper = db.query(Paper).filter(Paper.title == title).first()
        if paper:
            if paper.read_status != status:
                paper.read_status = status
                paper.obsidian_path = str(md_file.relative_to(vault_path))
                paper.obsidian_synced = 1
                updated += 1
                if status == "已读":
                    new_read += 1

    db.commit()
    return {"updated": updated, "total": total, "new_read": new_read}
