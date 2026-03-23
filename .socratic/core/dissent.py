"""
Dissent Detection — Surfaces disagreement patterns from roundtable sessions.

Analyzes structured AgentResponse data to identify:
- Overall dissent rate (what % of agents dissented)
- Dissent pairs (who disagrees with whom)
- Low-weight dissenters (the highest-value signal — proven across 5+ sessions)
- Claim divergence (which specific claims lack consensus)

This module produces metrics for the orchestrator to display and act on.
It does NOT auto-escalate — that decision stays with the human/lead.

Usage (from orchestrator after Round 1):
    from core.dissent import analyze_dissent, format_dissent_report

    report = analyze_dissent(responses)
    print(format_dissent_report(report))

    # If report["dissent_rate"] > 0.3 and novel domain:
    #   -> consider escalating to full roundtable
"""

from typing import Dict, List, Optional
from collections import defaultdict


def analyze_dissent(responses: list) -> Dict:
    """Extract dissent metrics from a list of AgentResponse objects.

    Args:
        responses: list of AgentResponse (from roundtable.py) with
                   .agent_name, .dissents, .weight, .confidence, .key_claims

    Returns:
        dict with dissent_rate, dissent_pairs, low_weight_dissenters,
        claim_clusters, recommendation
    """
    if not responses:
        return {"dissent_rate": 0, "total_dissents": 0, "dissent_pairs": [],
                "low_weight_dissenters": [], "claim_clusters": {},
                "recommendation": "No responses to analyze."}

    total_dissents = sum(len(r.dissents) for r in responses)
    dissent_rate = total_dissents / len(responses)

    # Who dissents against whom
    dissent_pairs = []
    for r in responses:
        for d in r.dissents:
            dissent_pairs.append({
                "dissenter": r.agent_name,
                "dissenter_weight": r.weight,
                "against": d.get("against", "unknown"),
                "reason": d.get("reason", ""),
            })

    # Low-weight agents who dissent — historically the highest-impact signal
    median_weight = sorted(r.weight for r in responses)[len(responses) // 2]
    low_weight_dissenters = [
        {
            "agent": r.agent_name,
            "weight": r.weight,
            "dissent_count": len(r.dissents),
            "targets": [d.get("against", "?") for d in r.dissents],
        }
        for r in responses
        if r.weight < median_weight and len(r.dissents) > 0
    ]

    # Cluster claims to find where consensus exists vs doesn't
    claim_clusters = _cluster_claims(responses)

    # Generate recommendation
    recommendation = _recommend(dissent_rate, low_weight_dissenters, claim_clusters)

    return {
        "dissent_rate": round(dissent_rate, 2),
        "total_dissents": total_dissents,
        "dissent_pairs": dissent_pairs,
        "low_weight_dissenters": low_weight_dissenters,
        "claim_clusters": claim_clusters,
        "recommendation": recommendation,
    }


def _cluster_claims(responses: list) -> Dict:
    """Group claims by similarity and count support.

    Returns dict of claim -> list of agents supporting it.
    Simple word-overlap clustering (no ML).
    """
    all_claims = []
    for r in responses:
        for claim in r.key_claims:
            all_claims.append((r.agent_name, claim.lower().strip()))

    if not all_claims:
        return {}

    # Group by word overlap — claims sharing >50% of words cluster together
    clusters: Dict[str, List[str]] = {}
    used = set()

    for i, (agent_a, claim_a) in enumerate(all_claims):
        if i in used:
            continue
        cluster_agents = [agent_a]
        used.add(i)
        words_a = set(claim_a.split())

        for j, (agent_b, claim_b) in enumerate(all_claims):
            if j in used or j == i:
                continue
            words_b = set(claim_b.split())
            if not words_a or not words_b:
                continue
            overlap = len(words_a & words_b) / min(len(words_a), len(words_b))
            if overlap > 0.5:
                cluster_agents.append(agent_b)
                used.add(j)

        # Use first claim as representative
        clusters[all_claims[i][1]] = cluster_agents

    return clusters


def _recommend(dissent_rate: float, low_weight_dissenters: list,
               claim_clusters: dict) -> str:
    """Generate a short recommendation based on dissent metrics."""
    parts = []

    if dissent_rate == 0:
        parts.append("Full consensus — consider whether groupthink is a risk.")
    elif dissent_rate < 0.3:
        parts.append("Low dissent — routine decision, spot-check sufficient.")
    elif dissent_rate < 0.6:
        parts.append("Moderate dissent — self-critique recommended.")
    else:
        parts.append("High dissent — consider full roundtable with targeted R2.")

    if low_weight_dissenters:
        names = [d["agent"] for d in low_weight_dissenters]
        parts.append(
            f"Low-weight dissenter(s): {', '.join(names)} — "
            f"historically highest-impact signal. Investigate their concerns."
        )

    # Check for isolated claims (only 1 agent supports)
    isolated = [c for c, agents in claim_clusters.items() if len(agents) == 1]
    if isolated:
        parts.append(f"{len(isolated)} isolated claim(s) — potential blind spots.")

    return " ".join(parts)


def format_dissent_report(report: Dict) -> str:
    """Format dissent analysis as readable text for display."""
    lines = [
        "## Dissent Analysis",
        f"Dissent rate: {report['dissent_rate']} ({report['total_dissents']} total dissents)",
        "",
    ]

    if report["dissent_pairs"]:
        lines.append("### Dissent Pairs")
        for p in report["dissent_pairs"]:
            lines.append(
                f"  {p['dissenter']} (w={p['dissenter_weight']:.3f}) "
                f"vs {p['against']}: {p['reason']}"
            )
        lines.append("")

    if report["low_weight_dissenters"]:
        lines.append("### Low-Weight Dissenters (HIGH-VALUE SIGNAL)")
        for d in report["low_weight_dissenters"]:
            lines.append(
                f"  {d['agent']} (w={d['weight']:.3f}): "
                f"{d['dissent_count']} dissent(s) against {', '.join(d['targets'])}"
            )
        lines.append("")

    if report["claim_clusters"]:
        lines.append("### Claim Consensus")
        for claim, agents in report["claim_clusters"].items():
            status = "CONSENSUS" if len(agents) >= 3 else (
                "SPLIT" if len(agents) == 2 else "ISOLATED"
            )
            lines.append(f"  [{status}] ({', '.join(agents)}): {claim}")
        lines.append("")

    lines.append(f"**Recommendation:** {report['recommendation']}")
    return "\n".join(lines)
