from sqlalchemy import inspect, text
from app.database.session import engine, Base


def _migrate_tables():
    inspector = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing_cols = {col["name"] for col in inspector.get_columns(table.name)}
        model_cols = {col.name for col in table.columns}
        missing_cols = model_cols - existing_cols
        if not missing_cols:
            continue
        with engine.begin() as conn:
            for col_name in missing_cols:
                col_obj = table.columns[col_name]
                col_type = col_obj.type.compile(engine.dialect)
                sql = f'ALTER TABLE {table.name} ADD COLUMN {col_name} {col_type}'
                if col_obj.default is not None:
                    default_val = col_obj.default.arg
                    if callable(default_val):
                        default_val = default_val({})
                    if isinstance(default_val, str):
                        sql += f" DEFAULT '{default_val}'"
                    else:
                        sql += f" DEFAULT {default_val}"
                conn.execute(text(sql))


def _init_memory_fts():
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS research_memories_fts "
            "USING fts5(title, body)"
        ))
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS research_memories_fts_insert "
            "AFTER INSERT ON research_memories BEGIN "
            "INSERT INTO research_memories_fts(rowid, title, body) "
            "VALUES (NEW.id, NEW.title, NEW.content); "
            "END"
        ))
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS research_memories_fts_update "
            "AFTER UPDATE ON research_memories BEGIN "
            "DELETE FROM research_memories_fts WHERE rowid = OLD.id; "
            "INSERT INTO research_memories_fts(rowid, title, body) "
            "VALUES (NEW.id, NEW.title, NEW.content); "
            "END"
        ))
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS research_memories_fts_delete "
            "AFTER DELETE ON research_memories BEGIN "
            "DELETE FROM research_memories_fts WHERE rowid = OLD.id; "
            "END"
        ))


def _init_chat_fts():
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS chat_messages_fts "
            "USING fts5(content)"
        ))
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS chat_messages_fts_insert "
            "AFTER INSERT ON chat_messages BEGIN "
            "INSERT INTO chat_messages_fts(rowid, content) "
            "VALUES (NEW.id, NEW.content); "
            "END"
        ))
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS chat_messages_fts_update "
            "AFTER UPDATE ON chat_messages BEGIN "
            "INSERT INTO chat_messages_fts(chat_messages_fts, rowid, content) "
            "VALUES ('delete', OLD.id, OLD.content); "
            "INSERT INTO chat_messages_fts(rowid, content) "
            "VALUES (NEW.id, NEW.content); "
            "END"
        ))
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS chat_messages_fts_delete "
            "AFTER DELETE ON chat_messages BEGIN "
            "INSERT INTO chat_messages_fts(chat_messages_fts, rowid, content) "
            "VALUES ('delete', OLD.id, OLD.content); "
            "END"
        ))


def _init_knowledge_fts():
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_documents_fts "
            "USING fts5(title, category, tags, authors)"
        ))
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS knowledge_documents_fts_insert "
            "AFTER INSERT ON knowledge_documents BEGIN "
            "INSERT INTO knowledge_documents_fts(rowid, title, category, tags, authors) "
            "VALUES (NEW.id, NEW.title, NEW.category, NEW.tags, NEW.authors); "
            "END"
        ))
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS knowledge_documents_fts_update "
            "AFTER UPDATE ON knowledge_documents BEGIN "
            "INSERT INTO knowledge_documents_fts(knowledge_documents_fts, rowid, title, category, tags, authors) "
            "VALUES ('delete', OLD.id, OLD.title, OLD.category, OLD.tags, OLD.authors); "
            "INSERT INTO knowledge_documents_fts(rowid, title, category, tags, authors) "
            "VALUES (NEW.id, NEW.title, NEW.category, NEW.tags, NEW.authors); "
            "END"
        ))
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS knowledge_documents_fts_delete "
            "AFTER DELETE ON knowledge_documents BEGIN "
            "INSERT INTO knowledge_documents_fts(knowledge_documents_fts, rowid, title, category, tags, authors) "
            "VALUES ('delete', OLD.id, OLD.title, OLD.category, OLD.tags, OLD.authors); "
            "END"
        ))


def init_db():
    import app.models  # noqa: F401 — ensure all models are registered with Base
    Base.metadata.create_all(bind=engine)
    _migrate_tables()
    _init_memory_fts()
    _register_builtin_skills()
    _init_chat_fts()
    _init_knowledge_fts()
    _register_builtin_rules()
    _create_default_workspace()


def _register_builtin_skills():
    from app.database.session import SessionLocal
    from app.models.skill import Skill
    from app.services.skill_manager import register_builtin_skills
    db = SessionLocal()
    try:
        count = db.query(Skill).count()
        if count == 0:
            register_builtin_skills(db)
    finally:
        db.close()


def _register_builtin_rules():
    from app.database.session import SessionLocal
    from app.models.agent_rule import AgentRule
    db = SessionLocal()
    try:
        count = db.query(AgentRule).count()
        if count == 0:
            rules = [
                AgentRule(name="academic-rigor", description="保持学术严谨性，不夸大、不简化", content="# 学术严谨性\n\n- 不要夸奖论文，只客观分析\n- 不要简化数学定义，保持原文的形式化严格性\n- 必须引用原文位置\n- 禁止使用通俗类比替代精确表述", category="behavior", priority=80, enabled=True, source="builtin", scope="global", conflict_resolution="highest_priority"),
                AgentRule(name="chinese-response", description="默认使用中文回复", content="# 中文回复\n\n- 默认使用中文回复用户\n- 专有名词和术语保留英文原文\n- 数学公式使用 LaTeX 格式", category="output", priority=70, enabled=True, source="builtin", scope="global", conflict_resolution="highest_priority"),
                AgentRule(name="safety-guard", description="安全防护规则", content="# 安全防护\n\n- 不执行任何可能损坏用户数据的操作\n- 不执行系统命令\n- 不访问未授权的资源\n- 敏感操作需要用户确认", category="safety", priority=100, enabled=True, source="builtin", scope="global", conflict_resolution="highest_priority"),
            ]
            for rule in rules:
                db.add(rule)
            db.commit()
    finally:
        db.close()


def _create_default_workspace():
    from app.database.session import SessionLocal
    from app.models.workspace import Workspace
    db = SessionLocal()
    try:
        existing = db.query(Workspace).filter(Workspace.is_default == True).first()
        if not existing:
            ws = Workspace(name="默认工作空间", slug="default", description="默认工作空间", is_default=True)
            db.add(ws)
            db.commit()
    finally:
        db.close()
