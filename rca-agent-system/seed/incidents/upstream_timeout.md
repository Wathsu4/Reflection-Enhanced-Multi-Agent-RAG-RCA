---
incident_id: upstream-timeout-payments-001
title: Payments upstream timeouts during promotional event
severity: ERROR
root_cause: Payments service was under-scaled for the promotional event traffic
resolution: Coordinated a capacity plan with the payments team before major events; added circuit-breaker fallback
tags: upstream,timeout,circuit-breaker,payments,capacity
---

During a flash sale, the payments service started timing out after 30s on a
significant fraction of requests. Our orders service had no circuit breaker, so
the timeouts cascaded into user-visible errors. Root cause was the payments
team hadn't been notified of the sale and hadn't scaled; aggravated by our
missing circuit breaker.

## Log excerpt
ERROR Upstream 'payments' timed out after 30s
ERROR Order #8291 failed at payment step
WARN  Circuit breaker open (fallback active) -- 18 consecutive failures
