from sqlalchemy import text
from app.database.session import SessionLocal, engine


def init_fts():
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS papers_fts"))
        conn.execute(text("""
            CREATE VIRTUAL TABLE papers_fts USING fts5(
                title, abstract, authors, content=papers, content_rowid=rowid
            )
        """))
        conn.execute(text("""
            INSERT INTO papers_fts(rowid, title, abstract, authors)
            SELECT rowid, title, COALESCE(abstract,''), COALESCE(authors,'') FROM papers
        """))
        for trigger in ['papers_ai', 'papers_ad', 'papers_au']:
            conn.execute(text(f"DROP TRIGGER IF EXISTS {trigger}"))
        conn.execute(text("""
            CREATE TRIGGER papers_ai AFTER INSERT ON papers BEGIN
                INSERT INTO papers_fts(rowid, title, abstract, authors)
                VALUES (new.rowid, new.title, COALESCE(new.abstract,''), COALESCE(new.authors,''));
            END
        """))
        conn.execute(text("""
            CREATE TRIGGER papers_ad AFTER DELETE ON papers BEGIN
                INSERT INTO papers_fts(papers_fts, rowid, title, abstract, authors)
                VALUES ('delete', old.rowid, old.title, old.abstract, old.authors);
            END
        """))
        conn.execute(text("""
            CREATE TRIGGER papers_au AFTER UPDATE ON papers BEGIN
                INSERT INTO papers_fts(papers_fts, rowid, title, abstract, authors)
                VALUES ('delete', old.rowid, old.title, old.abstract, old.authors);
                INSERT INTO papers_fts(rowid, title, abstract, authors)
                VALUES (new.rowid, new.title, COALESCE(new.abstract,''), COALESCE(new.authors,''));
            END
        """))
        conn.commit()


def search_papers_fts(query: str, limit: int = 20):
    try:
        terms = query.strip().replace('"', '').replace("'", "")
        fts_query = " AND ".join(terms.split()) if terms else terms
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT rowid FROM papers_fts WHERE papers_fts MATCH :q ORDER BY rank LIMIT :lim"),
                {"q": fts_query, "lim": limit}
            )
            rowids = [r[0] for r in result.fetchall()]
        results = []
        for rid in rowids:
            with engine.connect() as conn:
                r = conn.execute(
                    text("SELECT id, title, authors, year, topic_id, difficulty, read_status, abstract FROM papers WHERE rowid = :rid"),
                    {"rid": rid}
                ).fetchone()
            if r:
                results.append({
                    "id": r[0], "title": r[1], "authors": r[2], "year": r[3],
                    "topic_id": r[4], "difficulty": r[5], "read_status": r[6],
                    "abstract": (r[7] or "")[:200],
                })
        if results:
            return {"query": query, "results": results, "engine": "fts5"}
    except Exception:
        pass

    db = SessionLocal()
    try:
        from app.models.paper import Paper
        from sqlalchemy import or_
        pattern = f"%{query}%"
        papers = db.query(Paper).filter(or_(
            Paper.title.like(pattern), Paper.abstract.like(pattern), Paper.authors.like(pattern)
        )).limit(limit).all()
        return {"query": query, "results": [
            {"id": p.id, "title": p.title, "authors": p.authors, "year": p.year,
             "topic_id": p.topic_id, "difficulty": p.difficulty, "read_status": p.read_status,
             "abstract": (p.abstract or "")[:200]} for p in papers
        ], "engine": "like_fallback"}
    finally:
        db.close()
