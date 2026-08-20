# Feast MCP Server — Architecture & Design Decisions

This document records *why* the Feast MCP server is built the way it is. Each
section is one decision: the context it was made in, what was decided, why, and
what we gave up. It complements the [Development guide](../development.md)
(which explains the code layout) and the [Configuration](../configuration.md)
and [Deployment](../deployment.md) guides (which explain how to run it).

## Overview

The Feast MCP server is a **thin, stateless gateway**. It exposes Feast to AI
clients (Cursor, VS Code, Claude, …) as Model Context Protocol (MCP) tools, and
turns each tool call into an HTTP call against your existing Feast servers.

```
AI client ──MCP──> feast-mcp ──HTTP──> Feast feature server  (online features, vector search, push)
 (Cursor,          (this repo)   └────> Feast registry server (projects, entities, feature views)
  Claude, …)
```

It owns no features, no registry, and no permissions of its own — those all
live in Feast. That single idea drives most of the decisions below.

---

## 1. A thin, stateless proxy that owns no data

**Context.** Feast already has a feature server and a registry server with
their own APIs and permission model. We needed to expose that to MCP clients.

**Decision.** The MCP server stores nothing. Every tool takes arguments, calls
a Feast HTTP endpoint through a small shared client (`client.py`), and returns
the result. There is no cache, no database, no local registry copy.

**Why.**
- One source of truth. Features and permissions never drift from Feast.
- Horizontal scaling is trivial — any replica can serve any request because
  there is no per-node state to keep in sync (the one exception, OIDC login
  state, is addressed in decision 4).
- The codebase stays small: understand one tool and you understand them all.

**Trade-offs.** Every tool call is a network hop to Feast; the MCP server adds
latency and cannot serve anything Feast can't. We accept that — correctness and
simplicity matter more than shaving a hop.

---

## 2. Compose two sub-servers behind one endpoint

**Context.** Feast splits its API across two services (feature server and
registry server). A client should still see a single MCP endpoint.

**Decision.** Build on **FastMCP** and mount two sub-servers under namespaces:
`features` and `registry`. Tools are exposed namespaced (e.g.
`features_get_online_features`, `registry_list_feature_views`). Each sub-server
is mounted only when its upstream URL is configured (`--feast-url` /
`--registry-url`), so you can run features-only, registry-only, or both.

**Why.**
- Namespacing keeps tool names unambiguous and lets the two Feast services
  evolve independently.
- Optional mounting means one binary covers every deployment shape without
  feature flags.

**Trade-offs.** The `features_` / `registry_` prefixes are part of the client
contract — renaming a namespace is a breaking change for callers. Clients (and
the demo client) must use the namespaced names.

---

## 3. Authorization by token pass-through, not our own RBAC

**Context.** Feast enforces its own permission model (OIDC / Kubernetes SA
tokens). Re-implementing authorization in the MCP layer would duplicate it and
risk the two drifting apart.

**Decision.** The MCP server does **not** enforce RBAC. It forwards the
caller's bearer token upstream to Feast on every tool call, and Feast decides
what that token may do. Two modes are supported:

- **Passthrough** (default): connections are accepted as-is; the client already
  holds a valid token (or none, for local dev).
- **OIDC** (`--auth-mode oidc`): an OIDC proxy discovers endpoints from the
  same discovery URL Feast uses and runs a browser login flow so IDE clients
  can sign in. Programmatic clients can also send OIDC provider tokens directly
  as bearer tokens — those are validated against the provider's JWKS as a
  fallback.

