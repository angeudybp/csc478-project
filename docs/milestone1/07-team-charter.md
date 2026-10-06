# Team Charter

This is a **solo project**, so the charter the brief asks for is adapted rather than omitted: in
place of interpersonal agreements it records role separation, a self-imposed cadence, and a written
Definition of Done. The separation of roles is genuinely useful even with one person, because the
three roles fail in different ways and compete for the same hours.

## Roles

One person wears all three hats; the value is in naming them so that time spent is deliberate.

| Role | Responsibility | Share of effort |
|:--------------------|:-----------------------------------------|:-----:|
| **Platform** | Minikube cluster, manifests, Services, probes, resource policy, PV/PVC, teardown and reprovision correctness. | ~45% |
| **Services** | The four FastAPI applications, the metrics sidecar, Dockerfiles, the ONNX integration and the mock classifier. | ~35% |
| **Documentation and demo** | This report, the diagrams, the final report, evidence capture, and the demonstration video. | ~20% |

: **Role allocation across the project.**

The Platform share is the largest on purpose: the project is graded on Kubernetes orchestration,
not on application code, and the mock classifier exists specifically so that Services work can
never become the critical path (§6.1, R8).

## Cadence

| Checkpoint | Frequency | Output |
|:--------------------|:--------------|:-----------------------------------------|
| Working session | 2–3 per week, ~2 hours | Commits on a feature branch; nothing left uncommitted at session end. |
| Self-review | Weekly, end of week | Re-read the milestone requirements against what exists; update the risk register; write down what is now blocked. |
| Milestone gate | Per milestone | Full deliverable checklist walked item by item before submission, against the traceability table in this document. |

: **Working cadence.** Self-imposed, since no teammate will notice a missed checkpoint.

Because no one else will notice a missed checkpoint, the weekly self-review is written down in the
repository rather than done mentally — a short dated note per week in `docs/journal.md`. That note
is also the raw material for the "individual contribution" section the brief asks the final report
to include.

## Definition of Done

A unit of work is done only when **all** of the following hold. Partial completion is tracked as
not done, not as mostly done.

1. **It applies from nothing.** The relevant manifests apply cleanly onto a freshly started cluster
   with no manual steps and no pre-existing state.
2. **It answers.** The endpoint or behaviour responds correctly to a `curl` command that is
   committed to the repository, not typed from memory.
3. **It is tested.** The corresponding row of the Table 9 matrix passes, and the command and its
   output are captured.
4. **It survives teardown.** `kubectl delete -f . && kubectl apply -f .` still works afterwards.
5. **It is documented.** Any decision that diverges from this design document is recorded, with the
   reason, in the same commit that makes the change.
6. **It is committed.** Work exists on a branch with a message explaining *why*, and the working
   tree is clean.

Criterion 5 matters most to the project as a whole. This document will be wrong about something —
designs written before implementation always are — and the value of the final report depends on
those divergences being recorded as they happen rather than reconstructed from memory at the end.

## Milestone schedule

| Milestone | Scope | Target |
|:-----------|:---------------------------------------------|:-------------|
| M1 | Architecture and design (this document) | [M1 due date] |
| M2 | Four Deployments, four Services, sidecar, scaling and self-healing evidence; no persistence | [M2 due date] |
| M3 | PV/PVC, persistence verification, probes, resource limits, demo video, final report | [M3 due date] |

: **Milestone schedule.** Dates are filled in from the course calendar.

Within M2 the order is deliberate: manifests with the mock classifier first, so that a working
end-to-end pipeline exists as early as possible, then the real model, then the sidecar, then the
scaling and self-healing evidence. The riskiest work (R1, R3 — image size and resource contention)
is scheduled first, while there is still time to change the approach.
