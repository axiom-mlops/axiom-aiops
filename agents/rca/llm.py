"""LLM backend behind a swappable interface.

Design decision: the loop depends on a Protocol, not a vendor SDK.
Why: (1) tests run deterministically against FakeLLM — golden scenarios
in CI with zero API cost; (2) the serving backend is a deployment
decision, not an architecture decision — the same loop runs against a
prompted frontier model today and a QLoRA fine-tuned Qwen served by
vLLM tomorrow, with no loop changes.
"""
from __future__ import annotations

import json
from typing import Protocol

from .contracts import Alert, Diagnosis, Evidence, ProposedPatch


class LLMBackend(Protocol):
    def diagnose(self, alert: Alert, evidence: list[Evidence]) -> Diagnosis: ...

    def propose(self, alert: Alert, diagnosis: Diagnosis) -> ProposedPatch: ...


class FakeLLM:
    """Deterministic backend encoding the HPA memory blind-spot playbook.

    Exists so the loop's control flow, gating and verification are
    testable independently of model quality. This is the golden-scenario
    oracle, not a mock of intelligence.
    """

    def diagnose(self, alert: Alert, evidence: list[Evidence]) -> Diagnosis:
        mem = any("memory" in e.finding.lower() for e in evidence)
        cpu_low = any("cpu" in e.finding.lower() and "low" in e.finding.lower() for e in evidence)
        hpa_cpu_only = any("hpa targets: cpu only" in e.finding.lower() for e in evidence)
        if mem and cpu_low and hpa_cpu_only:
            return Diagnosis(
                root_cause=(
                    f"{alert.service} is memory-bound under load but its HPA "
                    "scales only on CPU utilization. Memory approaches the pod "
                    "limit while CPU stays under the HPA target, so no scale-out "
                    "occurs and pods head toward OOMKill."
                ),
                confidence="high",
                evidence=evidence,
                blast_radius=(
                    "OOMKill restarts under sustained load; request failures and "
                    "latency spikes propagate to checkout via the frontend."
                ),
            )
        return Diagnosis(
            root_cause="Insufficient evidence for a confident root cause.",
            confidence="low",
            evidence=evidence,
            blast_radius="Unknown",
        )

    def propose(self, alert: Alert, diagnosis: Diagnosis) -> ProposedPatch:
        return ProposedPatch(
            action="patch_hpa_add_memory_target",
            target=alert.service,
            namespace=alert.namespace,
            params={"memory_target_utilization": 75},
            rationale=(
                "Add a memory utilization target (75%) alongside the existing CPU "
                "target so the HPA reacts to the actual binding resource. Chosen "
                "over raising the memory limit because the workload scales "
                "horizontally and a limit raise only delays the same failure."
            ),
            risk="low",
        )


def render_prompt(alert: Alert, evidence: list[Evidence]) -> str:
    """Prompt for real backends (vLLM/OpenAI-compatible). Kept here so the
    fine-tuned model and the prompted model share one instruction surface."""
    return (
        "You are an SRE diagnosis agent. Given the alert and evidence, "
        "return ONLY JSON matching the Diagnosis schema.\n"
        f"ALERT: {alert.model_dump()}\n"
        f"EVIDENCE: {json.dumps([e.model_dump() for e in evidence])}"
    )
