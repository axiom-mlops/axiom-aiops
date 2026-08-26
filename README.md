# axiom-aiops

The agent layer has been consolidated into the platform repo it runs against:

**→ [axiom-mlops/axiom-platform](https://github.com/axiom-mlops/axiom-platform)** — see [`aiops/`](https://github.com/axiom-mlops/axiom-platform/tree/main/aiops)

Keeping the loop, the alert rules it consumes, and the RBAC that bounds it in one
repository means the agent and the cluster contract it depends on version together.
