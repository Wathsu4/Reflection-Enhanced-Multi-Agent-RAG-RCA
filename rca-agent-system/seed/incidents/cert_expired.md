---
incident_id: tls-cert-expired-001
title: TLS certificate expired on internal API
severity: FATAL_OR_CRITICAL
root_cause: Auto-renewal cron job had stopped running after a host migration
resolution: Migrated cert renewal to the central automation platform; added expiry alerts 30/14/7 days out
tags: tls,certificate,expiry,automation,internal-api
---

The internal admin API became unreachable at midnight. All clients hit
`certificate_verify_failed`. The certificate was expired. Investigation found
the cron job that ran `certbot renew` had been tied to a specific host that was
decommissioned 60 days prior, and nobody noticed because there were no
near-expiry alerts.

## Log excerpt
ERROR HTTPS handshake failed: certificate verify failed (expired)
ERROR admin-api health-check failed (connect: error)
FATAL Maintenance dashboard unreachable -- deploy blocked
