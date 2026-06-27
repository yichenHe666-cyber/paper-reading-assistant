import hashlib
import json
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy import or_, text as sa_text
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.models.knowledge_document import KnowledgeDocument
from app.models.knowledge_edge import KnowledgeEdge
from app.services.knowledge_engine import knowledge_engine
from app.services.document_parser import DocumentParser
from app.services.wiki_operations import lint_wiki, query_wiki
from app.config import get_settings

router = APIRouter()

_document_parser = DocumentParser()

SUPPORTED_EXTENSIONS = {".pdf", ".md", ".markdown", ".epub", ".docx", ".doc", ".tex", ".latex"}


def _compute_sha256(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def _detect_format(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    fmt_map = {
        ".pdf": "pdf",
        ".md": "markdown",
        ".markdown": "markdown",
        ".epub": "epub",
        ".docx": "docx",
        ".doc": "docx",
        ".tex": "latex",
        ".latex": "latex",
    }
    return fmt_map.get(ext, "")


def _serialize_document(doc: KnowledgeDocument) -> dict:
    tags = []
    if doc.tags:
        try:
            tags = json.loads(doc.tags)
        except (json.JSONDecodeError, TypeError):
            tags = [t.strip() for t in doc.tags.split(",") if t.strip()]
    return {
        "id": doc.id,
        "title": doc.title,
        "file_name": doc.file_name,
        "file_path": doc.file_path,
        "file_format": doc.file_format,
        "file_size_bytes": doc.file_size_bytes,
        "content_hash": doc.content_hash,
        "category": doc.category,
        "tags": tags,
        "authors": doc.authors,
        "language": doc.language,
        "page_count": doc.page_count,
        "section_count": doc.section_count,
        "parse_status": doc.parse_status,
        "parse_errors": doc.parse_errors,
        "wiki_status": doc.wiki_status,
        "knowledge_extracted": doc.knowledge_extracted,
        "source_type": doc.source_type,
        "source_url": doc.source_url,
        "related_paper_id": doc.related_paper_id,
        "is_active": doc.is_active,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
    }


def _save_and_create_doc(
    file_bytes: bytes,
    file_name: str,
    category: str,
    tags: list,
    db: Session,
) -> dict:
    settings = get_settings()
    file_format = _detect_format(file_name)
    if not file_format:
        return {"file_name": file_name, "status": "unsupported_format"}

    content_hash = _compute_sha256(file_bytes)

    if settings.knowledge_dedup_enabled:
        existing = db.query(KnowledgeDocument).filter(
            KnowledgeDocument.content_hash == content_hash,
            KnowledgeDocument.is_active == True,
        ).first()
        if existing:
            return {"document_id": existing.id, "file_name": file_name, "status": "duplicate"}

    raw_dir = Path(settings.knowledge_base_path) / "raw" / (category or "default")
    raw_dir.mkdir(parents=True, exist_ok=True)

    dest_path = raw_dir / file_name
    counter = 1
    while dest_path.exists():
        stem = Path(file_name).stem
        suffix = Path(file_name).suffix
        dest_path = raw_dir / f"{stem}_{counter}{suffix}"
        counter += 1

    dest_path.write_bytes(file_bytes)

    tags_json = json.dumps(tags, ensure_ascii=False) if tags else "[]"

    doc = KnowledgeDocument(
        title=Path(file_name).stem,
        file_name=file_name,
        file_path=str(dest_path),
        file_format=file_format,
        file_size_bytes=len(file_bytes),
        content_hash=content_hash,
        category=category or "default",
        tags=tags_json,
        source_type="upload",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    return {"document_id": doc.id, "file_name": file_name, "status": "uploaded"}


@router.post("/upload")
async def upload_documents(
    files: list[UploadFile] = File(...),
    category: str = Form("default"),
    tags: str = Form(""),
    db: Session = Depends(get_db),
):
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    results = []

    for upload_file in files:
        try:
            file_bytes = await upload_file.read()
            result = _save_and_create_doc(file_bytes, upload_file.filename, category, tag_list, db)
            if result.get("status") == "uploaded" and result.get("document_id"):
                doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == result["document_id"]).first()
                if doc:
                    doc.parse_status = "parsing"
                    db.commit()
                    try:
                        parsed = _document_parser.parse(doc.file_path, format_hint=doc.file_format)
                        if parsed.parse_status == "success":
                            doc.parse_status = "parsed"
                            doc.section_count = len(parsed.sections) if parsed.sections else None
                        else:
                            doc.parse_status = "failed"
                            doc.parse_errors = "\n".join(parsed.parse_errors) if parsed.parse_errors else None
                        db.commit()
                    except Exception:
                        doc.parse_status = "failed"
                        doc.parse_errors = "解析异常"
                        db.commit()
            results.append(result)
        except Exception as e:
            results.append({"file_name": upload_file.filename, "status": "error", "message": str(e)})

    return {"results": results}


@router.post("/batch-import")
def batch_import(data: dict, db: Session = Depends(get_db)):
    import_path = data.get("path", "")
    category = data.get("category", "default")
    tags = data.get("tags", [])

    if not import_path:
        raise HTTPException(status_code=400, detail="path 为必填项")

    source = Path(import_path)
    if not source.exists():
        raise HTTPException(status_code=400, detail=f"路径不存在: {import_path}")

    file_list = []

    if source.is_file() and source.suffix.lower() == ".zip":
        try:
            with zipfile.ZipFile(source, "r") as zf:
                for name in zf.namelist():
                    if Path(name).suffix.lower() in SUPPORTED_EXTENSIONS and not name.startswith("__MACOSX"):
                        file_bytes = zf.read(name)
                        file_list.append((Path(name).name, file_bytes))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"ZIP 解压失败: {str(e)}")
    elif source.is_dir():
        for ext in SUPPORTED_EXTENSIONS:
            for f in source.rglob(f"*{ext}"):
                try:
                    file_bytes = f.read_bytes()
                    file_list.append((f.name, file_bytes))
                except Exception:
                    pass
    else:
        if source.suffix.lower() in SUPPORTED_EXTENSIONS:
            try:
                file_bytes = source.read_bytes()
                file_list.append((source.name, file_bytes))
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"读取文件失败: {str(e)}")
        else:
            raise HTTPException(status_code=400, detail="不支持的文件格式")

    imported = 0
    skipped = 0
    failed = 0

    for file_name, file_bytes in file_list:
        try:
            result = _save_and_create_doc(file_bytes, file_name, category, tags, db)
            status = result.get("status", "")
            if status == "uploaded":
                imported += 1
            elif status == "duplicate":
                skipped += 1
            else:
                failed += 1
        except Exception:
            failed += 1

    return {"imported": imported, "skipped": skipped, "failed": failed}


