# Overview

## The problem

Image classification is cheap to prototype and expensive to operate. A model that runs in twenty
lines of Python on a laptop still has to answer a harder set of questions before anyone else can
use it: what happens when two hundred people upload at once, when a request arrives while the
model is still loading, when someone uploads a 40-megapixel photograph or a text file renamed to
`.jpg`, or when the process holding every uploaded image is killed? None of those are modelling
problems. They are orchestration problems, and they are what this project is about.

## What KubeBalancer is

KubeBalancer is a small, honest, fully-observable image classification service running on
Kubernetes. A user sends an image to one public endpoint and gets back a label and a confidence
score. Behind that endpoint, four independently deployable services divide the work: a **gateway**
that validates and orchestrates, a **preprocessor** that normalizes images into model input, an
**inference** service that runs MobileNetV2, and a **storage** service that owns the only
persistent volume in the system. Every classification is durable — the original image, the
processed image, and the prediction are all retrievable afterwards by identifier.

The design deliberately favours *explicability over scale*. Each service does one thing, exposes
one small HTTP contract, and can be tested on its own. The inference tier runs three replicas and
carries a metrics sidecar in the same pod, so the behaviour of the component under load is visible
rather than inferred. The system is sized to run end-to-end on a single-node Minikube cluster on a
laptop, which means every claim in this report is one a reader can reproduce.

## Why it is built this way

The pipeline shape — upload, preprocess, infer, persist, retrieve — is the shape of essentially
every production inference service. Keeping it small makes the interesting parts visible. Three
decisions carry most of the design's weight, and each is a genuine tradeoff rather than a default:

1. **One orchestrating gateway rather than a chain of services.** It costs an extra network hop
   and makes the gateway the busiest component, but it keeps preprocessing and inference as pure
   transforms and gives the system exactly one external surface (§3.2, §3.4).
2. **Synchronous request handling rather than a queue.** A queue would scale better and degrade
   more gracefully, but it would move the project's difficulty from Kubernetes into distributed
   messaging, which is not what this project is meant to demonstrate (§3.7).
3. **One service owns all persistent state.** The storage service holds the only volume claim and
   is pinned to a single replica. This trades horizontal scalability in the storage tier for a
   system with no distributed-write problem anywhere in it (§5.3).

## Engineering case study framing

This report is written as a case study rather than a feature list, per the project brief. It
states the operational problem above; §3 presents the architecture and its central tradeoff; §6
enumerates the risks taken on and how each is contained; and §5.4 and §6.3 set out exactly what
evidence will be captured in Milestones 2 and 3 to show deployment, failure recovery, and
persistence actually working.

One discipline is worth stating explicitly, because it is easy to violate in a document written
before anything runs: **this report claims no measured performance, availability, or scale.**
Latency figures appear only as *budgets* — targets the implementation must meet — and are labelled
as such wherever they occur. Measured numbers appear for the first time in the Milestone 3 report.
