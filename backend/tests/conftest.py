import random
import sys
from pathlib import Path

import pytest

# Ensure repository root is on sys.path for test discovery
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(autouse=True)
def deterministic_random_state():
    """The legacy demo fraud simulator uses unseeded randomness; keep tests repeatable."""
    random.seed(0)
