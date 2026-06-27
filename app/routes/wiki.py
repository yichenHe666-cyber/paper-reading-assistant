from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.models.paper import Paper
from app.models.topic import Topic
from app.services.wiki_operations import ingest_document, ingest_paper, ingest_knowledge, query_wiki, lint_wiki

router = APIRouter()


@router.post("/ingest")
def ingest(data: dict, db: Session = Depends(get_db)):
    paper_id = data.get("paper_id")
    if not paper_id:
        raise HTTPException(status_code=400, detail="paper_id is required")

    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")

    topic = db.query(Topic).filter(Topic.id == paper.topic_id).first()

    paper_dict = {
        "id": paper.id,
        "title": paper.title,
        "authors": paper.authors,
        "year": paper.year,
        "topic_id": paper.topic_id,
        "subtopic": paper.subtopic,
        "abstract": paper.abstract,
        "topics_cn": topic.name_cn if topic else "",
    }

    try:
        result = ingest_document(paper_dict)
        return result
    except Exception as e:
        return {
            "error": f"Ingest 失败: {str(e)}",
            "hint": "请检查 LLM_API_KEY 是否正确配置在 .env 文件中"
        }


@router.post("/ingest-document")
def ingest_doc(data: dict):
    if not data.get("title"):
        raise HTTPException(status_code=400, detail="title is required")
    try:
        return ingest_document(data)
    except Exception as e:
        return {
            "error": f"Ingest 失败: {str(e)}",
            "hint": "请检查 LLM_API_KEY 是否正确配置在 .env 文件中"
        }


@router.post("/ingest-knowledge")
def ingest_know(data: dict):
    document = data.get("document", {})
    knowledge = data.get("knowledge", {})
    edges = data.get("edges", [])
    if not document.get("title"):
        raise HTTPException(status_code=400, detail="document.title is required")
    try:
        return ingest_knowledge(document, knowledge, edges)
    except Exception as e:
        return {
            "error": f"Ingest Knowledge 失败: {str(e)}",
            "hint": "请检查 LLM_API_KEY 是否正确配置在 .env 文件中"
        }


@router.post("/query")
def query(data: dict):
    question = data.get("question", "")
    if not question:
        raise HTTPException(status_code=400, detail="question is required")
    try:
        return query_wiki(question)
    except Exception as e:
        return {
            "error": f"Query 失败: {str(e)}",
            "hint": "请检查 LLM_API_KEY 是否正确配置在 .env 文件中"
        }


@router.post("/lint")
def lint():
    try:
        return lint_wiki()
    except Exception as e:
        return {
            "error": f"Lint 失败: {str(e)}",
            "hint": "请检查 LLM_API_KEY 是否正确配置在 .env 文件中"
        }
