import sqlite3
from pathlib import Path

DB_PATH = Path("data/reading_assistant.db")


def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(papers)")
    columns = [col[1] for col in cursor.fetchall()]

    if "doi" not in columns:
        cursor.execute("ALTER TABLE papers ADD COLUMN doi TEXT DEFAULT ''")
        conn.commit()
        print("✓ 已添加 doi 列到 papers 表")
    else:
        print("✓ doi 列已存在，跳过")

    cursor.execute("SELECT COUNT(*) FROM papers WHERE doi IS NULL OR doi = ''")
    missing_doi = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM papers")
    total = cursor.fetchone()[0]
    print(f"  当前DOI缺失: {missing_doi}/{total} ({missing_doi/total*100:.1f}%)")
    print(f"  提示: 运行 python scripts/enrich_paper_metadata.py 来补充DOI信息")

    conn.close()


if __name__ == "__main__":
    migrate()
