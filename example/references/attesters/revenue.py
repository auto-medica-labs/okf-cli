"""Attester for the Revenue computation.

Checks that the executed SQL matches the sanctioned computation
with the supplied parameters bound in.

Receipt shape: {job_id: str, executed_sql: str, result: list[dict]}
"""

import json
import re
import sys


def _normalize(sql: str) -> str:
    """Collapse whitespace for comparison."""
    return " ".join(sql.strip().split())


def attest(receipt: dict, params: dict) -> dict:
    """Return {ok: bool, reason: str}."""
    executed = _normalize(receipt.get("executed_sql", ""))

    # The sanctioned query for this parameter set
    year = params.get("year")
    expected = _normalize(
        f"SELECT SUM(amount) AS revenue "
        f"FROM finance.recognized_revenue "
        f"WHERE fiscal_year = {year}"
    )

    if executed != expected:
        return {
            "ok": False,
            "reason": f"SQL mismatch.\n  Expected: {expected}\n  Got:      {executed}",
        }

    return {"ok": True, "reason": "SQL matches sanctioned computation"}


if __name__ == "__main__":
    receipt = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    result = attest(receipt, params)
    print(json.dumps(result))
    sys.exit(0 if result["ok"] else 1)
