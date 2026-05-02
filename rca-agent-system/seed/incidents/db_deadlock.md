---
incident_id: db-deadlock-001
title: Frequent DB deadlocks on concurrent order updates
severity: ERROR
root_cause: Two code paths acquired row locks in opposite order under contention
resolution: Refactored both paths to acquire locks in a canonical order (orders then order_items)
tags: database,postgres,deadlock,transaction,concurrency
---

Under high concurrency the orders-service saw repeated deadlock errors from
PostgreSQL. Two transactional code paths -- "update order total" and "add order
item" -- were each acquiring row locks on the `orders` and `order_items` tables
but in opposite orders. Under contention this produced classic deadlocks.

## Log excerpt
ERROR SQLSTATE[40P01]: Deadlock detected
ERROR Transaction rolled back: deadlock detected (txn_id=84771)
ERROR Retry attempt 3/3 failed on order update path

## Remediation
- Standardized lock ordering: always acquire `orders` row first, then `order_items`.
- Added a DB-level monitoring alert for pg_stat_database.deadlocks.
