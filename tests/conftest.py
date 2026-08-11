"""pytest configuration: make the project root importable.

Mirrors the rootDir/transform setup of the NestJS jest config.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))