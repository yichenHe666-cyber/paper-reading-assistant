import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.services.obsidian_writer import ObsidianWriter
from app.services.vault_scanner import scan_read_status
from app.services.snapshot_manager import get_snapshots, rollback_to_version
from app.models.paper import Paper
from app.models.topic import Topic
from pathlib import Path
from app.config import get_settings

router = APIRouter()


@router.get("/status")
def get_vault_status():
    settings = get_settings()
    vault = Path(settings.obsidian_vault_path)
    stats = {"vault_path": str(vault), "exists": vault.exists()}
    if vault.exists():
        paper_dir = vault / "01-论文精读"
        concept_dir = vault / "02-概念卡片"
        vocab_dir = vault / "03-专业词汇"
        stats["paper_files"] = len(list(paper_dir.rglob("*.md"))) if paper_dir.exists() else 0
        stats["concept_files"] = len(list(concept_dir.rglob("*.md"))) if concept_dir.exists() else 0
        stats["vocab_files"] = len(list(vocab_dir.rglob("*.md"))) if vocab_dir.exists() else 0
    return stats


@router.post("/write-paper-note")
def write_paper_note(data: dict, db: Session = Depends(get_db)):
    paper_id = data.get("paper_id")
    note_draft = data.get("note_draft", "")
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        return {"error": "论文不存在"}
    paper_dict = {
        "id": paper.id, "title": paper.title, "authors": paper.authors,
        "year": paper.year, "topic_id": paper.topic_id, "subtopic": paper.subtopic,
        "venue": paper.venue, "pdf_url": paper.pdf_url, "community_notes_url": paper.community_notes_url,
        "abstract": paper.abstract, "difficulty": paper.difficulty, "tags": paper.tags,
        "concepts": paper.concepts,
    }
    writer = ObsidianWriter()
    try:
        path = writer.write_paper_note(paper_dict, note_draft)
        paper.obsidian_path = path
        paper.obsidian_synced = 1
        db.commit()
        logging.getLogger("paper_reader").info(f"[obsidian] Wrote paper note: {path}")
        return {"status": "ok", "path": path}
    except Exception as e:
        return {"error": str(e)}


@router.post("/write-all")
def write_all_to_obsidian(data: dict, db: Session = Depends(get_db)):
    paper_id = data.get("paper_id")
    note_draft = data.get("note_draft", "")
    concept_cards = data.get("concept_cards", [])
    vocabulary_md = data.get("vocabulary_md", "")

    if isinstance(concept_cards, dict):
        concept_cards = [
            {"name": k, "name_en": k, "definition": str(v), "category": "5C",
             "related_concepts": [], "related_papers": [], "difficulty": "中等",
             "context_in_paper": "", "evolution_line": "", "one_sentence": str(v),
             "formal_definition": str(v)}
            for k, v in concept_cards.items()
        ]
    if not isinstance(concept_cards, list):
        concept_cards = []
    concept_cards = [c for c in concept_cards if isinstance(c, dict)]

    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        return {"error": "论文不存在"}
    paper_dict = {
        "id": paper.id, "title": paper.title, "authors": paper.authors,
        "year": paper.year, "topic_id": paper.topic_id, "subtopic": paper.subtopic,
        "venue": paper.venue, "pdf_url": paper.pdf_url, "community_notes_url": paper.community_notes_url,
        "abstract": paper.abstract, "difficulty": paper.difficulty, "tags": paper.tags,
        "concepts": paper.concepts,
    }
    writer = ObsidianWriter()
    try:
        result = writer.write_all(paper_dict, note_draft, concept_cards, vocabulary_md)
        paper.obsidian_path = result["paper_path"]
        paper.obsidian_synced = 1
        db.commit()
        logging.getLogger("paper_reader").info(f"[obsidian] Wrote all for paper: {paper_id}")
        return {"status": "ok", **result}
    except Exception as e:
        import traceback
        logging.getLogger("paper_reader").error(f"[obsidian] write-all failed: {traceback.format_exc()}")
        return {"error": str(e)}


@router.post("/write-concept-card")
def write_concept_card(data: dict):
    writer = ObsidianWriter()
    try:
        path = writer.write_concept_card(data)
        return {"status": "ok", "path": path}
    except Exception as e:
        return {"error": str(e)}


@router.post("/scan-vault")
def scan_vault(db: Session = Depends(get_db)):
    try:
        result = scan_read_status(db)
        return {"status": "ok", **result}
    except Exception as e:
        return {"error": str(e)}


@router.post("/generate-dashboard")
def generate_dashboard():
    writer = ObsidianWriter()
    try:
        path = writer.write_dashboard()
        return {"status": "ok", "path": path}
    except Exception as e:
        return {"error": str(e)}


@router.get("/snapshots/{paper_id:path}")
def list_snapshots(paper_id: str, db: Session = Depends(get_db)):
    snapshots = get_snapshots(db, paper_id)
    return {
        "paper_id": paper_id,
        "snapshots": [
            {
                "id": s.id,
                "version": s.version,
                "obsidian_path": s.obsidian_path,
                "created_at": s.created_at,
            }
            for s in snapshots
        ],
    }


@router.post("/rollback")
def rollback_snapshot(data: dict, db: Session = Depends(get_db)):
    snapshot_id = data.get("snapshot_id")
    if not snapshot_id:
        return {"error": "snapshot_id is required"}

    paper = db.query(Paper).filter(Paper.id == data.get("paper_id")).first()
    if not paper:
        return {"error": "论文不存在"}

    old_content = rollback_to_version(db, paper.id, snapshot_id)
    if old_content is None:
        return {"error": "快照不存在"}

    settings = get_settings()
    obsidian_path = paper.obsidian_path
    if not obsidian_path:
        return {"error": "论文未关联 Obsidian 文件"}

    file_path = Path(settings.obsidian_vault_path) / obsidian_path
    try:
        file_path.write_text(old_content, encoding="utf-8")
        logging.getLogger("paper_reader").info(f"[obsidian] Rollback to snapshot {snapshot_id} for {paper.id}")
        return {"status": "ok", "path": str(file_path)}
    except Exception as e:
        return {"error": str(e)}
