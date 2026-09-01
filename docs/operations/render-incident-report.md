# Render Support Incident Report — External Ingress Failure

**Date:** 2026-09-01
**Reporter:** hi.myrepo deployment team
**Severity:** Service unreachable from public internet
**Service:** hi-myrepo-backend (Render Web Service)
**Runtime:** Docker (python:3.12-slim)
**Status:** Deploy succeeded | Live — but externally unreachable

---

## 1. Service Identity

| Field | Value |
|-------|-------|
| Service name | `hi-myrepo-backend` |
| Render URL | `https://hi-myrepo-backend.onrender.com` |
| Render plan | Free |
| Runtime | Docker |
| Region | `gcp-us-west1-1` (Oregon) |
| Deployment commit | `ce30fac` |
| Render status | "Deploy succeeded \| Live" |
| Internal health checks | Passing (GET /health → 200, every 5 seconds) |

## 2. Internal Health-Check Evidence (Render Logs)

The following log entries prove the container is running and healthy within Render's network:

```
21:59:25Z  Uvicorn started
21:59:30Z  Application startup complete
21:59:38Z  Render marked service live
21:59:38Z  GET /       → 200
21:59:38Z  GET /health → 200
21:59:43Z  GET /health → 200
21:59:48Z  GET /health → 200
21:59:53Z  GET /health → 200
21:59:58Z  GET /health → 200
```

**Conclusion:** The FastAPI application starts correctly, listens on port 8000, and responds to Render's internal health checks with HTTP 200. The container is operational.

## 3. External Access Failure — Primary Evidence

### 3.1 HTTPS (Port 443) — TLS Handshake Timeout

Multiple HTTPS attempts all fail during the TLS handshake. The TCP connection succeeds but the TLS ServerHello is never received.

**Test at 22:09:52 UTC:**
```
Host: hi-myrepo-backend.onrender.com:443
Resolved: 216.24.57.7
TCP connect: 54ms ✅
TLS handshake: TIMEOUT after 5160ms ❌
curl error: (28) SSL/TLS connection timeout
```

**Test at 22:13:06 UTC (Python, both IPs):**
```
216.24.57.7:443 → TCP: 30ms ✅  TLS: TIMEOUT after 8048ms ❌
216.24.57.15:443 → TCP: 31ms ✅  TLS: TIMEOUT after 8037ms ❌
```

### 3.2 HTTP (Port 80) — Connection Reset After ~19 Seconds

HTTP requests connect, the request is sent, but no response data is ever received. After exactly ~19 seconds, the connection is reset by the Render proxy.

**Test at 22:10:11 UTC:**
```
Host: hi-myrepo-backend.onrender.com:80
Connected to 216.24.57.7:80
TCP connect: <100ms ✅
Request sent: GET /health HTTP/1.1
Response: NONE (0 bytes)
After 19.2s: "Recv failure: Connection was reset"
```

**Test at 22:10:42 UTC (second IP):**
```
Connected to 216.24.57.15:80
TCP connect: <100ms ✅
Response: NONE (0 bytes)
After 19.2s: "Recv failure: Connection was reset"
```

### 3.3 Python Raw Socket Analysis (Port 80)

```
216.24.57.7:80  → TCP: 22ms ✅  Request sent  → 0 bytes received in 3s ❌
```

The Render proxy accepts the TCP connection, accepts the HTTP request, but never sends any response data.

## 4. Render Edge IPs Tested

Both Render edge IPs produce identical behavior:

| IP | Port | TCP | TLS/HTTP | Reset Time |
|----|------|-----|----------|------------|
| 216.24.57.7 | 443 | ✅ (30-54ms) | TLS TIMEOUT | N/A |
| 216.24.57.15 | 443 | ✅ (31ms) | TLS TIMEOUT | N/A |
| 216.24.57.7 | 80 | ✅ (22-34ms) | 0 bytes | ~19s |
| 216.24.57.15 | 80 | ✅ (<100ms) | 0 bytes | ~19s |

## 5. Phone Hotspot Verification

The same external access failure was independently reproduced from a phone hotspot (different network path, different ISP), confirming this is not a single-ISP routing issue.

## 6. Multiple Unrelated onrender.com Services Tested

To determine whether this is service-specific or platform-wide, we tested **four unrelated `.onrender.com` services** — including services that are NOT ours and a deliberately non-existent hostname:

### 6.1 HTTPS (TLS) Comparison

| Service | TCP Connect | TLS Result |
|---------|-------------|------------|
| hi-myrepo-backend (ours) | 46ms ✅ | TIMEOUT after 6066ms ❌ |
| drewscroll (unrelated) | 121ms ✅ | TIMEOUT after 6147ms ❌ |
| healthcheck-monitor (unrelated) | 115ms ✅ | TIMEOUT after 6149ms ❌ |
| render-wake-up (unrelated) | 91ms ✅ | TIMEOUT after 6109ms ❌ |
| this-does-not-exist-xyz (non-existent) | 101ms ✅ | TIMEOUT after 6s ❌ |

### 6.2 HTTP (Port 80) Comparison

