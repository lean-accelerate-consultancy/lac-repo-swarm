# RepoSwarm -- Full Workflow Guide

End-to-end guide to analyse repos with Claude and generate cross-repo Mermaid diagrams with PNG rendering.

---

## Analysis steps

Each repository is analysed by Claude using a sequence of prompted steps. All repo types share 17 base steps; some types add extra steps.

### Base steps (all repo types)

| # | Step | Description |
|---|------|-------------|
| 1 | hl_overview | High-level overview of the codebase |
| 2 | module_deep_dive | Deep dive into modules |
| 3 | dependencies | Dependencies and external libraries |
| 4 | core_entities | Core entities and their relationships |
| 5 | DBs | Database analysis |
| 6 | APIs | API analysis |
| 7 | events | Event analysis |
| 8 | service_dependencies | Service dependencies |
| 9 | deployment | Deployment processes and CI/CD pipelines |
| 10 | authentication | Authentication mechanisms |
| 11 | authorization | Authorization and access control |
| 12 | data_mapping | Data flow and personal information mapping |
| 13 | security_check | Top 10 security vulnerabilities assessment |
| 14 | monitoring | Monitoring, logging, metrics, and observability |
| 15 | ml_services | 3rd-party ML services and technologies |
| 16 | feature_flags | Feature flag frameworks and usage patterns |
| 17 | prompt_security_check | LLM and prompt injection vulnerability assessment |

### Type-specific additional steps

| Repo type | Extra steps | Description |
|-----------|-------------|-------------|
| backend | data_layer | Data persistence and access patterns |
| backend | events_and_messaging | Asynchronous communication and event patterns |
| frontend | components | Component architecture and design patterns |
| frontend | state_and_data | State management and data flow patterns |
| infra-as-code | resources | Detailed analysis of infrastructure resources |
| infra-as-code | environments | Environment management and deployment strategies |
| libraries | api_surface | Public API analysis and design patterns |
| libraries | internals | Internal architecture and implementation |
| mobile | ui_and_navigation | UI architecture and navigation patterns |
| mobile | api_and_network | API integration and network communication |
| mobile | device_features | Native device features and capabilities |
| mobile | data_and_persistence | Data persistence and state management |
| generic | _(none)_ | Uses base steps only |

### Gap analysis: AI mode vs Static Analyser mode

Each step produces output in both modes, but the depth and nature of analysis differs. AI mode (Claude) provides interpretive, architectural analysis; Static Analyser mode provides inventory-level, pattern-matched output.

