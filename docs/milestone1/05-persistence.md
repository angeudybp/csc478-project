# Persistence Plan

Milestone 2 runs the pipeline with ephemeral storage; Milestone 3 adds the persistent volume
described here. The design is fixed now because the storage service's API and directory layout
determine what the other services send it.

## What needs to be stored

Each accepted upload produces three durable artifacts:

| Artifact | Typical size | Why it is kept |
|:---------------------|:--------|:---------------------------------------------|
| Original image | 0.1–8 MB | Audit trail. Lets a prediction be re-run against a newer model without asking the user to re-upload. |
| Processed image (224×224 JPEG) | ~20 KB | Shows exactly what the model saw. Makes a surprising prediction diagnosable. |
| Prediction record (JSON) | ~1 KB | The result itself: labels, scores, model version, timings, timestamp. |

: **Persisted artifacts per classification.** Sizes are design expectations for the sample set, not measurements.

Nothing else is persisted. There is no user database, no session state, and no request log on disk
— logs go to stdout and are read with `kubectl logs`, which is the Kubernetes-native path and
keeps the volume holding only user data.

## Volume design and directory layout

A single `PersistentVolumeClaim` named `storage-data-pvc` requests **2 Gi** with access mode
**ReadWriteOnce**, using Minikube's default `standard` StorageClass, which provisions dynamically
through the `hostPath` provisioner on the node. It is mounted at `/data` in the storage pod and
nowhere else. 2 Gi is sized for roughly two thousand sample images — generous for a demonstration
and small enough to provision instantly.

```
/data/
├── originals/<yyyy>/<mm>/<dd>/<imageId>.<ext>     original upload, as received
├── processed/<yyyy>/<mm>/<dd>/<imageId>.jpg       224x224 model input
├── results/<imageId>.json                         prediction record
└── index/manifest.jsonl                           append-only, one line per classification
```

Images are sharded by ingest date so no single directory accumulates unbounded entries, while
prediction records are flat because they are only ever looked up by exact identifier. The
`manifest.jsonl` index exists so `GET /results?limit=n` does not have to scan a directory: it is
append-only, so a write is a single `O(1)` operation with no read-modify-write cycle to corrupt
under concurrent access, and the listing endpoint reads it from the tail.

If dynamic provisioning misbehaves on the target cluster, a statically-provisioned `hostPath`
PersistentVolume is kept as a documented fallback (`storage/05-storage-pv.yaml`), bound explicitly
by the claim. The reclaim policy is `Retain` in both cases, so deleting the claim does not
immediately destroy the demonstration data.

## The single-writer constraint

ReadWriteOnce means the volume can be mounted for writing by one node at a time, and in practice
by one pod. This has three consequences that are consequences of the design, not accidents of it:

1. The storage Deployment is **pinned to one replica**.
2. Its update strategy is **`Recreate`, not `RollingUpdate`** — a rolling update would try to start
   a second pod while the first still holds the volume, and the new pod would stay `Pending` on a
   multi-attach error while the old one was never terminated.
3. There is therefore a **brief write outage during any storage redeploy**, bounded by pod startup
   time. Uploads during that window fail with 503 from the gateway rather than being queued.

This is the cost of having exactly one owner of persistent state, and it buys a system with no
distributed-write problem: no two processes ever contend for the same file, so no locking,
leader election, or conflict resolution appears anywhere in the design. The production path away
from it is an object store (S3 or MinIO) behind the same storage API, which would make the storage
service stateless and horizontally scalable without changing a single caller. That is recorded as a
next step, not implemented here.

## Verification procedure (executed in Milestone 3)

Persistence is only demonstrated if data survives the destruction of the process that wrote it. The
procedure is:

1. Upload three distinct images; record the three returned `imageId` values.
2. Confirm all three are retrievable via `GET /api/v1/results/{imageId}`, and capture the output.
3. Delete the storage pod outright: `kubectl delete pod -l app.kubernetes.io/component=storage -n imgpipe`.
4. Watch the Deployment controller recreate it: `kubectl get pods -n imgpipe -w` until `Ready`.
5. Re-request all three identifiers and the processed image variants. Byte-for-byte identical
   results constitute the evidence.
6. Repeat with `kubectl rollout restart deployment/storage -n imgpipe` to confirm the `Recreate`
   strategy behaves as designed rather than stalling.
7. Finally, confirm that `kubectl delete -f . && kubectl apply -f .` reprovisions the full stack,
   and document explicitly whether data survives it — with `Retain` the volume persists, and that
   distinction between deleting a pod and deleting a claim is itself part of the result.

Each step's command and output are captured for the Milestone 3 report. No persistence claim is
made that is not backed by a captured command.
