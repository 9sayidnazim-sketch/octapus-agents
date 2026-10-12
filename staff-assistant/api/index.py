import sys
from pathlib import Path

# Insert parent directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app
