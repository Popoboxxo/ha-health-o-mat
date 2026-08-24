# Pipeline `se-cascade`

Execution mode: loop


**l0-stakeholder** — REPEAT_UNTIL Loop:
  - background(agent="se-requirements", prompt="Stakeholder Needs → formal SN-xxx Requirements")
  - background(agent="se-critic", prompt="Review / Critic feedback")
  Max iterations: 3 → Erfolg pruefen; bei Abbruch User benachrichtigen


**l1-requirements** — REPEAT_UNTIL Loop:
  - background(agent="se-requirements", prompt="L1 System Requirements (REQ-L1) from Stakeholder Needs")
  - background(agent="se-critic", prompt="Review / Critic feedback")
  Max iterations: 3 → Erfolg pruefen; bei Abbruch User benachrichtigen


**l1-architecture** — REPEAT_UNTIL Loop:
  - background(agent="se-architect", prompt="L1 System White-Box Decomposition (ARCH-L1)")
  - background(agent="se-critic", prompt="Review / Critic feedback")
  Max iterations: 3 → Erfolg pruefen; bei Abbruch User benachrichtigen


**l2-requirements** — REPEAT_UNTIL Loop:
  - background(agent="se-requirements", prompt="L2 System Requirements (REQ-L2) derived from L1 Architecture")
  - background(agent="se-critic", prompt="Review / Critic feedback")
  Max iterations: 3 → Erfolg pruefen; bei Abbruch User benachrichtigen


**l2-architecture** — REPEAT_UNTIL Loop:
  - background(agent="se-architect", prompt="L2 System White-Box Decomposition (ARCH-L2)")
  - background(agent="se-critic", prompt="Review / Critic feedback")
  Max iterations: 3 → Erfolg pruefen; bei Abbruch User benachrichtigen

1. background(agent="se-interface-mgr", prompt="Interface Registry + Propagation Map for L2") → warten bis abgeschlossen

**l3-requirements** — REPEAT_UNTIL Loop:
  - background(agent="se-requirements", prompt="L3 System Requirements (REQ-L3) derived from L2 Architecture")
  - background(agent="se-critic", prompt="Review / Critic feedback")
  Max iterations: 3 → Erfolg pruefen; bei Abbruch User benachrichtigen


**l3-architecture** — REPEAT_UNTIL Loop:
  - background(agent="se-architect", prompt="L3 System White-Box Decomposition (ARCH-L3)")
  - background(agent="se-critic", prompt="Review / Critic feedback")
  Max iterations: 3 → Erfolg pruefen; bei Abbruch User benachrichtigen


**termination** — Conditional execution:
  - Condition evaluated by se-termination: Per-system leaf/continue decision (respects SE_MIN_DEPTH / SE_MAX_DEPTH)
  Decision agent: se-termination
  If 'continue': Orchestrator spawns new cell at level n+1 with sanitized context
  If 'leaf': Component is final — handover to implementation discipline


**implementation** — REPEAT_UNTIL Loop:
  - background(agent="se-developer", prompt="For each leaf node with domain: software from the termination phase:
- Route to se-junior-developer for trivial leafs (0-1 interfaces, no cross-cutting)
- Route to se-developer for standard leafs (2-4 interfaces)
- Route to se-senior-developer for complex leafs (5+ interfaces, cross-cutting, boundary-level, security/performance-critical)
Implement each leaf against its Black-Box specification and interface contracts from the interface-registry.
Each implementation must reference its req_id and leaf_id in code artifacts.
hardware/mechanics leafs → document as COTS/spec (not implemented).
")
  - background(agent="code-reviewer", prompt="Review / Critic feedback")
  Max iterations: 2 → Erfolg pruefen; bei Abbruch User benachrichtigen


**validation** — Parallel dispatch:
  - background(agent="se-validator", prompt="L1 User-Journey validation")
  - background(agent="se-verifier", prompt="Multi-Level verification")
  - background(agent="se-integration-and-test-manager", prompt="V&V orchestration")

