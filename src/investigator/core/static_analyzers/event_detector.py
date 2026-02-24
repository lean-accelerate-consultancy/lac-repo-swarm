"""
EventDetector -- detects event/messaging systems, brokers, topics, and
pub/sub patterns from code, configuration, and infrastructure files.

Covers section: events
"""

import re
from pathlib import Path


# Code-level event framework patterns per language
EVENT_CODE_PATTERNS = {
    "Kafka": {
        "glob": ["**/*.java", "**/*.py", "**/*.go", "**/*.js", "**/*.ts"],
        "patterns": [
            re.compile(r'@KafkaListener', re.IGNORECASE),
            re.compile(r'@KafkaHandler', re.IGNORECASE),
            re.compile(r'KafkaTemplate', re.IGNORECASE),
            re.compile(r'KafkaProducer|KafkaConsumer'),
            re.compile(r'kafka\.(?:Producer|Consumer|AdminClient)'),
            re.compile(r'confluent_kafka'),
            re.compile(r'from\s+kafka\s+import'),
            re.compile(r'import\s+kafka'),
            re.compile(r'sarama\.'),  # Go Kafka client
            re.compile(r'kafkajs'),
            re.compile(r'spring\.kafka'),
        ],
    },
    "RabbitMQ": {
        "glob": ["**/*.java", "**/*.py", "**/*.go", "**/*.js", "**/*.ts"],
        "patterns": [
            re.compile(r'@RabbitListener'),
            re.compile(r'@RabbitHandler'),
            re.compile(r'RabbitTemplate'),
            re.compile(r'amqp://'),
            re.compile(r'spring\.rabbitmq'),
            re.compile(r'pika\.'),
            re.compile(r'amqplib|amqp\.connect'),
            re.compile(r'streadway/amqp|rabbitmq/amqp091-go'),
        ],
    },
    "AWS SQS": {
        "glob": ["**/*.java", "**/*.py", "**/*.go", "**/*.js", "**/*.ts"],
        "patterns": [
            re.compile(r'sqs\.(?:send_message|receive_message|create_queue)', re.IGNORECASE),
            re.compile(r'SqsClient|AmazonSQS'),
            re.compile(r"boto3\.client\s*\(\s*['\"]sqs['\"]"),
            re.compile(r'@SqsListener'),
            re.compile(r'aws-sdk.*SQS'),
            re.compile(r'sqs\.SendMessage|sqs\.ReceiveMessage'),
        ],
    },
    "AWS SNS": {
        "glob": ["**/*.java", "**/*.py", "**/*.go", "**/*.js", "**/*.ts"],
        "patterns": [
            re.compile(r'sns\.(?:publish|subscribe|create_topic)', re.IGNORECASE),
            re.compile(r'SnsClient|AmazonSNS'),
            re.compile(r"boto3\.client\s*\(\s*['\"]sns['\"]"),
            re.compile(r'aws-sdk.*SNS'),
        ],
    },
    "AWS EventBridge": {
        "glob": ["**/*.java", "**/*.py", "**/*.go", "**/*.js", "**/*.ts"],
        "patterns": [
            re.compile(r'EventBridgeClient|EventBridge'),
            re.compile(r'put_events|PutEvents'),
            re.compile(r"boto3\.client\s*\(\s*['\"]events['\"]"),
        ],
    },
    "Redis Pub/Sub": {
        "glob": ["**/*.java", "**/*.py", "**/*.go", "**/*.js", "**/*.ts"],
        "patterns": [
            re.compile(r'\.publish\s*\(.*\).*redis', re.IGNORECASE),
            re.compile(r'\.subscribe\s*\(.*\).*redis', re.IGNORECASE),
            re.compile(r'RedisMessageListenerContainer'),
            re.compile(r'redis\.(?:pubsub|publish|subscribe)'),
        ],
    },
    "NATS": {
        "glob": ["**/*.go", "**/*.js", "**/*.ts", "**/*.py"],
        "patterns": [
            re.compile(r'nats\.Connect'),
            re.compile(r'nats-io'),
            re.compile(r'nats\.connect'),
            re.compile(r'from\s+nats\s+import'),
        ],
    },
    "Google Pub/Sub": {
        "glob": ["**/*.java", "**/*.py", "**/*.go", "**/*.js", "**/*.ts"],
        "patterns": [
            re.compile(r'PublisherClient|SubscriberClient'),
            re.compile(r'google\.cloud\.pubsub'),
            re.compile(r'@google-cloud/pubsub'),
        ],
    },
}

