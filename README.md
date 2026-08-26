# axiom-aiops — Agentic AIOps on a production-grade observability platform

Autonomous incident-response agents that detect, diagnose, propose, and remediate
Kubernetes reliability issues — with a human approval gate before any change touches
the cluster. Built on top of [axiom-platform](https://github.com/axiom-mlops/axiom-platform),
a Kubernetes microservices platform with a full LGTM observability stack, load-tested
to 5,000 concurrent users.

## The business problem

Incident response is the most expensive toil in operations. The costly part is not
the fix — it is the 30–90 minutes an on-call engineer spends correlating metrics,
logs, and configuration before anyone knows what to fix. That is MTTR, and MTTR is
revenue: every minute of a degraded checkout path has a dollar value.

This project automates the correlation-and-diagnosis phase and *proposes* the fix,
while keeping a human accountable for the decision. The agent compresses
time-to-diagnosis from tens of minutes to seconds; the human approves in one click
with the full evidence trail in front of them.

## What it does (working demo)

A real failure mode from the underlying platform: a service is **memory-bound under
load, but its HPA scales on CPU only**. Memory climbs toward the pod limit, CPU
stays under the autoscaling target, no scale-out happens, and pods head toward
OOMKill — the dashboards look "green" on the metric the autoscaler watches.

The agent lifecycle for this incident:

```
Alertmanager alert
      │
      ▼
 OBSERVE   fixed golden-signal evidence sweep: Prometheus (memory vs limit,
      │    CPU vs request), Kubernetes (HPA spec), Loki (error logs)
      ▼
 DIAGNOSE  LLM produces a *typed* Diagnosis (root cause, confidence, evidence,
      │    blast radius) — validated at the boundary, never free text
      ▼
 PROPOSE   a ProposedPatch from a whitelisted action space
      │    (here: add a 75% memory target to the HPA)
      ▼
 GATE      hard stop — human approval required (PagerDuty in live mode);
      │    the act-plane is structurally unreachable without it
      ▼
 EXECUTE   scoped Kubernetes API patch (agent emits intent; executor holds RBAC)
      ▼
 VERIFY    did the signals recover? (HPA spec updated, replicas 3→7,
      │    memory 91%→63% of limit)
      ▼
 RUNBOOK   the agent writes the runbook for the next human, from the audit
           trail — see docs/runbooks/agent-generated-hpa-memory-blindspot.md
```

Captured run: [`demo/transcript.md`](demo/transcript.md). Reproduce anywhere:

```bash
python -m agents.rca.run_demo   # fixture mode — no cluster required
python -m pytest tests/         # golden scenarios
```

## Design decisions (and the alternatives they beat)

**Hand-rolled ~120-line loop, not LangGraph/CrewAI.** A remediation agent has one
correct control flow, and it must be auditable line-by-line by a change-approval
board. Frameworks pay off when the graph is dynamic; here the graph is fixed and
the risk lives in the edges — what can execute, and when. The loop *is* the safety
documentation. When this grows into multi-agent coordination, LangGraph is the
right upgrade and the typed contracts port over unchanged.

**Whitelisted actions, not generated commands.** The model selects from a `Literal`
action space (`patch_hpa_add_memory_target`, `scale_deployment`,
`rollback_deployment`). It cannot invent kubectl. This converts "can we trust the
LLM?" into "do we trust these three reviewed actions?" — a question ops teams
already know how to answer.

**Human gate as structure, not prompt.** The act-plane tools are unreachable until
an approved `GateDecision` exists. A prompt cannot talk its way past an interface.

**Low-confidence exit.** If the evidence doesn't support a confident diagnosis, the
agent holds the action and escalates to on-call instead of guessing. Knowing when
*not* to act is what separates an SRE tool from a pager-noise generator.

**Swappable LLM backend.** The loop depends on a Protocol, not a vendor SDK.
Golden-scenario tests run in CI against a deterministic backend at zero API cost;
the live path targets a prompted frontier model today and a QLoRA fine-tuned
Qwen3.5-9B served by vLLM as the drop-in upgrade — a deployment decision, not an
architecture change.

## Value audit methodology

The demo numbers are illustrative; the *auditing method* is the deliverable and it
ports to any environment:

| Measure | Baseline (human-only) | With agent |
|---|---|---|
| Time-to-diagnosis | 30–90 min (log/metric correlation by hand) | seconds (evidence sweep + structured RCA) |
| Time-to-safe-remediation | diagnosis + change drafting + review | one-click approval of a pre-vetted patch |
| Knowledge capture | tribal, or a postmortem written days later | runbook written at resolution time, from the audit trail |

Method: instrument the loop itself (every stage emits duration + outcome), price
on-call time and revenue-per-minute of the affected path, and compare a quarter of
incidents before/after. The agent's own telemetry feeds the same Grafana stack it
diagnoses — the "Agent Operations" dashboard closes the loop.

## Roadmap — three agents, one chassis

The detect→reason→propose→gate→execute→verify loop is a reusable chassis across the
incident lifecycle:

1. **Triage/RCA agent** (this repo — working): respond faster.
2. **Deployment verification agent**: prevent incidents — canary analysis with
   automated chaos/load verification before promotion.
3. **Right-sizing agent**: optimize spend — continuous resource recommendation with
   the same human-gated execution.

Plus: OTel GenAI semantic-convention instrumentation of the agents themselves
(`gen_ai.*` spans into Tempo), and the fine-tuned SLM backend.

## Repo layout

```
agents/rca/
  contracts.py   # Pydantic v2 typed boundaries: Alert, Diagnosis, ProposedPatch, ...
  loop.py        # the agent loop — start here
  llm.py         # LLMBackend protocol + deterministic golden-scenario backend
  tools.py       # read-plane (Prometheus/Loki/K8s) and act-plane (K8s writes) split
  gate.py        # human approval gate
  run_demo.py    # end-to-end demo entrypoint
tests/           # golden scenarios: gate-before-execute, deny=zero-writes, low-confidence escalation
docs/runbooks/   # includes the agent-generated runbook
demo/            # captured run transcript
```
