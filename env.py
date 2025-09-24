from logging.config import fileConfig
import os
import importlib  # Added back to fix NameError

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

# Override sqlalchemy.url with environment variable
db_url = os.getenv("DATABASE_URL", "sqlite:///patients.db")
config.set_main_option("sqlalchemy.url", db_url)
