"""Run the data retention schedule once. Schedule it daily (see README)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import init_db  # noqa: E402
from app.retention import run  # noqa: E402

if __name__ == "__main__":
    init_db()
    print(run())
