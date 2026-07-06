"""Swappable LLM boundary.

The loop depends on this Protocol, never on a vendor SDK.
Implementations: FakeLLM (tests/dev today), OpenAI-compatible
client against vLLM (prompted Qwen), fine-tuned Qwen (later).
Swapping = changing one constructor arg.
"""
from typing import Protocol
from agent.models import Alert, Diagnosis, Evidence, ProposedPatch


class DiagnosisEngine(Protocol):
    def diagnose(self, alert: Alert, evidence: list[Evidence]) -> Diagnosis: ...
    def propose(self, diagnosis: Diagnosis) -> ProposedPatch: ...


class FakeLLM:
    """Deterministic stand-in: encodes the HPA blind-spot answer.

    Lets us build and test the ENTIRE loop -- gate, execute,
    verify, runbook -- before any GPU or API key exists.
    """

    def diagnose(self, alert: Alert, evidence: list[Evidence]) -> Diagnosis:
        from agent.models import Hypothesis
        return Diagnosis(
            alert_fingerprint=alert.fingerprint,
            evidence=evidence,
            hypotheses=[
                Hypothesis(
                    statement=(
                        "Service is memory-bound under load but the HPA "
                        "scales only on CPU; memory saturates before CPU "
                        "crosses the scale threshold."
                    ),
                    confidence=0.9,
                    supporting_evidence=list(range(len(evidence))),
                ),
                Hypothesis(
                    statement="Memory leak in recent deploy.",
                    confidence=0.2,
                    supporting_evidence=[],
                ),
            ],
        )

    def propose(self, diagnosis: Diagnosis) -> ProposedPatch:
        from agent.models import RiskLevel
        return ProposedPatch(
            target_kind="HorizontalPodAutoscaler",
            target_name="recommendationservice",
            target_namespace="boutique",
            patch_json=(
                '{"spec":{"metrics":[{"type":"Resource","resource":'
                '{"name":"memory","target":{"type":"Utilization",'
                '"averageUtilization":75}}}]}}'
            ),
            rationale=(
                "Top hypothesis (0.9): memory-bound workload with "
                "CPU-only HPA. Adding a memory target lets the HPA "
                "react to the actual saturating resource."
            ),
            risk=RiskLevel.low,
            rollback_command=(
                "kubectl -n boutique patch hpa recommendationservice "
                "--type=json -p '[{\"op\":\"remove\",\"path\":\"/spec/metrics/1\"}]'"
            ),
        )
