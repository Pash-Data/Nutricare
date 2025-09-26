from logging.config import fileConfig
import os

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Dynamic import to ensure PatientDB is loaded
try:
    main_module = importlib.import_module("main")
    PatientDB = getattr(main_module, "PatientDB", None)
    if PatientDB is None:
        raise ImportError("PatientDB not found in main.py. Verify file content.")
    target_metadata = PatientDB.metadata
except ImportError as e:
    raise ImportError(f"Failed to import PatientDB from main.py: {str(e)}")

# Alembic Config
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url with environment variable (fallback to SQLite for local)
db_url = os.getenv("DATABASE_URL", "sqlite:///patients.db")
config.set_main_option("sqlalchemy.url", db_url)

# Target metadata (from your SQLModel)
target_metadata = PatientDB.metadata

def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        url=os.getenv("DATABASE_URL", "sqlite:///patients.db"),  # Consistent fallback
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()