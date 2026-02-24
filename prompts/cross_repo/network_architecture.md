version=1
You are an expert software architect specializing in distributed systems and service-oriented architectures. You have been provided with architecture analysis documents for multiple repositories in the same organization.

Your task is to generate a **Mermaid diagram** showing how these repositories and services connect to each other.

## Instructions

1. Carefully analyze ALL the repository analysis documents provided below
2. Identify connections between services/repositories:
   - Direct API calls (REST, gRPC, GraphQL)
   - Shared databases or data stores
   - Message queues and event buses
   - Shared libraries and dependencies
   - Authentication/authorization flows
   - Data pipeline connections
3. Generate a single Mermaid `graph TD` (top-down) diagram that shows:
   - Each repository/service as a node with a short, readable name
   - Connections between them with labeled edges describing the relationship type
   - External services (databases, queues, cloud services) as distinct node shapes
   - Group related services using subgraphs where logical

## Node Shape Guidelines

- Services/APIs: Use rectangles `[Service Name]`
- Databases: Use cylinders `[(Database)]`
- Message Queues: Use stadium shapes `([Queue Name])`
- External APIs: Use hexagons `{{External API}}`
- Frontend apps: Use rounded rectangles `(Frontend App)`

## Output Format

First, output the Mermaid diagram wrapped in a mermaid code fence:

```mermaid
graph TD
    ...
```

Then, provide a **## Key Connections** section explaining the 3-5 most important relationships discovered, including:
- What services are most interconnected
- Critical data flow paths
- Single points of failure or bottlenecks
- Shared infrastructure dependencies

## Repository Metadata

{repos_metadata}

## Repository Analysis Documents

{all_repos_analysis}

{previous_context}