| # | Step | AI Mode (Claude) | Static Analyser Mode |
|---|------|-------------------|----------------------|
| 1 | hl_overview | Reads entire repo structure. Identifies project purpose, architecture pattern, tech stack, languages, frameworks, config/package files, directory purpose, high-level architecture, build/run/test entry points. Narrative output from a senior architect perspective. | `LanguageDetector` scans files — reports LOC by language, tech stack list, framework detection. Reads first line of README for purpose. Dumps directory tree (truncated at 80 lines). |
| 2 | module_deep_dive | Uses prior overview as context. For each component: core responsibility, key sub-directories/files/classes/functions with roles, internal import dependencies, external service interactions. | Directory walker — counts files and subdirectories per top-level folder. Lists sub-packages with file counts. No code reading, no import analysis. |
| 3 | dependencies | Uses prior overview as context. Analyses internal modules (purpose of each), and every external dependency from package files — maps each to official name, role in project, source file. Reads full dependency files. | If `deps_data` provided from `read_dependencies_activity`: uses it. Otherwise lists dependency file names found (package.json, requirements.txt etc.) without parsing contents. |
| 4 | core_entities | Identifies domain models/data entities, their key attributes/fields, and relationships (1:M, M:M). Works from code structure inspection. | `EntityParser` — regex-based class/struct detection across languages. Finds class names but no attribute extraction or relationship mapping. |
| 5 | DBs | Expert database architect analysis. Per database: type, purpose/role, access methods (ORM/SDK), key files, schema/table structure with columns and keys, entity relationships, interacting components. Returns "no database" if none found. | `DatabaseScanner` — detects database config files, ORM patterns, connection strings. Reports technology detected but no schema extraction or query analysis. |
| 6 | APIs | Expert API documentation. Per endpoint: HTTP method, full URL path, request payload (JSON schema/example), response payload, purpose. Infers payloads from request handling code. | `APIScanner` — detects route definitions by framework patterns (Express, Flask, Spring etc.). Lists endpoints found but no payload inference or schema extraction. |
| 7 | events | Per event: broker type (SQS/Kafka/EventBridge etc.), event name/topic/queue, direction (producing/consuming), payload schema, purpose. Infers from SDK calls. | `EventDetector` — detects pub/sub patterns, message broker SDK usage. Reports event systems found but no payload analysis. |
| 8 | service_dependencies | Uses overview + APIs + events as context. Maps every external dependency: name, type, purpose, integration points. Covers APIs, brokers, databases, cloud SDKs, config files, monitoring tools, containers. | `TerraformParser` — parses Terraform `resource` blocks, data sources, module references. Strong for IaC repos (extracts full resource graph). Returns empty for non-Terraform repos. |
| 9 | deployment | Uses overview + dependencies as context. 15-section analysis: CI/CD platform, pipeline stages/triggers/artifacts, deployment targets, IaC, build process, testing in pipeline, release management, rollback strategy, access control, anti-patterns, manual procedures, multi-deployment, coordination, performance, documentation. | `DeploymentScanner` — detects CI/CD config files (GitHub Actions, CircleCI, Jenkins etc.), Dockerfiles, Kubernetes manifests. Reports file presence but no pipeline flow analysis or anti-pattern detection. |
| 10 | authentication | Security architect analysis. Covers: auth type (JWT/OAuth/SAML etc.), identity providers, credential management, token lifecycle, session management, login/logout/registration/password recovery flows, middleware, security headers, cookies, biometric, API keys, service-to-service auth, OAuth flows, vulnerabilities. | `SecurityScanner` + `TerraformParser` — detects auth framework imports, IAM/Cognito Terraform resources. Reports technologies present but no flow analysis, token lifecycle, or vulnerability assessment. |
| 11 | authorization | Security architect analysis. Covers: RBAC/ABAC/ACL models, permission structure/hierarchy, role/group management, middleware/guards, resource access control, policy engine, database schema, API endpoint protection, UI authorization, multi-tenancy, delegation/impersonation, audit/compliance, dynamic authorization, integration points, vulnerabilities. | `SecurityScanner` + `TerraformParser` — detects security group, IAM policy, WAF, ACL Terraform resources. Reports resource types but no permission model analysis or access control evaluation. |
| 12 | data_mapping | Data privacy/compliance expert analysis. Maps complete data flow: collection points, internal processing, third-party processors, outputs. Categorises personal identifiers, sensitive data, business data. Covers retention, GDPR/CCPA/HIPAA compliance, data subject rights, cross-border transfers, security controls, breach risks, third-party sharing, risk assessment. | `DataMappingScanner` — regex patterns for PII field names (email, phone, SSN etc.) across source files. Reports field matches but no data flow tracing, retention analysis, or compliance assessment. |
| 13 | security_check | Security auditor — top 10 critical vulnerabilities with file locations and line numbers. Covers: auth/session, authorization/IDOR, injection (SQL/command/template), data exposure (hardcoded secrets, sensitive logs), crypto issues, input validation/XSS/XXE, misconfig, vulnerable dependencies with CVE checks, business logic flaws (race conditions, TOCTOU), API security. Provides severity, vulnerable code, impact, fix, secure implementation. | `SecurityScanner` — regex for hardcoded secrets (API keys, passwords, tokens), security headers, known vulnerable patterns. Reports matches found but no severity ranking, impact analysis, or fix recommendations. |
| 14 | monitoring | Monitoring/observability expert. Covers: observability platforms, logging frameworks (language-specific), log management infrastructure, metrics collection libraries, application/infrastructure/custom metrics, distributed tracing, health checks, circuit breakers, alerting, APM, error tracking, RUM, synthetic monitoring, database monitoring, queue monitoring, cost monitoring, dashboards. Checks raw dependencies to catch missed tools. | `MonitoringScanner` — detects logging framework imports, metrics library usage, monitoring SDK patterns. Reports tools detected but no infrastructure analysis, alerting evaluation, or observability gap assessment. |
| 15 | ml_services | Uses overview as context. Documents every ML integration: type (API/local/framework), purpose, integration points, configuration (model, temperature, max_tokens), data flow, access controls, security/compliance, cost, reliability patterns. Summary with total count, major dependencies, architecture pattern, risk assessment. | Terraform ML resource detection (SageMaker, Bedrock etc.) + `PromptSecurityScanner` LLM SDK import detection. Reports resources/imports found — no configuration analysis, data flow, or risk assessment. |
| 16 | feature_flags | Feature flag expert. Per flag: name, type, purpose, default value, code locations, evaluation pattern, impact of toggle. Framework configuration, flag categories (release/kill-switch/A/B/config), context/targeting. | `FeatureFlagScanner` — detects flag framework imports (LaunchDarkly, Flagsmith, Unleash etc.) and boolean check patterns. Reports frameworks detected but no flag inventory or impact analysis. |
| 17 | prompt_security_check | Uses overview + ml_services as context. 7 detection strategies for LLM usage. Per usage: type, technology, location, purpose, config, data flow, access controls. Then vulnerability assessment: lethal trifecta analysis, string concatenation injection, markdown exfiltration, tool calling security, input sanitisation, system prompt protection, output validation, MCP security, RAG poisoning, multi-agent security, API key management. Per vulnerability: severity, location, attack scenario, mitigation. | `PromptSecurityScanner` — detects LLM SDK imports, API client instantiation patterns, prompt template files. Reports findings but no lethal trifecta analysis, attack scenarios, or vulnerability severity assessment. |
| IaC-1 | resources | Infrastructure analyst. Categorises: compute (instances, containers, serverless), networking (VPCs, subnets, SGs, LBs, DNS), storage/databases (S3, RDS, DynamoDB), security/identity (IAM, secrets management), orchestration/deployment. Per resource: type, name, purpose, key configs, dependencies, cost implications. | `TerraformParser` — parses all Terraform `.tf` files. Extracts resource blocks with type, name, file location. Reports full resource inventory with categorisation. |
| IaC-2 | environments | Infrastructure environment specialist. Analyses: environment identification (dev/staging/prod), variable management (tfvars, values.yaml), resource segregation (naming, network isolation), deployment strategy (blue-green/canary), scaling differences, access control per environment, disaster recovery (backup, RTO/RPO, cross-region). | `TerraformParser` — detects workspace/environment patterns, tfvars files, environment-specific variable files. Reports environment structure found but no strategy assessment or DR analysis. |