# Config-file event patterns (application.yml, .properties, etc.)
CONFIG_EVENT_PATTERNS = {
    "Kafka": [
        re.compile(r'(?:spring\.kafka|bootstrap\.servers|kafka\.)', re.IGNORECASE),
        re.compile(r'KAFKA_BOOTSTRAP_SERVERS|KAFKA_BROKER', re.IGNORECASE),
        re.compile(r'^\s*kafka\s*:', re.MULTILINE | re.IGNORECASE),
        re.compile(r'bootstrap-servers\s*:', re.IGNORECASE),
    ],
    "RabbitMQ": [
        re.compile(r'(?:spring\.rabbitmq|amqp://)', re.IGNORECASE),
        re.compile(r'RABBITMQ_HOST|AMQP_URL', re.IGNORECASE),
    ],
    "AWS SQS": [
        re.compile(r'SQS_QUEUE_URL|SQS_ENDPOINT', re.IGNORECASE),
    ],
    "AWS SNS": [
        re.compile(r'SNS_TOPIC_ARN|SNS_ENDPOINT', re.IGNORECASE),
    ],
    "Redis": [
        re.compile(r'REDIS_URL|REDIS_HOST|spring\.redis', re.IGNORECASE),
    ],
}

# Topic/queue name extraction patterns
TOPIC_PATTERNS = [
    # Java annotations
    (re.compile(r'@KafkaListener\s*\([^)]*topics?\s*=\s*["\'{]([^"\'}\)]+)["\'}]'),
     "Kafka topic (consumer)"),
    (re.compile(r'@RabbitListener\s*\([^)]*queues?\s*=\s*["\'{]([^"\'}\)]+)["\'}]'),
     "RabbitMQ queue (consumer)"),
    # Config properties
    (re.compile(r'(?:topic|queue)[._-]?name\s*[=:]\s*["\']?([a-zA-Z0-9._\-]+)', re.IGNORECASE),
     "Topic/Queue name"),
    # Spring config
    (re.compile(r'spring\.kafka\.consumer\.group-id\s*[=:]\s*(\S+)'),
     "Kafka consumer group"),
]

# Schema file patterns for event payloads
SCHEMA_FILE_PATTERNS = {
    "**/*.avsc": "Avro",
    "**/*.proto": "Protobuf",
    "**/asyncapi.yml": "AsyncAPI",
    "**/asyncapi.yaml": "AsyncAPI",
    "**/asyncapi.json": "AsyncAPI",
}


