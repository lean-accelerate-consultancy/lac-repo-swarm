"""
DatabaseScanner -- detects database usage from Terraform resources, config files,
connection strings, and Docker Compose service definitions.

Covers section: DBs
"""

import re
from pathlib import Path


# Terraform database resource types and their engines
TF_DB_RESOURCES = {
    "aws_rds_cluster": "RDS",
    "aws_rds_cluster_instance": "RDS",
    "aws_db_instance": "RDS",
    "aws_db_subnet_group": "RDS",
    "aws_db_parameter_group": "RDS",
    "aws_dynamodb_table": "DynamoDB",
    "aws_dynamodb_global_table": "DynamoDB",
    "aws_elasticache_cluster": "ElastiCache",
    "aws_elasticache_replication_group": "ElastiCache",
    "aws_elasticache_subnet_group": "ElastiCache",
    "aws_redshift_cluster": "Redshift",
    "aws_redshift_subnet_group": "Redshift",
    "aws_neptune_cluster": "Neptune",
    "aws_docdb_cluster": "DocumentDB",
    "aws_keyspaces_table": "Keyspaces",
    "aws_elasticsearch_domain": "Elasticsearch",
    "aws_opensearch_domain": "OpenSearch",
    "aws_memorydb_cluster": "MemoryDB",
    "aws_timestream_database": "Timestream",
    "aws_qldb_ledger": "QLDB",
    # Azure
    "azurerm_cosmosdb_account": "CosmosDB",
    "azurerm_mssql_server": "SQL Server",
    "azurerm_mysql_server": "MySQL",
    "azurerm_postgresql_server": "PostgreSQL",
    "azurerm_redis_cache": "Redis",
    # GCP
    "google_sql_database_instance": "Cloud SQL",
    "google_spanner_instance": "Spanner",
    "google_bigtable_instance": "Bigtable",
    "google_redis_instance": "Memorystore",
}

# Docker Compose database image patterns
DOCKER_DB_IMAGES = {
    "postgres": "PostgreSQL",
    "mysql": "MySQL",
    "mariadb": "MariaDB",
    "mongo": "MongoDB",
    "redis": "Redis",
    "memcached": "Memcached",
    "cassandra": "Cassandra",
    "elasticsearch": "Elasticsearch",
    "opensearch": "OpenSearch",
    "mssql": "SQL Server",
    "oracle": "Oracle",
    "cockroachdb": "CockroachDB",
    "neo4j": "Neo4j",
    "influxdb": "InfluxDB",
    "dynamodb-local": "DynamoDB (local)",
    "localstack": "LocalStack (AWS services)",
    "minio": "MinIO (S3-compatible)",
}

# Connection string patterns
CONN_STRING_PATTERNS = [
    (re.compile(r'jdbc:postgresql://[^\s"\']+'), "PostgreSQL"),
    (re.compile(r'jdbc:mysql://[^\s"\']+'), "MySQL"),
    (re.compile(r'jdbc:oracle://[^\s"\']+'), "Oracle"),
    (re.compile(r'jdbc:sqlserver://[^\s"\']+'), "SQL Server"),
    (re.compile(r'jdbc:h2:[^\s"\']+'), "H2"),
    (re.compile(r'mongodb://[^\s"\']+'), "MongoDB"),
    (re.compile(r'mongodb\+srv://[^\s"\']+'), "MongoDB"),
    (re.compile(r'redis://[^\s"\']+'), "Redis"),
    (re.compile(r'amqp://[^\s"\']+'), "RabbitMQ"),
]


