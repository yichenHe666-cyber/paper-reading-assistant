from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database.session import engine, Base
from app.database.init_db import init_db
from app.services.sqlite_log_handler import setup_logger
from app.services.api_auth import APIKeyMiddleware
from app.routes import topics, papers, reading, obsidian, system, wiki, recommend, research

_logger = setup_logger("paper_reader")

app = FastAPI(
    title="经典论文精读助手",
    description="从 Papers We Love 抓取经典 CS 论文，LLM 辅助阅读，一键写入 Obsidian",
    version="0.1.1",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(APIKeyMiddleware)

app.include_router(topics.router, prefix="/api/topics", tags=["主题"])
app.include_router(papers.router, prefix="/api/papers", tags=["论文"])
app.include_router(reading.router, prefix="/api/reading", tags=["阅读辅助"])
app.include_router(obsidian.router, prefix="/api/obsidian", tags=["Obsidian"])
app.include_router(system.router, prefix="/api/system", tags=["系统"])
app.include_router(wiki.router, prefix="/api/wiki", tags=["Wiki"])
app.include_router(recommend.router, prefix="/api/recommend", tags=["推荐"])
app.include_router(research.router, prefix="/api/research", tags=["AI研究助手"])


@app.on_event("startup")
def on_startup():
    init_db()
    try:
        from app.services.fts_manager import init_fts
        init_fts()
    except Exception:
        pass
    try:
        from app.services.backup import auto_backup_db
        auto_backup_db()
    except Exception:
        pass
    _logger.info("经典论文精读助手启动完成")
    print("[READER] 经典论文精读助手 v0.2.0 启动完成 (含 AI 研究助手)")


@app.get("/")
def root():
    return {"app": "经典论文精读助手", "version": "0.2.0", "docs": "/docs", "features": ["论文精读", "AI研究助手"]}


def get_logger():
    return _logger
