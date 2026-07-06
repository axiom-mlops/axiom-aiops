"""Data contracts for the agentic SRE loop.

Every boundary in the loop passes one of these typed objects.
LLM output is parsed INTO these models -- if validation fails,
the loop retries or escalates. LLM text never flows raw.
"""
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field


class Severity(str, Enum):
    critical = "critical"
    warning = "warning"
    info = "info"


class Alert(BaseModel):
    """Normalized alert -- source-agnostic (Prometheus, CloudWatch, etc.)."""
    fingerprint: str
    name: str
    severity: Severity
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    starts_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class Evidence(BaseModel):
    """One piece of retrieved context the agent reasons over."""
    source: str          # e.g. "promql", "loki", "k8s_api", "runbook"
    query: str           # exactly what was asked -- auditability
    result: str          # what came back (truncated/summarized)


class Hypothesis(BaseModel):
    statement: str
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_evidence: list[int] = Field(
        default_factory=list,
        description="Indices into Diagnosis.evidence",
    )


class Diagnosis(BaseModel):
    """Ranked root-cause hypotheses with cited evidence."""
    alert_fingerprint: str
    hypotheses: list[Hypothesis]
    evidence: list[Evidence]

    @property
    def top(self) -> Hypothesis:
        return max(self.hypotheses, key=lambda h: h.confidence)


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class ProposedPatch(BaseModel):
    """The ONLY object allowed to cross the human gate."""
    target_kind: str        # e.g. "HorizontalPodAutoscaler"
    target_name: str
    target_namespace: str
    patch_json: str         # strategic-merge patch, as JSON string
    rationale: str          # written justification -- the audit trail
    risk: RiskLevel
    rollback_command: str   # every change ships with its undo
