---
incident_id: kafka-consumer-lag-001
title: Order-events consumer group fell hours behind after a downstream slowdown
severity: ERROR
resolution: Added a circuit breaker so the consumer skips the slow enrichment call under sustained latency, and scaled consumer partitions from 6 to 12
root_cause: A downstream enrichment API slowed down, and the consumer's synchronous per-message call to it throttled the whole consumer group's throughput
tags: kafka,consumer-lag,backlog,message-queue,throughput
---

Consumer lag on the `order-events` topic climbed from a normal ~500 messages
to over 400,000 over two hours, delaying order-confirmation emails by up to
three hours. Each consumer makes a synchronous HTTP call to a fraud-scoring
enrichment service before processing a message; that service's p99 latency
had jumped from 80ms to over 4s after an unrelated deploy on their side.
Because the consumer processes messages one at a time per partition and waits
on that call, the whole group's effective throughput collapsed to a fraction
of the topic's normal produce rate.

## Log excerpt
WARN  Consumer group order-events-processor lag: 187342 (rising)
WARN  Enrichment call to fraud-scoring-api took 4123ms (p99 baseline: 80ms)
ERROR Consumer lag exceeded alert threshold (100000) for 15+ minutes

## What worked
- Grafana's consumer-lag-over-time panel showed the exact inflection point,
  which lined up with the enrichment service's own latency dashboard.
- Confirming CPU/memory on the consumer pods were normal ruled out a
  resource-starvation explanation on our side.

## What did NOT help
- Restarting the consumer pods (lag kept climbing at the same rate once they
  rejoined the group, since the bottleneck was the external call, not the pod).
- Adding more consumer instances beyond the partition count (Kafka can't
  assign more consumers than partitions, so extra instances sat idle).