class EventDetector:
    """Scans a repository for event/messaging system usage and configuration."""

    SKIP_DIRS = {".terraform", "node_modules", ".venv", "venv", "vendor",
                 ".git", "__pycache__", "dist", "build", "target"}

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    def scan(self) -> dict:
        """Scan the repo for event/messaging patterns."""
        result = {
            "brokers": [],
            "topics": [],
            "config_refs": [],
            "schemas": [],
        }

        if not self.repo_path.exists():
            return result

        self._scan_code_patterns(result)
        self._scan_config_patterns(result)
        self._scan_topics(result)
        self._scan_schemas(result)

        return result

    def _should_skip(self, path: Path) -> bool:
        return any(d in path.parts for d in self.SKIP_DIRS)

    def _scan_code_patterns(self, result: dict):
        """Scan source code for event framework usage."""
        found_brokers = set()

        for broker, config in EVENT_CODE_PATTERNS.items():
            if broker in found_brokers:
                continue

            for glob_pattern in config["glob"]:
                if broker in found_brokers:
                    break

                for f in self.repo_path.rglob(glob_pattern):
                    if self._should_skip(f):
                        continue
                    if f.stat().st_size > 500_000:
                        continue

                    try:
                        content = f.read_text(encoding="utf-8", errors="replace")
                    except (OSError, IOError):
                        continue

                    for pattern in config["patterns"]:
                        if pattern.search(content):
                            found_brokers.add(broker)
                            rel_path = str(f.relative_to(self.repo_path))
                            result["brokers"].append({
                                "broker": broker,
                                "source": "code",
                                "file": rel_path,
                            })
                            break

                    if broker in found_brokers:
                        break

    def _scan_config_patterns(self, result: dict):
        """Scan config files for event broker references."""
        config_patterns = ["**/*.yml", "**/*.yaml", "**/*.properties",
                          "**/*.json", "**/*.toml", "**/*.env.example"]
        found_configs = set()

        for glob_pattern in config_patterns:
            for f in self.repo_path.rglob(glob_pattern):
                if self._should_skip(f):
                    continue
                if f.stat().st_size > 200_000:
                    continue

                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                except (OSError, IOError):
                    continue

                rel_path = str(f.relative_to(self.repo_path))

                for broker, patterns in CONFIG_EVENT_PATTERNS.items():
                    config_key = (broker, rel_path)
                    if config_key in found_configs:
                        continue

                    for pattern in patterns:
                        if pattern.search(content):
                            found_configs.add(config_key)
                            result["config_refs"].append({
                                "broker": broker,
                                "file": rel_path,
                            })
                            break

    def _scan_topics(self, result: dict):
        """Extract topic/queue names from annotations and config."""
        found_topics = set()

        for ext in ["**/*.java", "**/*.py", "**/*.go", "**/*.js", "**/*.ts",
                    "**/*.yml", "**/*.yaml", "**/*.properties"]:
            for f in self.repo_path.rglob(ext):
                if self._should_skip(f):
                    continue
                if f.stat().st_size > 500_000:
                    continue

                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                except (OSError, IOError):
                    continue

                rel_path = str(f.relative_to(self.repo_path))

                for pattern, desc in TOPIC_PATTERNS:
                    for match in pattern.finditer(content):
                        topic_name = match.group(1).strip()
                        if topic_name and topic_name not in found_topics:
                            found_topics.add(topic_name)
                            result["topics"].append({
                                "name": topic_name,
                                "type": desc,
                                "file": rel_path,
                            })

    def _scan_schemas(self, result: dict):
        """Scan for event schema files (Avro, Protobuf, AsyncAPI)."""
        for glob_pattern, schema_type in SCHEMA_FILE_PATTERNS.items():
            for f in self.repo_path.rglob(glob_pattern):
                if self._should_skip(f):
                    continue
                rel_path = str(f.relative_to(self.repo_path))
                result["schemas"].append({
                    "type": schema_type,
                    "file": rel_path,
                })

    def format_as_markdown(self, data: dict) -> str:
        """Format event detection results as markdown."""
        brokers = data.get("brokers", [])
        topics = data.get("topics", [])
        config_refs = data.get("config_refs", [])
        schemas = data.get("schemas", [])

        if not brokers and not topics and not config_refs and not schemas:
            return ("*No event/messaging systems, brokers, or pub/sub patterns detected.*\n\n"
                    "---\n*Generated by static analysis (ENABLE_AI=false)*")

        lines = []

        # Combine brokers from code and config into a unified view
        all_brokers = set()
        for b in brokers:
            all_brokers.add(b["broker"])
        for c in config_refs:
            all_brokers.add(c["broker"])

        if all_brokers:
            lines.append("**Event/Messaging Systems Detected:**\n")
            for broker in sorted(all_brokers):
                code_files = [b["file"] for b in brokers if b["broker"] == broker]
                cfg_files = [c["file"] for c in config_refs if c["broker"] == broker]
                lines.append(f"- **{broker}**")
                if code_files:
                    lines.append(f"  - Code: `{code_files[0]}`")
                if cfg_files:
                    lines.append(f"  - Config: `{cfg_files[0]}`")
            lines.append("")

        if brokers:
            lines.append("**Broker Usage in Code:**\n")
            lines.append("| Broker | Source | File |")
            lines.append("|--------|--------|------|")
            for b in sorted(brokers, key=lambda x: x["broker"]):
                lines.append(f"| {b['broker']} | {b['source']} | `{b['file']}` |")
            lines.append("")

        if topics:
            lines.append("**Topics/Queues:**\n")
            lines.append("| Name | Type | File |")
            lines.append("|------|------|------|")
            for t in sorted(topics, key=lambda x: x["name"]):
                lines.append(f"| `{t['name']}` | {t['type']} | `{t['file']}` |")
            lines.append("")

        if schemas:
            lines.append("**Event Schema Files:**\n")
            lines.append("| Schema Type | File |")
            lines.append("|------------|------|")
            for s in sorted(schemas, key=lambda x: x["type"]):
                lines.append(f"| {s['type']} | `{s['file']}` |")
            lines.append("")

        if config_refs:
            lines.append("**Configuration References:**\n")
            lines.append("| Broker | Config File |")
            lines.append("|--------|------------|")
            for c in sorted(config_refs, key=lambda x: x["broker"]):
                lines.append(f"| {c['broker']} | `{c['file']}` |")

        lines.append("\n---")
        lines.append("*Generated by static analysis (ENABLE_AI=false)*")
        return "\n".join(lines)
