# Static Analysis Pre-Pass: Feasibility Assessment

## The 17 Analysis Models

| # | Model | Key | Description |
|---|-------|-----|-------------|
| 1 | **High-Level Overview** | `hl_overview` | Repository structure, architecture patterns, tech stack |
| 2 | **Module Deep Dive** | `module_deep_dive` | Detailed component analysis, responsibilities, inter-module dependencies |
| 3 | **Dependencies** | `dependencies` | Internal modules and external library mapping |
| 4 | **Core Entities** | `core_entities` | Domain models, attributes, and relationships |
| 5 | **Databases** | `DBs` | SQL/NoSQL databases, schemas, access methods |
| 6 | **APIs** | `APIs` | HTTP API endpoints, methods, payloads, responses |
| 7 | **Events** | `events` | Event systems, message brokers, topics, payloads |
| 8 | **Service Dependencies** | `service_dependencies` | External API calls, event brokers, cloud SDKs |
| 9 | **Deployment** | `deployment` | CI/CD pipelines, infrastructure, containerization |
| 10 | **Authentication** | `authentication` | Auth methods, identity providers, credential management |
| 11 | **Authorization** | `authorization` | Access control, RBAC/ABAC, permission structures |
| 12 | **Data Mapping** | `data_mapping` | Data flows, PII mapping, compliance-relevant handling |
| 13 | **Security Check** | `security_check` | Top 10 security vulnerability assessment |
| 14 | **Monitoring** | `monitoring` | Logging, metrics, tracing, alerting, observability |
| 15 | **ML Services** | `ml_services` | 3rd-party ML APIs, frameworks, ML infrastructure |
| 16 | **Feature Flags** | `feature_flags` | Feature flag platforms, SDKs, usage patterns |
| 17 | **Prompt Security Check** | `prompt_security_check` | LLM prompt injection and security risk assessment |

## Overview

This document evaluates whether the 17 analysis models above can be replicated using static analysis (without AI), and proposes a hybrid approach that combines static extraction with targeted LLM reasoning.

## What Static Analysis CAN Cover Well

| Model | Tool / Technique | Coverage |
|-------|-----------------|----------|
| **Dependencies** | Parse `package.json`, `requirements.txt`, `go.mod`, etc. | ~85% |
| **Deployment** | Parse GitHub Actions YAML, Dockerfiles, k8s manifests | ~90% |
| **APIs** | Route extraction from Express/Flask/FastAPI via AST | ~70% |
| **Databases** | ORM model parsing, connection string regex, migration files | ~75% |
| **Events** | Message queue SDK import detection, handler patterns | ~70% |
| **Monitoring** | Library import detection (DataDog, Sentry, etc.) | ~80% |
| **ML Services** | Import scanning for `openai`, `torch`, `anthropic`, etc. | ~80% |
| **Feature Flags** | LaunchDarkly/Flagsmith SDK detection, config parsing | ~75% |

Existing tools that do parts of this: `madge`, `dependency-cruiser`, `semgrep`, `snyk`, `trivy`, `swagger-jsdoc`, `pyan`, `jscpd`.

## What Static Analysis CANNOT Replicate

| Model | Why AI is Needed |
|-------|-----------------|
| **High-Level Overview** | Requires understanding intent — what the project is for, why it's structured this way |
| **Module Deep Dive** | Requires reasoning about responsibilities, not just listing imports |
| **Core Entities** | Domain model relationships and meaning go beyond AST parsing |
| **Security Check** | Real vulnerability assessment requires contextual reasoning (is this SQL concatenation actually exploitable? is this auth bypass reachable?) |
| **Data Mapping** | PII flow tracing and compliance implications require business logic understanding |
| **Authentication** | Distinguishing auth strategies from code patterns requires semantic understanding |
| **Authorization** | RBAC/ABAC logic is deeply embedded in business logic |
| **Prompt Security** | Prompt injection risk assessment requires understanding LLM attack vectors in context |

## The Core Gap

The system currently feeds raw file contents and directory structure to the LLM (up to 180K tokens) and asks it to reason about architecture. Static tools can **detect** (what libraries, what files, what patterns) but cannot **synthesize** (why this architecture, what are the risks, how do components relate semantically).

For example:

- **Static:** "This project imports `jsonwebtoken` and has a `/login` route"
- **AI:** "Authentication uses JWT with RS256, tokens are issued at login, validated via middleware on protected routes, but refresh token rotation is missing — creating a session fixation risk"

## Speed Impact

A static pre-pass would be **faster overall**. Currently the system sends up to 180K tokens of raw file content per analysis step across 17 sequential steps. A static pre-pass would:

- Replace raw file scanning with structured facts (smaller payloads, faster LLM calls)
- Run in seconds (AST parsing, regex, config parsing are near-instant)
- Reduce or eliminate the map-reduce batching needed for large repos (e.g., the `dependencies` model)

The LLM steps that remain would run faster because they receive pre-digested input instead of raw source files.

## Quality Impact

Quality would likely **improve for some models** and stay neutral for others:

| Effect | Why |
|--------|-----|
| **Improved** | Static tools are exhaustive — they won't miss a route definition buried in file 847 that gets truncated at the token limit. The current system truncates repo content to fit 180K tokens, so large repos lose coverage. |
| **Improved** | Structured input (e.g., a complete dependency list with versions) gives the LLM better signal-to-noise for its synthesis step |
| **Improved** | Deterministic extraction means no hallucinated endpoints or phantom dependencies |
| **Neutral** | For reasoning-heavy models (security, architecture, data mapping), quality depends on the LLM regardless |
| **Risk** | A poorly-written static extractor could miss non-standard patterns (e.g., dynamically registered routes, meta-programmed models). The LLM's flexibility with raw code handles these edge cases better |

## The Real Risk

The only quality concern is coverage of non-standard patterns. Static tools are brittle against:

- Dynamic route registration (`app.use(routeFactory(config))`)
- Metaprogrammed ORM models
- Convention-over-configuration frameworks where intent is implicit

This is solvable: use static extraction as the primary source and fall back to LLM analysis of raw code only for files/patterns the static pass couldn't confidently parse.

## Proposed Hybrid Approach

1. **Pre-pass with static tools** — dependency parsing, route extraction, import scanning, config file analysis
2. **Feed structured results to AI** — instead of raw files, give the LLM pre-extracted facts
3. **Use AI only for synthesis** — architecture reasoning, security assessment, relationship inference

This would cut token usage significantly while keeping the high-value AI reasoning where it matters most.

## Bottom Line

A well-implemented pre-pass would be **faster and equal-or-better quality** for most models. The key word is "well-implemented" — it requires building reliable extractors per language/framework, which is upfront engineering effort. The current all-LLM approach trades compute cost for implementation simplicity.