| Service | TCP Connect | Response | Behavior |
|---------|-------------|----------|----------|
| hi-myrepo-backend (ours) | 34ms ✅ | 0 bytes | NO RESPONSE |
| drewscroll (unrelated) | 24ms ✅ | 0 bytes | NO RESPONSE |
| healthcheck-monitor (unrelated) | 23ms ✅ | 0 bytes | NO RESPONSE |
| this-does-not-exist-xyz (non-existent) | 101ms ✅ | 0 bytes | NO RESPONSE |

**All four services — including services unrelated to ours and a hostname that does not exist — show identical external behavior.**

## 7. Control Tests (Non-Render Services)

To confirm this is not a general network issue from our machine:

| Service | Domain | TCP | TLS | HTTP | Total Time |
|---------|--------|-----|-----|------|------------|
| httpbin.org | 3.234.68.252 | 269ms ✅ | 806ms ✅ | 200 OK ✅ | 1.06s |
| Render status page | status.render.com | 121ms ✅ | 238ms ✅ | 200 OK ✅ | 0.55s |

Both non-`*.onrender.com` services respond normally from the same machine.

## 8. DNS Resolution (Verified Correct)

```
hi-myrepo-backend.onrender.com
  → CNAME: gcp-us-west1-1.origin.onrender.com
  → A: 216.24.57.7
  → A: 216.24.57.15
```

DNS resolves correctly. The issue is not DNS-related.

## 9. External Requests Never Reach FastAPI

**Correlation test at 22:09–22:14 UTC:**

- External HTTPS/HTTP requests were made at precisely recorded timestamps
- Render application logs show NO corresponding request entries for any of these timestamps
- Render's only log entries are its own internal health checks (21:59:38–21:59:58)
- The failure occurs **before application ingress** — at the Render proxy/TLS termination layer

```
EXTERNAL CLIENT
      │
      ▼ TCP CONNECT ✅
      │
      ▼ TLS HANDSHAKE ← TIMEOUT (proxy never responds)
      │
      ▼ (no TLS = no HTTP)
      │
      ▼ FastAPI application ← Never sees the request
```

## 10. Render Status Page State

As of 2026-09-01T21:13:53Z, Render's status page reports:

```json
{
  "status": {
    "indicator": "none",
    "description": "All Systems Operational"
  }
}
```

Note: The status page is hosted on `status.render.com` (separate infrastructure), not on `*.onrender.com`.

## 11. Render Service State

| Check | Result |
|-------|--------|
| Deploy status | "Deploy succeeded \| Live" |
| Internal health checks | Passing (200) |
| Container startup | Uvicorn started at 21:59:25Z |
| Application ready | 21:59:30Z (5 seconds startup) |
| Service marked live | 21:59:38Z |
| Free-tier spin-down | NOT triggered (service confirmed running) |

---

## Distinguishing Facts from Inference

### Proven Service-Level Facts

1. The FastAPI container starts successfully in 5 seconds
2. Uvicorn listens on 0.0.0.0:8000
3. GET /health returns HTTP 200
4. Render's internal health checks pass continuously
5. Render's dashboard shows "Deploy succeeded | Live"

### Proven External Ingress Behavior

1. TCP connections to both Render edge IPs (216.24.57.7, 216.24.57.15) succeed in 22-54ms on both ports 80 and 443
2. TLS handshake to `hi-myrepo-backend.onrender.com` never completes (timeout)
3. HTTP on port 80: request is sent, 0 bytes received, connection reset after ~19 seconds
4. **All four tested `.onrender.com` services** (including unrelated and non-existent hostnames) show identical behavior
5. External requests never appear in FastAPI application logs
6. Non-Render HTTPS services (httpbin.org, status.render.com) work normally from the same machine
7. The same failure was reproduced from a phone hotspot (different network/ISP)

### Inference About Render Infrastructure

The evidence is consistent with the following hypothesis:

**Render's external TLS termination and ingress proxy for `*.onrender.com` domains is not serving external traffic.** The proxy accepts TCP connections but does not complete TLS handshakes and does not forward HTTP requests to backend services.

This could be caused by:
- A platform-level issue with the `*.onrender.com` external ingress layer
- A regional issue affecting `gcp-us-west1-1` edge nodes
- A configuration change affecting free-tier external access
- A certificate provisioning issue for the `*.onrender.com` wildcard

**Note:** We do not have evidence of a global Render outage. The status page reports "All Systems Operational." However, `status.render.com` is hosted on separate infrastructure and does not prove that `*.onrender.com` external ingress is functioning.

---

## Requested Actions

1. **Verify the external TLS termination layer** for `*.onrender.com` services in the `gcp-us-west1-1` region
2. **Check for any recent changes** to the free-tier external ingress configuration
3. **Verify the wildcard TLS certificate** provisioning status for `*.onrender.com`
4. **Test external access** to an arbitrary `*.onrender.com` service from a known-good network to confirm whether this is regional or global
5. **Provide a status update** on whether free-tier external access is currently expected to work

## Contact

- **Service URL:** https://hi-myrepo-backend.onrender.com
- **Dashboard:** Render Dashboard → hi-myrepo-backend
- **Incident window:** 2026-09-01 21:48 UTC — ongoing
