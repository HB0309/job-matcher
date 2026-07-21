"""Standalone script invoked by the backend to run auto-apply in a separate process.

Usage (called by auto_apply.trigger_apply):
    python run_auto_apply.py <draft_id>

Runs independently of uvicorn — server reloads won't kill it.
"""
import sys
import logging
from pathlib import Path

log_file = Path(__file__).parent / "auto_apply.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file, encoding="utf-8"),
    ],
)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python run_auto_apply.py <draft_id>")
        sys.exit(1)

    draft_id = sys.argv[1]

    # Ensure app package is importable
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))

    from app.workers.auto_apply import _run
    _run(draft_id)
