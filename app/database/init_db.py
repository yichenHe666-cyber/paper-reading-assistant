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


def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate_tables()
