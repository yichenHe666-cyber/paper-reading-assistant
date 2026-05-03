from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.note_snapshot import NoteSnapshot


def snapshot_before_write(db: Session, paper_id: str, obsidian_path: str, content: str) -> None:
    max_ver = db.query(func.max(NoteSnapshot.version)).filter(
        NoteSnapshot.paper_id == paper_id
    ).scalar() or 0
    snapshot = NoteSnapshot(
        paper_id=paper_id,
        obsidian_path=obsidian_path,
        content=content,
        version=max_ver + 1,
    )
    db.add(snapshot)
    db.commit()
    cleanup_old_snapshots(db, paper_id)


def get_snapshots(db: Session, paper_id: str) -> list:
    return db.query(NoteSnapshot).filter(
        NoteSnapshot.paper_id == paper_id
    ).order_by(NoteSnapshot.version.desc()).all()


def rollback_to_version(db: Session, paper_id: str, snapshot_id: int) -> str:
    target = db.query(NoteSnapshot).filter(NoteSnapshot.id == snapshot_id).first()
    if not target:
        return None
    max_ver = db.query(func.max(NoteSnapshot.version)).filter(
        NoteSnapshot.paper_id == paper_id
    ).scalar() or 0
    latest = db.query(NoteSnapshot).filter(
        NoteSnapshot.paper_id == paper_id,
        NoteSnapshot.version == max_ver,
    ).first()
    current_content = latest.content if latest else ""
    snapshot = NoteSnapshot(
        paper_id=paper_id,
        obsidian_path=target.obsidian_path,
        content=current_content,
        version=max_ver + 1,
    )
    db.add(snapshot)
    db.commit()
    cleanup_old_snapshots(db, paper_id)
    return target.content


def cleanup_old_snapshots(db: Session, paper_id: str, max_versions: int = 10):
    count = db.query(func.count(NoteSnapshot.id)).filter(
        NoteSnapshot.paper_id == paper_id
    ).scalar()
    if count > max_versions:
        oldest = db.query(NoteSnapshot).filter(
            NoteSnapshot.paper_id == paper_id
        ).order_by(NoteSnapshot.version.asc()).limit(count - max_versions).all()
        for snap in oldest:
            db.delete(snap)
        db.commit()
