import json
import sys
from pathlib import Path


def check(totals):
    lines = 100 * totals["covered_lines"] / max(1, totals["num_statements"])
    branches = 100 * totals["covered_branches"] / max(1, totals["num_branches"])
    print(f"Linhas: {lines:.2f}% (mínimo 85%); branches: {branches:.2f}% (mínimo 80%)")
    return lines >= 85 and branches >= 80


if __name__ == "__main__":
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    sys.exit(0 if check(data["totals"]) else 1)
