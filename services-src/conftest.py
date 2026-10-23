"""Make the shared module importable when pytest runs from services-src/."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "common"))