---

## Modes of operation

RepoSwarm supports 6 modes. Pick the one that fits your use case:

| Mode | Description | Claude API? | GitHub token? | Architecture Hub? | Run command |
|------|-------------|-------------|---------------|-------------------|-------------|
| **1. Local repos, Claude only** | Analyse repos on disk with Claude, save results locally. | Yes | No | No | `mise investigate-local` |
| **2. Remote repos, Claude + Hub** | Clone from GitHub, analyse with Claude, push results to Architecture Hub. | Yes | Yes | Yes | `mise investigate-all` |
| **3. Remote repos, Claude only** | Clone from GitHub, analyse with Claude, save results locally. | Yes | Yes | No | `mise investigate-all` |
| **4. Diagrams only** | Skip investigation, regenerate cross-repo diagrams/PNGs from cached results. | Yes | No | No | `mise investigate-local` |
| **5. Local repos, Static Analysis** | Analyse repos on disk with static analysis only. No AI, no API key needed. | No | No | No | `mise investigate-local` |
| **6. Local repos, Static Analysis + Diagrams** | Static analysis + programmatic Mermaid diagram generation. No AI needed. | No | No | No | `mise investigate-local` |

Modes 1-4 require an `ANTHROPIC_API_KEY`. Modes 5-6 set `ENABLE_AI=false` and use programmatic static analysis instead of Claude -- no API key or credits required.

Each mode requires different env vars in `.env.local` -- see `env.local.example` for full details.

---

## Prerequisites

