import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database.session import engine, Base
from app.database.init_db import init_db
from app.config import get_settings
from app.services.sqlite_log_handler import setup_logger
from app.services.api_auth import APIKeyMiddleware
from app.routes import topics, papers, reading, obsidian, system, wiki, recommend, research, skills, memory, chat, workspace, sandbox, rules, knowledge

_logger = setup_logger("paper_reader")

_startup_time = None

# 允许的 CORS 来源。当包含通配 "*" 时，allow_credentials 必须为 False（CORS 规范要求）。
ALLOWED_ORIGINS = ["*"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── startup ──
    import datetime
    from app.config import get_settings
    global _startup_time
    settings = get_settings()
    _logger.info("系统启动 — 时间: %s, 日志级别: %s, 数据库: %s",
                 datetime.datetime.now().isoformat(), settings.log_level, settings.database_path)
    init_db()
    _logger.info("数据库初始化完成: %s", get_settings().database_path)
    t = threading.Thread(target=_background_init, daemon=True)
    t.start()
    _startup_time = datetime.datetime.now()
    yield
    # ── shutdown ──
    now = datetime.datetime.now()
    _logger.info("系统正常关闭 — 时间: %s", now.isoformat())


app = FastAPI(
    title="核动力科研牛马",
    description="从 Papers We Love 抓取经典 CS 论文，核动力科研牛马辅助阅读，一键写入 Obsidian",
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials="*" not in ALLOWED_ORIGINS,
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
app.include_router(skills.router, prefix="/api/skills", tags=["技能管理"])
app.include_router(memory.router, prefix="/api/memory", tags=["科研记忆"])
app.include_router(chat.router, prefix="/api/chat", tags=["智能体对话"])
app.include_router(workspace.router, prefix="/api/workspaces", tags=["工作空间"])
app.include_router(sandbox.router, prefix="/api/sandbox", tags=["沙盒"])
app.include_router(rules.router, prefix="/api/rules", tags=["规则管理"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["知识库"])


def _background_init():
    import time
    _start = time.time()
    try:
        from app.services.fts_manager import init_fts
        init_fts()
    except Exception:
        _logger.exception("后台初始化子任务失败")
    try:
        from app.services.backup import auto_backup_db
        auto_backup_db()
    except Exception:
        _logger.exception("后台初始化子任务失败")
    try:
        _auto_memory_enhancement()
    except Exception:
        _logger.exception("记忆增强自动任务异常")
    elapsed = time.time() - _start
    _logger.info("核动力科研牛马启动完成，耗时: %.1f 秒", elapsed)
    print("[READER] 核动力科研牛马 v0.3.0 启动完成 (含 AI 研究助手)")


def _auto_memory_enhancement():
    import time
    from app.database.session import SessionLocal
    from app.services.memory_vectorizer import memory_vectorizer
    from app.services.memory_observer import memory_observer
    from app.services.memory_reflector import memory_reflector
    from app.models.research_memory import ResearchMemory

    if memory_vectorizer._provider is None:
        _logger.info("嵌入服务不可用，跳过自动记忆增强")
        return

    _logger.info("开始自动记忆增强：嵌入回填...")
    db = SessionLocal()
    try:
        result = memory_vectorizer.backfill_embeddings(db)
        _logger.info("嵌入回填完成：处理 %d 条，失败 %d 条", result.get("processed", 0), result.get("failed", 0))
    except Exception:
        _logger.exception("嵌入回填异常")
    finally:
        db.close()

    _logger.info("开始自动记忆增强：观察合并...")
    db = SessionLocal()
    try:
        result = memory_observer.run_consolidation_cycle(db)
        _logger.info("观察合并完成：合并 %d 个实体，失败 %d 个", result.get("consolidated", 0), result.get("failed", 0))
    except Exception:
        _logger.exception("观察合并异常")
    finally:
        db.close()

    active_count = 0
    db = SessionLocal()
    try:
        active_count = db.query(ResearchMemory).filter(ResearchMemory.is_active == True).count()
    finally:
        db.close()

    if active_count > 20:
        _logger.info("开始自动记忆增强：反思推理（记忆数 %d > 20）...", active_count)
        db = SessionLocal()
        try:
            from app.models.memory_entity import MemoryEntity
            from sqlalchemy import func as sa_func
            top_entities = (
                db.query(MemoryEntity.name, sa_func.count(MemoryEntity.id).label("cnt"))
                .group_by(MemoryEntity.name)
                .order_by(sa_func.count(MemoryEntity.id).desc())
                .limit(3)
                .all()
            )
            for entity_name, _ in top_entities:
                try:
                    result = memory_reflector.reflect(db, query=entity_name, entity_name=entity_name)
                    if result.get("insights") or result.get("contradictions"):
                        memory_reflector.save_reflection_as_memory(
                            db, result, query=entity_name, entity_name=entity_name, auto=True
                        )
                        _logger.info("自动反思完成：实体 %s", entity_name)
                    time.sleep(2)
                except Exception:
                    _logger.exception("自动反思异常（实体 %s）", entity_name)
        except Exception:
            _logger.exception("自动反思整体异常")
        finally:
            db.close()
    else:
        _logger.info("记忆数量不足 20 条（当前 %d），跳过自动反思", active_count)

    _logger.info("自动记忆增强全部完成")


@app.get("/")
def root():
    return {"app": "核动力科研牛马", "version": "0.3.0", "docs": "/docs", "features": ["论文精读", "AI研究助手"]}


def get_logger():
    return _logger
