---
incident_id: jvm-oom-heap-001
title: Order processor JVM OOM on heap exhaustion
severity: FATAL_OR_CRITICAL
root_cause: Heap size too small for peak daily volume; unbounded LRU cache growth
resolution: Increased -Xmx from 512m to 2g; added size cap to the internal order-history cache
tags: jvm,java,oom,heap,memory,order-processor
---

The order-processor service crashed with OutOfMemoryError during a peak period.
Java flight recorder showed the internal order-history cache occupying ~80% of
heap just before the crash. The cache was implemented as a LinkedHashMap
without a size limit. Fix was a two-part change: raise heap size and cap the
cache at 10k entries using a proper LRU eviction policy.

## Log excerpt
FATAL Out of memory: Java heap space - Cannot allocate 512MB
FATAL JVM terminated. Core dump written to /var/crash/core.4521
FATAL Service 'order-processor' crashed. PID 4521 exited with signal 9
ERROR Cascading failure: 3 dependent services unreachable
