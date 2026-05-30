#!/usr/bin/env python3
"""CLI entry point — delegates to the agent orchestrator."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agent import run_agent


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    result = run_agent(query, filing_count=count)
    print(json.dumps({"paths": result["paths"], "evaluation": result["evaluation"]}, indent=2))


if __name__ == "__main__":
    main()
