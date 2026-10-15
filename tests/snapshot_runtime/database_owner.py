"""Own the actual database lock until normal process exit (without close)."""

import sys
from pathlib import Path

from craftreport.adapters.storage.database import Database

database = Database(Path(sys.argv[1]), "deployment-a")
Path(sys.argv[2]).write_text("ready", encoding="utf-8")
sys.stdin.readline()
