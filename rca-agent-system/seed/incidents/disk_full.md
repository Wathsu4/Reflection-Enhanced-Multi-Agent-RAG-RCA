---
incident_id: disk-full-log-001
title: Disk full on app host caused service to hang
severity: FATAL_OR_CRITICAL
root_cause: Application log files not rotated; /var/log filled to 100%
resolution: Installed logrotate config; added a Prometheus alert at 85% disk usage
tags: disk,log-rotation,filesystem,logrotate,monitoring
---

The app service became unresponsive. `df -h` revealed /var/log at 100%. The
service was configured to write verbose logs but logrotate wasn't configured on
this host (it was a recently-provisioned VM). Once the disk filled, log writes
blocked, which stalled the service.

## Log excerpt
ERROR Failed to write to log file: no space left on device
FATAL Service stuck: unable to flush buffers
WARN  Disk usage: 100% /var/log (prior alert threshold was 95%)
