import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

# main.py har top-level google-imports som ikke trengs for å teste rene funksjoner
for _mod in [
    "google",
    "google.oauth2",
    "google.oauth2.service_account",
    "googleapiclient",
    "googleapiclient.discovery",
]:
    sys.modules.setdefault(_mod, MagicMock())
