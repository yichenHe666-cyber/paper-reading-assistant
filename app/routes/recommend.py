from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.services.paper_recommender import recommend_next_paper, recommend_by_confusion

router = APIRouter()


@router.post("/next")
def get_recommendation(data: dict, db: Session = Depends(get_db)):
    paper_id = data.get("paper_id")
    topic_id = data.get("topic_id")
    return recommend_next_paper(db, paper_id, topic_id)


@router.get("/difficulty-up")
def get_difficulty_upgrade(db: Session = Depends(get_db)):
    return recommend_by_confusion(db)
