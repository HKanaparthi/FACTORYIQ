"""
FactoryIQ Milestone 5 — Evaluation Engine.

Scores a completed investigation against eval_ground_truth using pattern
matching against finding text.

DOCUMENTED LIMITATION: This engine uses regex pattern matching, not semantic
verification. Keyword presence ≠ correct reasoning. Any result labelled
non_evaluable or acceptable_alt requires human review before citing in reports.
Scripted-runner results must NOT be presented as Claude model accuracy.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from db import get_pool

logger = logging.getLogger(__name__)

# Patterns that indicate the agent acknowledged uncertainty / data quality issues
_UNCERTAINTY_PATTERNS: list[str] = [
    r"stale",
    r"freshness",
    r"quality.*issue",
    r"bad.*quality",
    r"unavailab",
    r"insufficient",
    r"cannot.*confirm",
    r"uncertain",
    r"data.*unavail",
    r"not.*fresh",
    r"missing.*data",
    r"no.*readings",
    r"non.good",
    r"reduce.*reliab",
]

# Patterns indicating a named sensor tag or numeric reading was cited
_GROUNDING_PATTERNS: list[str] = [
    r"\d+\.\d+",
    r"Pressure_bar",
    r"FlowRate_Lmin",
    r"Temperature_degC",
    r"Current_A",
    r"Speed_mps",
    r"Level_pct",
    r"FillRate_Lmin",
    r"readings",
    r"sensor",
]


def _matches_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


async def evaluate_investigation(
    run_scenario_id: str,
    investigation_id: str,
    scenario_id: str,
) -> dict[str, Any]:
    """
    Score a completed investigation against ground truth. Persists to eval_results.
    Returns the full result dict.
    """
    pool = get_pool()

    inv = await pool.fetchrow(
        "SELECT status, finding_text, agent_tool_calls FROM investigations WHERE investigation_id = $1",
        uuid.UUID(investigation_id),
    )

    gt = await pool.fetchrow(
        """
        SELECT true_root_cause, injected_fault_type,
               acceptable_conclusion_patterns, negative_patterns,
               uncertainty_required, fault_expected, evaluation_notes
        FROM eval_ground_truth
        WHERE scenario_id = $1
        """,
        scenario_id,
    )

    if gt is None:
        result = _non_evaluable(run_scenario_id, "No ground truth record found for this scenario")
        await _save_result(result)
        return result

    finding_text: str = (inv["finding_text"] or "") if inv else ""
    finding_lower = finding_text.lower()
    status: str = inv["status"] if inv else "failed"
    tool_calls: int = (inv["agent_tool_calls"] or 0) if inv else 0

    positive_patterns: list[str] = gt["acceptable_conclusion_patterns"] or []
    negative_patterns: list[str] = gt["negative_patterns"] or []
    uncertainty_required: bool = gt["uncertainty_required"]

    # Completion: investigation submitted a finding
    completed = status == "pending_review" and bool(finding_text)

    # Tool use: at least 3 tool calls (data-gathering + flag_for_review)
    tool_use_ok = tool_calls >= 3

    # Evidence grounding: finding cites a sensor tag or numeric value
    evidence_grounded = _matches_any(finding_text, _GROUNDING_PATTERNS)

    # Uncertainty handling
    uncertainty_handled = (
        _matches_any(finding_lower, _UNCERTAINTY_PATTERNS)
        if uncertainty_required
        else True
    )

    # Diagnostic verdict
    if not completed:
        verdict = "non_evaluable"
        failure_reason = f"Investigation did not complete (status={status!r})"

    elif not positive_patterns:
        # Scenario intentionally has no positive patterns (detection-gap scenario)
        verdict = "non_evaluable"
        failure_reason = "No acceptable_conclusion_patterns defined (detection gap scenario — expected)"

    else:
        matched_pos = _matches_any(finding_lower, positive_patterns)
        matched_neg = _matches_any(finding_lower, negative_patterns)

        if matched_pos and not matched_neg:
            if uncertainty_required and not uncertainty_handled:
                verdict = "incorrect"
                failure_reason = (
                    "Finding matched positive patterns but did not "
                    "acknowledge required uncertainty"
                )
            else:
                verdict = "correct"
                failure_reason = None

        elif matched_neg and not matched_pos:
            verdict = "incorrect"
            failure_reason = "Finding matched a negative pattern and no positive patterns"

        elif matched_pos and matched_neg:
            verdict = "acceptable_alt"
            failure_reason = "Finding matched both positive and negative patterns — requires human review"

        else:
            # No positive pattern matched
            if uncertainty_required and uncertainty_handled:
                verdict = "uncertain_correct"
                failure_reason = None
            else:
                verdict = "incorrect"
                failure_reason = "Finding did not match any acceptable_conclusion_patterns"

    score_detail: dict[str, Any] = {
        "finding_length": len(finding_text),
        "positive_patterns": positive_patterns,
        "negative_patterns": negative_patterns,
        "matched_positive": _matches_any(finding_lower, positive_patterns) if positive_patterns else None,
        "matched_negative": _matches_any(finding_lower, negative_patterns) if negative_patterns else None,
        "uncertainty_required": uncertainty_required,
        "tool_calls": tool_calls,
        "evaluation_notes": gt["evaluation_notes"] or "",
    }

    result: dict[str, Any] = {
        "run_scenario_id": run_scenario_id,
        "diagnostic_verdict": verdict,
        "evidence_grounded": evidence_grounded,
        "uncertainty_handled": uncertainty_handled,
        "tool_use_ok": tool_use_ok,
        "completed": completed,
        "score_detail": score_detail,
        "failure_reason": failure_reason,
    }

    await _save_result(result)
    logger.info(
        "Evaluated scenario via %s → verdict=%s",
        run_scenario_id[:8], verdict,
    )
    return result


def _non_evaluable(run_scenario_id: str, reason: str) -> dict[str, Any]:
    return {
        "run_scenario_id": run_scenario_id,
        "diagnostic_verdict": "non_evaluable",
        "evidence_grounded": None,
        "uncertainty_handled": None,
        "tool_use_ok": None,
        "completed": False,
        "score_detail": {},
        "failure_reason": reason,
    }


async def _save_result(result: dict[str, Any]) -> None:
    pool = get_pool()
    await pool.execute(
        """
        INSERT INTO eval_results (
            run_scenario_id, diagnostic_verdict, evidence_grounded,
            uncertainty_handled, tool_use_ok, completed,
            score_detail, failure_reason, evaluated_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        ON CONFLICT (run_scenario_id) DO UPDATE SET
            diagnostic_verdict  = EXCLUDED.diagnostic_verdict,
            evidence_grounded   = EXCLUDED.evidence_grounded,
            uncertainty_handled = EXCLUDED.uncertainty_handled,
            tool_use_ok         = EXCLUDED.tool_use_ok,
            completed           = EXCLUDED.completed,
            score_detail        = EXCLUDED.score_detail,
            failure_reason      = EXCLUDED.failure_reason,
            evaluated_at        = EXCLUDED.evaluated_at
        """,
        uuid.UUID(result["run_scenario_id"]),
        result["diagnostic_verdict"],
        result["evidence_grounded"],
        result["uncertainty_handled"],
        result["tool_use_ok"],
        result["completed"],
        result["score_detail"],
        result["failure_reason"],
        datetime.now(timezone.utc),
    )