- Python 3.12 (managed via mise)
- Anthropic API key with credits at [console.anthropic.com](https://console.anthropic.com) -- not needed for Mode 5/6
- Docker (via Colima or Docker Desktop) -- only needed for PNG rendering
- For Mode 1/4/5/6: repos cloned locally
- For Mode 2/3: GitHub token with repo scope

---

## 1. Install dependencies

```bash
cd ~/git-repos/repo-swarm-2
mise install
uv sync
```

---

## 2. Configure environment

Copy the example and edit:

```bash
cp env.local.example .env.local
```

Set these values in `.env.local`. Pick one of the examples below:

### Mode 1 -- Local repos with Claude (AI analysis)

```bash
ANTHROPIC_API_KEY=sk-ant-your-key-here
LOCAL_TESTING=true
LOCAL_MODE=true
PROMPT_CONTEXT_STORAGE=file
SKIP_DYNAMODB_CHECK=true
CREATE_DIAGRAMS=true
LOCAL_OUTPUT_DIR=outputs

# Temporal (defaults are fine for local dev)
TEMPORAL_SERVER_URL=localhost:7233
TEMPORAL_NAMESPACE=default
TEMPORAL_TASK_QUEUE=investigate-task-queue
TEMPORAL_IDENTITY=local-worker
```

### Mode 5 -- Local repos with Static Analysis (no AI, no API key)

```bash
ENABLE_AI=false
LOCAL_TESTING=true
LOCAL_MODE=true
PROMPT_CONTEXT_STORAGE=file
SKIP_DYNAMODB_CHECK=true
LOCAL_OUTPUT_DIR=outputs

# Temporal (defaults are fine for local dev)
TEMPORAL_SERVER_URL=localhost:7233
TEMPORAL_NAMESPACE=default
TEMPORAL_TASK_QUEUE=investigate-task-queue
TEMPORAL_IDENTITY=local-worker
```

### Mode 6 -- Static Analysis + Diagrams (no AI, no API key)

```bash
ENABLE_AI=false
CREATE_DIAGRAMS=true
LOCAL_TESTING=true
LOCAL_MODE=true
PROMPT_CONTEXT_STORAGE=file
SKIP_DYNAMODB_CHECK=true
LOCAL_OUTPUT_DIR=outputs

# PNG rendering (optional -- requires Docker)
RENDER_MERMAID_PNGS=true
# MERMAID_DOCKER_IMAGE=repo-swarm-mermaid:local
# MERMAID_RENDER_TIMEOUT=120

# Temporal (defaults are fine for local dev)
TEMPORAL_SERVER_URL=localhost:7233
TEMPORAL_NAMESPACE=default
TEMPORAL_TASK_QUEUE=investigate-task-queue
TEMPORAL_IDENTITY=local-worker
```

---

## 3. Configure repos to analyse

Edit `prompts/repos.json` to define which repositories to analyse.

### Option A -- Remote GitHub repos

Use this when analysing public or private GitHub repositories (requires `GITHUB_TOKEN` in `.env.local` for private repos):

```json
{
  "default": "https://github.com/facebook/react",
  "_comment": "Available types: generic, backend, frontend, mobile, infra-as-code, libraries",
  "repositories": {
    "react": {
      "uri": "https://github.com/facebook/react",
      "description": "React core library - the foundation of the React ecosystem",
      "type": "frontend"
    },
    "react-router": {
      "uri": "https://github.com/remix-run/react-router",
      "description": "Declarative routing for React",
      "type": "frontend"
    },
    "redux-toolkit": {
      "uri": "https://github.com/reduxjs/redux-toolkit",
      "description": "Official Redux toolset for state management",
      "type": "libraries"
    }
  }
}
```

**Notes (remote mode):**
- `uri` must be a full GitHub URL (`https://github.com/owner/repo`)
- `default` sets which repo is used by `mise investigate-one` when no repo is specified
- Requires `LOCAL_MODE=false` (or unset) and `LOCAL_TESTING=false` in `.env.local`
- Run with `mise investigate-all` or `mise investigate-one`

### Option B -- Local repos on disk

Use this when analysing repos already cloned locally (no GitHub access needed):

```json
{
  "default": "file:///Users/qwerty/git-repos/Terraform/EmrWithVpc/aws-terraform-emr-network/src/main/terraform",
  "_comment": "Available types: generic, backend, frontend, mobile, infra-as-code, libraries",
  "repositories": {
    "aws-terraform-emr-network": {
      "uri": "file:///Users/qwerty/git-repos/Terraform/EmrWithVpc/aws-terraform-emr-network/src/main/terraform",
      "description": "Terraform AWS EMR",
      "type": "infra-as-code"
    },
    "terraform-cf-integration": {
      "uri": "file:///Users/qwerty/git-repos/Github/tek-edf-emr/terraform-cf-integration",
      "description": "Cloudformation AWS EMR",
      "type": "infra-as-code"
    },
    "emr-with-vpc": {
      "uri": "file:///Users/qwerty/git-repos/Github/tek-edf-emr/emr-with-vpc",
      "description": "IaC EMR",
      "type": "infra-as-code"
    }
  }
}
```

**Notes (local mode):**
- `uri` uses the `file://` scheme followed by the absolute path to the repo on disk
- Requires `LOCAL_MODE=true` and `LOCAL_TESTING=true` in `.env.local`
- Run with `mise investigate-local`

**Common notes:**
- The `uri` field uses standard URI schemes: `https://` for remote repos, `file://` for local repos
- `type` helps Claude tailor its analysis -- valid types: `backend`, `frontend`, `mobile`, `infra-as-code`, `libraries`, `generic`
- `description` gives Claude context about what each repo does

---

## 4. Build the Mermaid Docker image (one-time)

Skip this step if you set `RENDER_MERMAID_PNGS=false`.

```bash
# Start Docker runtime
colima start

# Build the mermaid rendering image
mise mermaid-build

# Verify it works
mise mermaid-test
```

---

## 5. Run the analysis

Open **3 terminals**, all in `~/git-repos/repo-swarm-2`:

### Terminal 1 -- Temporal server

```bash
mise dev-server
```

Wait for `Temporal server is running` message.

### Terminal 2 -- Worker

```bash
mise dev-worker
```

Wait for `TEMPORAL WORKER IS RUNNING` message.

### Terminal 3 -- Start investigation

```bash
mise investigate-local
```

### What happens

1. Reads repos from `prompts/repos.json`
2. For each repo with a `file://` URI:
   - Scans directory structure
   - **If `ENABLE_AI=true` (default):** Runs 17 analysis steps via Claude (architecture, APIs, dependencies, security, etc.)
   - **If `ENABLE_AI=false`:** Runs programmatic static analysis using 11 specialized scanners (language detection, API scanning, Terraform parsing, security analysis, etc.) -- no API calls
   - Writes `outputs/{repo-name}-arch.md`
3. If `CREATE_DIAGRAMS=true`:
   - Combines all repo analyses
   - **If `ENABLE_AI=true`:** Generates 3 Mermaid diagram types via Claude
   - **If `ENABLE_AI=false`:** Generates 8 Mermaid diagram types programmatically via MermaidDiagramGenerator:
     - Cross-Repository Lifecycle (`graph LR`) -- how all repos work together
     - Network/Architecture Overview (`graph TD`) -- repos + AWS service nodes with edges
     - Technology Stack (`graph LR`) -- tech items per repo with cross-tech edges
     - Infrastructure Architecture (`graph TD`) -- layered resource view
     - Data Flow (`flowchart LR`) -- end-to-end pipeline with 6+ subgraphs
     - Module Structure (`graph TD`) -- per-repo directory breakdown
     - Language Distribution (pie chart)
     - Sequence Diagrams -- IaC provisioning, CloudFormation integration, EMR runtime
   - Also generates narrative sections: Key Connections, Data Flow Summary, Governance Concerns
   - Writes `outputs/diagrams/architecture-overview.md`
4. If `RENDER_MERMAID_PNGS=true`:
   - Extracts each mermaid code block to a `.mmd` file
   - Renders each to `.png` via Docker (falls back to local `mmdc` if Docker unavailable)

---

## 6. View outputs

```bash
# Per-repo analysis files
ls -lh outputs/*.md

# Cross-repo diagrams (markdown + PNG)
ls -lh outputs/diagrams/
```

### Output structure

**AI mode** (`ENABLE_AI=true`):
```
outputs/
|-- my-backend-service-arch.md              # Per-repo analysis (Claude)
|-- my-infra-arch.md
+-- diagrams/
    |-- architecture-overview.md            # All diagrams in one markdown file
    |-- diagram-01-graph.mmd               # Network architecture (source)
    |-- diagram-01-graph.png               # Network architecture (rendered)
    |-- diagram-02-sequence.mmd            # Sequence diagram (source)
    |-- diagram-02-sequence.png            # Sequence diagram (rendered)
    |-- diagram-03-flowchart.mmd           # Data flow diagram (source)
    +-- diagram-03-flowchart.png           # Data flow diagram (rendered)
```

**Static analysis mode** (`ENABLE_AI=false`):
```
outputs/
|-- my-infra-repo-arch.md                   # Per-repo analysis (static scanners)
|-- my-other-repo-arch.md
+-- diagrams/
    |-- architecture-overview.md            # All diagrams + narrative in one file
    |-- diagram-01-graph.mmd               # Cross-Repo Lifecycle
    |-- diagram-01-graph.png
    |-- diagram-02-graph.mmd               # Network/Architecture Overview
    |-- diagram-02-graph.png
    |-- diagram-03-graph.mmd               # Technology Stack
    |-- diagram-03-graph.png
    |-- diagram-04-graph.mmd               # Infrastructure Architecture
    |-- diagram-04-graph.png
    |-- diagram-05-flowchart.mmd           # Data Flow
    |-- diagram-05-flowchart.png
    |-- diagram-06-graph.mmd               # Module Structure (repo 1)
    |-- diagram-06-graph.png
    |-- diagram-07-graph.mmd               # Module Structure (repo 2)
    |-- diagram-07-graph.png
    |-- diagram-08-pie.mmd                 # Language Distribution
    |-- diagram-08-pie.png
    |-- diagram-09-sequence.mmd            # IaC Provisioning Sequence
    |-- diagram-09-sequence.png
    |-- diagram-10-sequence.mmd            # CF Integration Sequence
    |-- diagram-10-sequence.png
    |-- diagram-11-sequence.mmd            # EMR Runtime Sequence
    +-- diagram-11-sequence.png
```

### Viewing diagrams

```bash
# Open all PNGs (macOS)
open outputs/diagrams/*.png

# Or view the markdown in any Mermaid-compatible viewer:
# - VS Code with Mermaid extension
# - GitHub markdown preview
# - https://mermaid.live (paste mermaid blocks)
```

---

## CLI options

```bash
# Force re-analysis (ignore cache)
mise investigate-local force

# Override Claude model
mise investigate-local model claude-sonnet-4-5-20250929

# Override max tokens per analysis step
mise investigate-local max-tokens 8000

# Process repos in parallel (default: 8)
mise investigate-local chunk-size 4

# Custom output directory
mise investigate-local output-dir my-output

# Combine options
mise investigate-local force chunk-size 4 model claude-sonnet-4-5-20250929

# Dry run (show config without executing)
mise investigate-local dry-run

# Help
mise investigate-local h
```

---

## Troubleshooting

### "ANTHROPIC_API_KEY environment variable is not set"
Set your API key in `.env.local`. Get one at [console.anthropic.com](https://console.anthropic.com).

### "credit balance is too low"
Anthropic API credits are separate from a Claude Pro subscription. Top up at [console.anthropic.com/settings/billing](https://console.anthropic.com/settings/billing).

### "Repository URI must start with file://, http://, or https://"
Your `repos.json` has an invalid `uri` value. Use `file:///absolute/path` for local repos or `https://github.com/org/repo` for remote repos.

### Diagrams not generated
Check that `.env.local` has `CREATE_DIAGRAMS=true`. The worker must be restarted after changing env vars.

### PNGs not generated
1. Check `RENDER_MERMAID_PNGS=true` in `.env.local`
2. Check Docker is running: `colima status` or `docker info`
3. Check the mermaid image exists: `docker images repo-swarm-mermaid:local`
4. If Docker is unavailable, install mmdc locally as fallback: `npm install -g @mermaid-js/mermaid-cli`

### Worker crashes with "Cannot access X from inside a workflow"
Restart the worker (`Ctrl+C` in terminal 2, then `mise dev-worker`). This is a Temporal sandbox error -- the worker needs the latest code.

### Cached results from previous run
Use `force` flag to re-analyse: `mise investigate-local force`

---

## Stopping

- **Terminal 3** (client): exits automatically when analysis completes
- **Terminal 2** (worker): `Ctrl+C`
- **Terminal 1** (server): `Ctrl+C`
- **Kill everything**: `mise kill`

---

## Cost estimate

**Modes 5 and 6 (`ENABLE_AI=false`) are completely free** -- no API calls, no credits needed.

For AI modes (1-4), each repo analysis uses ~17 Claude API calls. Cross-repo diagrams add 3 more calls.

| Repos | Approximate calls | Estimated cost (claude-opus-4-5) |
|-------|-------------------|----------------------------------|
| 3     | ~54               | ~$5-10                           |
| 10    | ~173              | ~$15-30                          |
| 30    | ~513              | ~$40-80                          |

Use a cheaper model to reduce cost: `mise investigate-local model claude-sonnet-4-5-20250929`
