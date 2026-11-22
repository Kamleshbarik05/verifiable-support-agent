"""
v1 Legacy Support Agent Package.
Preserves original v1 baseline behavior, intent classifier, deterministic guardrails,
retriever, and evaluation logic without modification.
"""

import sys
from pathlib import Path

# Ensure app/v1 is on sys.path so internal imports (from src..., from evaluation...) work seamlessly
V1_DIR = Path(__file__).resolve().parent
if str(V1_DIR) not in sys.path:
    sys.path.insert(0, str(V1_DIR))
