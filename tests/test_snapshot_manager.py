import os
import tempfile
from pathlib import Path


def test_snapshot_creation(monkeypatch):
    from app.database.session import SessionLocal, Base, engine

    Base.metadata.create_all(bind=engine)

    from app.services.snapshot_manager import snapshot_before_write, get_snapshots, cleanup_old_snapshots
    db = SessionLocal()

    paper_id = "test/paper"
    path = "test/path.md"
    content = "version 1 content"

    snapshot_before_write(db, paper_id, path, content)

    snapshots = get_snapshots(db, paper_id)
    assert len(snapshots) == 1
    assert snapshots[0].version == 1

    snapshot_before_write(db, paper_id, path, "version 2 content")
    snapshots = get_snapshots(db, paper_id)
    assert len(snapshots) == 2

    db.close()


def test_cleanup_max_versions(monkeypatch):
    from app.database.session import SessionLocal, Base, engine

    Base.metadata.create_all(bind=engine)

    from app.services.snapshot_manager import snapshot_before_write, get_snapshots, cleanup_old_snapshots
    db = SessionLocal()

    paper_id = "test/cleanup"
    for i in range(12):
        snapshot_before_write(db, paper_id, f"path/{i}", f"content {i}")

    snapshots_before = get_snapshots(db, paper_id)
    cleanup_old_snapshots(db, paper_id, max_versions=10)
    snapshots_after = get_snapshots(db, paper_id)

    assert len(snapshots_after) == 10

    db.close()
