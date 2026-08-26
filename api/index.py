import os
import sys

# Ensure project root directory is on Python search path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

os.environ.setdefault("VERCEL", "1")

from app.main import app
