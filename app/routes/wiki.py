from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.models.paper import Paper
from app.models.topic import Topic
from app.services.wiki_operations import ingest_paper, query_wiki, lint_wiki

router = APIRouter()


@router.post("/ingest")
def ingest(data: dict, db: Session = Depends(get_db)):
    paper_id = data.get("paper_id")
    if not paper_id:
        return {"error": "paper_id is required"}

    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        return {"error": "论文不存在"}

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
        result = ingest_paper(paper_dict)
        return result
    except Exception as e:
        return {
            "error": f"Ingest 失败: {str(e)}",
            "hint": "请检查 LLM_API_KEY 是否正确配置在 .env 文件中"
        }


@router.post("/query")
def query(data: dict):
    question = data.get("question", "")
    if not question:
        return {"error": "question is required"}
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
