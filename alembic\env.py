from logging.config import fileConfig
import os
import importlib

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Dynamic import with debugging
print("Attempting to import main.py...")
try:
    main_module = importlib.import_module("main")
    print("main_module loaded:", dir(main_module))  # Debug: List available attributes
    PatientDB = getattr(main_module, "PatientDB", None)
    if PatientDB is None:
        raise ImportError("PatientDB not found in main.py. Available attributes:", dir(main_module))
    target_metadata = PatientDB.metadata
    print("PatientDB loaded successfully:", PatientDB)
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
