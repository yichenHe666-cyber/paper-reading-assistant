import shutil
import zipfile
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("paper_reader")


DB_PATH = Path("data/reading_assistant.db")
BACKUP_DIR = Path("data/backups")
OBSIDIAN_PATHS = {
    "01-论文精读": Path(r"C:\Users\Public\Documents\01-论文精读"),
    "02-概念卡片": Path(r"C:\Users\Public\Documents\02-概念卡片"),
    "03-专业词汇": Path(r"C:\Users\Public\Documents\03-专业词汇"),
}
WIKI_PATH = Path(r"C:\Users\Public\Documents\wiki-knowledge")


def auto_backup_db():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if not DB_PATH.exists():
        return None
    today = datetime.now().strftime("%Y%m%d")
    backup_file = BACKUP_DIR / f"reading_assistant_{today}.db"
    if not backup_file.exists():
        shutil.copy2(DB_PATH, backup_file)
        logger.info("文件创建: %s", backup_file)
    all_backups = sorted(BACKUP_DIR.glob("reading_assistant_*.db"))
    for old in all_backups[:-7]:
        old.unlink()
    return str(backup_file)


def export_all_to_zip() -> str:
    export_dir = Path("data/exports")
    export_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = export_dir / f"reading_assistant_{timestamp}.zip"

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        if DB_PATH.exists():
            zf.write(DB_PATH, "reading_assistant.db")

        for prefix, vault_dir in OBSIDIAN_PATHS.items():
            if vault_dir.exists():
                for f in vault_dir.rglob("*.md"):
                    zf.write(f, f"obsidian/{prefix}/{f.relative_to(vault_dir)}")

        if WIKI_PATH.exists():
            for f in WIKI_PATH.rglob("*.md"):
                zf.write(f, f"wiki/{f.relative_to(WIKI_PATH)}")

    size_mb = round(zip_path.stat().st_size / 1024 / 1024, 1)
    return str(zip_path.resolve())
