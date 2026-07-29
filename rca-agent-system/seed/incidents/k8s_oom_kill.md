---
incident_id: k8s-oom-kill-001
title: Kubernetes pod repeatedly OOMKilled during nightly batch job
severity: FATAL_OR_CRITICAL
resolution: Raised the pod's memory limit and request to match observed peak usage; added a memory-usage alert at 80% of the limit
root_cause: Pod memory limit was sized for steady-state traffic, not the nightly batch job's peak working set
tags: kubernetes,oomkilled,container,memory-limit,batch-job
---

The nightly reconciliation batch job's pod was killed and restarted three times
in a row around 02:00. `kubectl describe pod` showed `Last State: Terminated,
Reason: OOMKilled` each time. The pod's memory limit (512Mi) had been set based
on the service's steady-state daytime traffic; the batch job loads a much
larger working set into memory to build its reconciliation report, which
regularly exceeds that limit. The container runtime's cgroup killed the
process the instant it crossed the limit, with no graceful degradation.

## Log excerpt
WARN  Memory usage at 480Mi / 512Mi limit, approaching OOM
FATAL container reconciler-job killed (OOMKilled), exit code 137
ERROR CrashLoopBackOff: back-off restarting failed container

## What worked
- Correlated the kill timestamp with the batch job's start time via the
  Kubernetes events timeline (`kubectl get events --sort-by=.lastTimestamp`).
- Confirmed via `kubectl top pod` history that the same job pushed memory
  usage close to the limit on prior nights too, just under the threshold.

## What did NOT help
- Restarting the pod manually (it just OOMKilled again on the next run).
- Scaling the number of replicas (this is a single batch job, not a
  request-serving workload; more replicas don't reduce one job's memory need).
