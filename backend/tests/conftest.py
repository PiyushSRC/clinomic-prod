"""Pytest configuration and fixtures."""
import os
import sys

# Ensure backend is in path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Set test environment variables before any imports
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "clinomic_test")
os.environ.setdefault("APP_ENV", "dev")
os.environ.setdefault("DEMO_USERS_ENABLED", "true")