**Why.**
- Single, authoritative permission model (Feast's). No second place to get
  authorization wrong.
- IDE clients get a real login flow; scripts get a simple token path.

**Trade-offs.** The MCP server is only as safe as the token it forwards; it
deliberately does not add its own allow/deny layer. (Hiding individual tools —
distinct from authorizing operations — is noted as possible future work.)

---

## 4. Load-balancer-safe, pluggable session storage

**Context.** The OIDC login flow (decision 3) has server-side state — client
registrations, transactions, auth codes, token mappings. FastMCP's default
keeps that on local disk, per node. Behind a load balancer with more than one
replica, a login started on node A can land on node B and break.

**Decision.** Make the OAuth-state store pluggable via an `AsyncKeyValue`
backend, selected with `--session-storage-backend` (redis, valkey, postgresql,
mongodb, disk, memory). A frozen-dataclass config plus a factory builds the
store; the server warns loudly if the chosen backend is **not** shared across
processes. When no backend is set, FastMCP's default (per-node disk) is used.

**Why.**
- OIDC works correctly behind a load balancer with many replicas.
- The rest of the server stays stateless (decision 1); this is the *only*
  shared state, and it's opt-in.

**Trade-offs.** Multi-replica OIDC needs an external store (Redis, etc.) to be
provisioned. Single-replica or passthrough deployments need nothing extra.
Session affinity is still recommended as a simpler alternative when you only
run a couple of replicas.

---

## 5. Layered configuration, with logging resolved first

**Context.** The server runs in very different places — an IDE launching it
over stdio, a container, a Kubernetes pod — each with a different natural way to
configure it.

**Decision.** Resolve every setting from, in priority order: **CLI flags → env
vars → `feast_mcp.yaml` → built-in defaults.** Observability settings live in a
*separate* `LoggingConfig` that is loaded and applied **before** anything else,
so all subsequent setup (mounting, auth, serving) is already visible in the
logs. Standard `OTEL_*` env vars are honored as a fallback so existing
OpenTelemetry tooling works unchanged.

**Why.**
- Flags for quick overrides, env vars for containers, YAML for full configs —
  no one is forced into a style that doesn't fit their environment.
- Configuring logging first means startup problems are never silent.

**Trade-offs.** Two config loaders (main + logging) instead of one. The
separation is deliberate: logging must not depend on the rest of the config
being valid.

---

## 6. Observability: fan-out logging + per-request correlation

**Context.** Operators need to see what the server is doing, tie log lines to a
specific request, and ship telemetry to their existing backend.

**Decision.**
- **Fan-out logging.** Logs always go to the console on **stderr** (stdout is
  reserved by the MCP stdio transport for the protocol). When an OTLP endpoint
  is set, the *same* lines are also exported over OpenTelemetry.
- **Logger bridging.** FastMCP, the MCP SDK, and the web server (uvicorn /
  gunicorn) log to their own logger trees; those are bridged onto the same
  handlers so their output shows up on the console and in OTEL too.
- **Per-request auth logging.** `get_auth_token()` is the choke point every
  tool call passes through, so it logs one line of auth context per request:
  the authenticated user, the client IP (honoring `X-Forwarded-For` /
  `X-Real-IP`), and the request method/path.
- **Per-request trace correlation.** Each HTTP request is wrapped in an
  OpenTelemetry span by an ASGI middleware, so every log line emitted while
  handling that request shares one `trace_id` — making it possible to group
  "all logs for one request." With the OTEL SDK installed it's a real trace id
  and the span is exported too; without it, a generated per-request id keeps
  console logs groupable.

**Why.**
- stderr keeps the stdio JSON-RPC channel clean.
- Bridging means you don't lose framework logs when shipping to a backend.
- A single choke point (`get_auth_token`) is the cheapest reliable place to
  attribute a request to a user.
- Wrapping the request in a span is the OpenTelemetry-native way to correlate
  logs — no manual id threading through every function.

**Trade-offs.** The trace-correlation span middleware is the outermost ASGI
layer, adding a tiny per-request cost. Real trace ids and exported spans depend
on the optional OTEL SDK (decision 8).

---

## 7. Transports and the serving model

**Context.** IDE clients speak MCP over stdio; network deployments need HTTP.

**Decision.** Support `stdio`, `http` / `streamable-http`, and `sse`
transports. For HTTP serving, use **uvicorn** for the single-process case and
**gunicorn** (with uvicorn workers) when `--workers > 1`. SSE is rejected with
more than one worker because its long-lived connections don't fan out across
worker processes.

**Why.**
- stdio is what IDEs launch; HTTP is what you deploy as a service.
- gunicorn gives multi-worker scaling; uvicorn keeps the common single-process
  path simple.

**Trade-offs.** Multiple serving paths to maintain, and an explicit guard rail
against the SSE-plus-workers combination that would silently misbehave.

---

## 8. Optional dependencies with graceful degradation

**Context.** Different users want different features (YAML config, multi-worker
serving, OpenTelemetry, a specific session-storage backend) and shouldn't have
to install what they don't use.

**Decision.** Ship features behind extras — `feast-mcp[yaml]`,
`feast-mcp[server]`, `feast-mcp[otel]`, and the key-value backends. If an
optional package is missing, the server **turns that feature off with a clear
warning** (or tells you the exact `pip install` to run) rather than crashing.

**Why.**
- A minimal install stays minimal.
- A missing optional dependency degrades gracefully — e.g. asking for OTEL
  without the SDK still runs, just console-only, with a warning telling you how
  to enable export.

**Trade-offs.** More import-guarding code, and behavior that varies with what's
installed. We consider that acceptable for a tool meant to run in many
environments.

---

## Status and follow-ups

These decisions reflect the server as it stands today. Ideas being considered
but not yet built (see `Future_work.md`) include dynamic/token-efficient tool
search, a rate limiter and circuit breaker in front of the Feast server,
request pre-validation to fail fast, and tool-level visibility control in the
registry.
