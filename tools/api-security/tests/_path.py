"""Put the library on sys.path for the suite. Imported first by every test module."""
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parent.parent
LIB = TOOL / "python"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))
