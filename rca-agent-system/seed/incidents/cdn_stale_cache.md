---
incident_id: cdn-stale-cache-001
title: CDN served a stale, pre-deploy version of the pricing page for six hours
severity: ERROR
resolution: Added a CDN cache-purge step to the deploy pipeline, and moved to versioned asset URLs so stale HTML can never reference the wrong bundle
root_cause: The deploy pipeline updated the origin but never invalidated the CDN's cached copy of the pricing page, which had a long TTL
tags: cdn,cache,stale-content,deploy,invalidation
---

Customers reported seeing yesterday's (lower) prices on the pricing page well
after a scheduled price update had gone live. The origin servers were serving
the new page correctly when queried directly, but the CDN edge nodes were
still serving a cached copy from before the deploy. The pricing page's
cache-control header set a 24-hour TTL, and the deploy pipeline had no step to
purge the CDN cache on release -- previous deploys had gotten lucky because
they didn't touch cacheable pages, so the gap went unnoticed until now.

## Log excerpt
INFO  Deploy pricing-service v2.14.0 completed successfully
WARN  CDN cache HIT ratio 98% on /pricing (expected drop after deploy, none observed)
ERROR Customer support: multiple reports of incorrect pricing displayed

## What worked
- Comparing response headers (`X-Cache: HIT` vs `MISS`, and the `Age` header)
  between a direct origin request and a normal browser request immediately
  showed the CDN was the one serving stale content.
- A manual cache purge on the affected path fixed it instantly, confirming
  the origin was never the problem.

## What did NOT help
- Redeploying the same code again (without a purge, the CDN just cached the
  "new" response under the same stale TTL window behavior).
- Clearing browser cache on the reporting customers' machines (the staleness
  was at the CDN edge, not client-side).
