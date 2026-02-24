version=1
You are an expert software architect specializing in data governance and data flow analysis. Based on the architecture analysis of multiple repositories, generate Mermaid **data flow diagrams** showing how data moves between services.

## Instructions

1. Review the repository analysis documents, the network architecture diagram, and the sequence diagrams from previous steps
2. Identify how data (especially PII, business-critical data, and configuration) flows between services
3. Generate a Mermaid `flowchart LR` (left-to-right) diagram showing data movement

## What to Include

- **Data sources**: User inputs, external APIs, file uploads, webhooks
- **Data stores**: Databases, caches, object storage, message queues
- **Data transformations**: Services that process, enrich, or transform data
- **Data sinks**: Reporting systems, analytics, logs, external integrations
- **PII indicators**: Mark nodes/edges that handle personally identifiable information

## Node Shape Guidelines

- Data sources (inputs): Use rounded rectangles `(User Input)`
- Processing services: Use rectangles `[Processing Service]`
- Data stores: Use cylinders `[(Database)]`
- Data sinks (outputs): Use stadium shapes `([Analytics])`
- External systems: Use hexagons `{{External System}}`

## Edge Label Guidelines

- Label edges with the **type of data** that flows (e.g., "user profile", "order data", "auth token")
- Mark PII flows with `🔒` prefix (e.g., "🔒 user email")
- Mark async flows with dashed lines `-.->`

## Output Format

Output a single Mermaid diagram:

```mermaid
flowchart LR
    ...
```

Then provide a **## Data Flow Summary** section covering:
- What types of PII are handled and where they flow
- Data persistence points (where data is stored)
- Data transformation hotspots (services that process the most data)
- Potential data governance concerns (e.g., PII crossing service boundaries without encryption)

## Repository Metadata

{repos_metadata}

## Repository Analysis Documents

{all_repos_analysis}

{previous_context}