class DatabaseScanner:
    """Scans a repository for database usage and configuration."""

    SKIP_DIRS = {".terraform", "node_modules", ".venv", "venv", "vendor",
                 ".git", "__pycache__", "dist", "build"}

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    def scan(self) -> dict:
        """Scan the repo for database references."""
        result = {
            "terraform_dbs": [],
            "docker_dbs": [],
            "connection_strings": [],
            "config_dbs": [],
        }

        if not self.repo_path.exists():
            return result

        self._scan_terraform(result)
        self._scan_docker_compose(result)
        self._scan_connection_strings(result)
        self._scan_config_files(result)

        return result

    def _should_skip(self, path: Path) -> bool:
        return any(d in path.parts for d in self.SKIP_DIRS)

    def _scan_terraform(self, result: dict):
        """Scan .tf files for database resources."""
        for tf_file in self.repo_path.rglob("*.tf"):
            if self._should_skip(tf_file):
                continue
            try:
                content = tf_file.read_text(encoding="utf-8", errors="replace")
            except (OSError, IOError):
                continue

            rel_path = str(tf_file.relative_to(self.repo_path))

            for res_type, engine in TF_DB_RESOURCES.items():
                pattern = re.compile(rf'resource\s+"{res_type}"\s+"(\w+)"')
                for match in pattern.finditer(content):
                    # Try to extract engine from block
                    detected_engine = self._extract_tf_engine(content, match.start()) or engine
                    result["terraform_dbs"].append({
                        "type": res_type,
                        "name": match.group(1),
                        "engine": detected_engine,
                        "file": rel_path,
                    })

    def _extract_tf_engine(self, content: str, block_start: int) -> str:
        """Try to extract the engine attribute from a Terraform resource block."""
        # Look in the next ~500 chars for engine attribute
        block_slice = content[block_start:block_start + 500]
        engine_match = re.search(r'engine\s*=\s*"([^"]*)"', block_slice)
        if engine_match:
            return engine_match.group(1)
        return ""

    def _scan_docker_compose(self, result: dict):
        """Scan docker-compose files for database services."""
        compose_files = (
            list(self.repo_path.rglob("docker-compose*.yml")) +
            list(self.repo_path.rglob("docker-compose*.yaml")) +
            list(self.repo_path.rglob("compose.yml")) +
            list(self.repo_path.rglob("compose.yaml"))
        )

        for compose_file in compose_files:
            if self._should_skip(compose_file):
                continue
            try:
                content = compose_file.read_text(encoding="utf-8", errors="replace")
            except (OSError, IOError):
                continue

            rel_path = str(compose_file.relative_to(self.repo_path))

            for image_key, db_type in DOCKER_DB_IMAGES.items():
                if re.search(rf'image:\s*["\']?{image_key}', content):
                    result["docker_dbs"].append({
                        "type": db_type,
                        "source": "docker-compose",
                        "file": rel_path,
                    })

    def _scan_connection_strings(self, result: dict):
        """Scan config files for database connection strings."""
        config_patterns = [
            "**/*.properties", "**/*.yml", "**/*.yaml", "**/*.json",
            "**/*.env", "**/*.env.*", "**/*.conf", "**/*.cfg", "**/*.ini",
            "**/*.toml",
        ]

        for glob_pattern in config_patterns:
            for f in self.repo_path.rglob(glob_pattern):
                if self._should_skip(f):
                    continue
                if f.stat().st_size > 100_000:  # Skip large files
                    continue
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                except (OSError, IOError):
                    continue

                rel_path = str(f.relative_to(self.repo_path))

                for pattern, db_type in CONN_STRING_PATTERNS:
                    if pattern.search(content):
                        result["connection_strings"].append({
                            "type": db_type,
                            "file": rel_path,
                        })
                        break  # One match per file is enough

    def _scan_config_files(self, result: dict):
        """Scan Spring/application config for datasource settings."""
        for pattern in ["**/application.yml", "**/application.yaml",
                        "**/application.properties", "**/application-*.yml",
                        "**/application-*.yaml", "**/application-*.properties"]:
            for f in self.repo_path.rglob(pattern):
                if self._should_skip(f):
                    continue
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                except (OSError, IOError):
                    continue

                rel_path = str(f.relative_to(self.repo_path))

                # Spring datasource
                if "spring.datasource" in content or "spring.data" in content:
                    db_type = "Unknown"
                    if "postgresql" in content.lower():
                        db_type = "PostgreSQL"
                    elif "mysql" in content.lower():
                        db_type = "MySQL"
                    elif "h2" in content.lower():
                        db_type = "H2"
                    elif "oracle" in content.lower():
                        db_type = "Oracle"
                    result["config_dbs"].append({
                        "type": db_type,
                        "source": "Spring datasource config",
                        "file": rel_path,
                    })

    def format_as_markdown(self, data: dict) -> str:
        """Format database data as markdown."""
        tf_dbs = data.get("terraform_dbs", [])
        docker_dbs = data.get("docker_dbs", [])
        conn_strings = data.get("connection_strings", [])
        config_dbs = data.get("config_dbs", [])

        all_items = tf_dbs + docker_dbs + conn_strings + config_dbs
        if not all_items:
            return ("*No database resources, connection strings, or data store configurations detected.*\n\n"
                    "---\n*Generated by static analysis (ENABLE_AI=false)*")

        lines = []

        if tf_dbs:
            lines.append("**Database Resources (Terraform):**\n")
            lines.append("| Type | Name | Engine | File |")
            lines.append("|------|------|--------|------|")
            for db in sorted(tf_dbs, key=lambda x: x["type"]):
                engine = db["engine"] or "-"
                lines.append(f"| `{db['type']}` | {db['name']} | {engine} | {db['file']} |")
            lines.append("")

        if docker_dbs:
            lines.append("**Database Services (Docker Compose):**\n")
            lines.append("| Database | File |")
            lines.append("|----------|------|")
            for db in sorted(docker_dbs, key=lambda x: x["type"]):
                lines.append(f"| {db['type']} | `{db['file']}` |")
            lines.append("")

        if conn_strings:
            lines.append("**Connection Strings Detected:**\n")
            lines.append("| Database Type | Config File |")
            lines.append("|--------------|-------------|")
            for cs in sorted(conn_strings, key=lambda x: x["type"]):
                lines.append(f"| {cs['type']} | `{cs['file']}` |")
            lines.append("")

        if config_dbs:
            lines.append("**Application Config Database References:**\n")
            lines.append("| Database Type | Source | File |")
            lines.append("|--------------|--------|------|")
            for db in sorted(config_dbs, key=lambda x: x["type"]):
                lines.append(f"| {db['type']} | {db['source']} | `{db['file']}` |")

        lines.append("\n---")
        lines.append("*Generated by static analysis (ENABLE_AI=false)*")
        return "\n".join(lines)
