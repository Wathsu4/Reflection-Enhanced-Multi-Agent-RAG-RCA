---
incident_id: api-key-expired-001
title: Shipping-rate lookups failed after a partner API key rotation
severity: ERROR
resolution: Migrated the key to the shared secrets manager with a 30-day-before-expiry rotation reminder, instead of a key hardcoded in a config file
root_cause: The shipping-rates partner API key expired on schedule but the rotation reminder had been sent to a distribution list nobody monitored
tags: api-key,authentication,secrets,third-party,expiry
---

Checkout pages began showing "Shipping rates unavailable" for all carriers.
Every call to the shipping-rates partner API returned `401 Unauthorized:
API key expired`. The partner rotates API keys annually and had emailed the
90/30/7-day rotation warnings to an engineering distribution list that had
been quietly abandoned after a team reorg; nobody rotated the key before it
expired. The key itself was also hardcoded in a config file rather than the
shared secrets manager, so there was no internal alert on approaching expiry
either.

## Log excerpt
ERROR shipping-rates-client: 401 Unauthorized: API key expired
ERROR Checkout: shipping rate lookup failed for 100% of requests in the last 10m
WARN  Falling back to flat-rate shipping estimate (degraded UX)

## What worked
- The partner's error body explicitly said "API key expired" with an expiry
  date, which immediately ruled out a network or outage-on-their-side theory.
- Checking the partner developer portal directly confirmed the key's status
  and let us generate a new one without waiting on their support queue.

## What did NOT help
- Retrying the request with backoff (a 401 for an expired key is not
  transient; every retry failed identically).
- Checking our own service's uptime/health dashboards (this was purely an
  external credential problem, not a service health issue).