@router.get("/documents")
def list_documents(
    category: str = None,
    tags: str = None,
    format: str = None,
    parse_status: str = None,
    wiki_status: str = None,
    q: str = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    query = db.query(KnowledgeDocument).filter(KnowledgeDocument.is_active == True)

    if category:
        query = query.filter(KnowledgeDocument.category == category)
    if format:
        query = query.filter(KnowledgeDocument.file_format == format)
    if parse_status:
        query = query.filter(KnowledgeDocument.parse_status == parse_status)
    if wiki_status:
        query = query.filter(KnowledgeDocument.wiki_status == wiki_status)

    tag_list = None
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        if tag_list:
            tag_filters = [KnowledgeDocument.tags.contains(tag) for tag in tag_list]
            query = query.filter(or_(*tag_filters))

    if q:
        try:
            fts_result = db.execute(
                sa_text("SELECT rowid FROM knowledge_documents_fts WHERE knowledge_documents_fts MATCH :q"),
                {"q": q},
            ).fetchall()
            matching_ids = [row[0] for row in fts_result]
            if matching_ids:
                query = query.filter(KnowledgeDocument.id.in_(matching_ids))
            else:
                query = query.filter(KnowledgeDocument.title.contains(q))
        except Exception:
            query = query.filter(KnowledgeDocument.title.contains(q))

    total = query.count()
    docs = query.order_by(KnowledgeDocument.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "documents": [_serialize_document(d) for d in docs],
        "total": total,
    }


@router.get("/documents/{document_id}")
def get_document(document_id: int, db: Session = Depends(get_db)):
    doc = db.query(KnowledgeDocument).filter(
        KnowledgeDocument.id == document_id,
        KnowledgeDocument.is_active == True,
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    return _serialize_document(doc)


@router.delete("/documents/{document_id}")
def delete_document(document_id: int, db: Session = Depends(get_db)):
    doc = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    doc.is_active = False
    db.commit()
    return {"status": "ok", "document_id": document_id, "is_active": False}


@router.post("/query")
def query_knowledge(data: dict, db: Session = Depends(get_db)):
    question = data.get("question", "")
    max_results = data.get("max_results", 10)

    if not question:
        raise HTTPException(status_code=400, detail="question 为必填项")

    try:
        context = knowledge_engine.query_for_context(question)
        wiki_result = query_wiki(question)

        answer = ""
        sources = []
        confidence = "low"

        if isinstance(wiki_result, dict) and wiki_result.get("status") == "ok":
            result_data = wiki_result.get("result", {})
            answer = result_data.get("answer", "")
            sources = result_data.get("sources_used", [])
            confidence = result_data.get("confidence", "low")

        if context and not answer:
            answer = context
            confidence = "medium"

        return {
            "answer": answer,
            "sources": sources,
            "confidence": confidence,
            "context_length": len(context) if context else 0,
        }
    except Exception as e:
        return {"answer": "", "sources": [], "confidence": "error", "message": str(e)}


@router.get("/graph")
def get_graph(
    concept: str = None,
    depth: int = 2,
    relation_type: str = None,
):
    try:
        result = knowledge_engine.get_graph_data(
            concept=concept,
            depth=depth,
            relation_type=relation_type,
        )
        return {
            "nodes": result.get("nodes", []),
            "edges": result.get("links", []),
            "total_nodes": result.get("total_nodes", 0),
            "total_edges": result.get("total_links", 0),
        }
    except Exception as e:
        return {"nodes": [], "edges": [], "message": str(e)}


@router.post("/graph/edges")
def create_edge(data: dict, db: Session = Depends(get_db)):
    source_concept = data.get("source_concept")
    target_concept = data.get("target_concept")
    relation_type = data.get("relation_type")

    if not source_concept or not target_concept or not relation_type:
        raise HTTPException(status_code=400, detail="source_concept, target_concept, relation_type 为必填项")

    try:
        edge = KnowledgeEdge(
            source_concept=source_concept,
            target_concept=target_concept,
            relation_type=relation_type,
            strength=data.get("strength", 0.5),
            evidence=data.get("evidence", ""),
            source_document_id=data.get("source_document_id"),
            is_verified=False,
        )
        db.add(edge)
        db.commit()
        db.refresh(edge)

        return {
            "id": edge.id,
            "source_concept": edge.source_concept,
            "target_concept": edge.target_concept,
            "relation_type": edge.relation_type,
            "strength": edge.strength,
            "evidence": edge.evidence,
            "source_document_id": edge.source_document_id,
            "is_verified": edge.is_verified,
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/graph/edges/{edge_id}")
def update_edge(edge_id: int, data: dict, db: Session = Depends(get_db)):
    edge = db.query(KnowledgeEdge).filter(KnowledgeEdge.id == edge_id).first()
    if not edge:
        raise HTTPException(status_code=404, detail="边不存在")

    try:
        if "relation_type" in data:
            edge.relation_type = data["relation_type"]
        if "strength" in data:
            edge.strength = data["strength"]
        if "is_verified" in data:
            edge.is_verified = data["is_verified"]
        db.commit()
        db.refresh(edge)

        return {
            "id": edge.id,
            "source_concept": edge.source_concept,
            "target_concept": edge.target_concept,
            "relation_type": edge.relation_type,
            "strength": edge.strength,
            "is_verified": edge.is_verified,
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/graph/edges/{edge_id}")
def delete_edge(edge_id: int, db: Session = Depends(get_db)):
    edge = db.query(KnowledgeEdge).filter(KnowledgeEdge.id == edge_id).first()
    if not edge:
        raise HTTPException(status_code=404, detail="边不存在")

    try:
        db.delete(edge)
        db.commit()
        return {"status": "ok", "edge_id": edge_id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
def knowledge_stats():
    try:
        return knowledge_engine.get_stats()
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/extract/{document_id}")
def extract_knowledge(document_id: int, db: Session = Depends(get_db)):
    doc = db.query(KnowledgeDocument).filter(
        KnowledgeDocument.id == document_id,
        KnowledgeDocument.is_active == True,
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    try:
        result = knowledge_engine.extract(document_id)
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/lint")
def lint():
    try:
        return lint_wiki()
    except Exception as e:
        return {"status": "error", "message": str(e)}
