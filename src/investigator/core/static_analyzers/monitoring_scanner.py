"""
MonitoringScanner -- detects monitoring, logging, metrics, and observability tooling.

Covers section: monitoring
"""

import re
from pathlib import Path


# Terraform monitoring resource types
TF_MONITORING_RESOURCES = {
    "aws_cloudwatch_metric_alarm": "CloudWatch Alarms",
    "aws_cloudwatch_log_group": "CloudWatch Logs",
    "aws_cloudwatch_log_stream": "CloudWatch Logs",
    "aws_cloudwatch_dashboard": "CloudWatch Dashboards",
    "aws_cloudwatch_event_rule": "CloudWatch Events",
    "aws_cloudwatch_event_target": "CloudWatch Events",
    "aws_sns_topic": "SNS (Alerting)",
    "aws_sns_topic_subscription": "SNS (Alerting)",
    "aws_xray_sampling_rule": "X-Ray (Tracing)",
    "aws_xray_group": "X-Ray (Tracing)",
    # Azure
    "azurerm_monitor_metric_alert": "Azure Monitor",
    "azurerm_monitor_action_group": "Azure Monitor",
    "azurerm_application_insights": "Application Insights",
    "azurerm_log_analytics_workspace": "Log Analytics",
    # GCP
    "google_monitoring_alert_policy": "Google Cloud Monitoring",
    "google_monitoring_notification_channel": "Google Cloud Monitoring",
    "google_logging_metric": "Google Cloud Logging",
}

# Known monitoring config files
MONITORING_CONFIG_FILES = {
    "prometheus.yml": "Prometheus",
    "prometheus.yaml": "Prometheus",
    "alertmanager.yml": "Alertmanager",
    "alertmanager.yaml": "Alertmanager",
    "grafana.ini": "Grafana",
    "grafana.yaml": "Grafana",
    "datadog.yaml": "DataDog",
    "datadog.yml": "DataDog",
    "newrelic.yml": "New Relic",
    "newrelic.js": "New Relic",
    "elastic-apm-agent.properties": "Elastic APM",
    "sentry.properties": "Sentry",
    ".sentryclirc": "Sentry",
    "fluent.conf": "Fluentd",
    "fluentd.conf": "Fluentd",
    "fluent-bit.conf": "Fluent Bit",
    "filebeat.yml": "Filebeat",
    "filebeat.yaml": "Filebeat",
    "logstash.conf": "Logstash",
    "otel-collector-config.yaml": "OpenTelemetry",
    "otel-config.yaml": "OpenTelemetry",
    "jaeger-config.yaml": "Jaeger",
}

# Logging framework imports per language
LOGGING_IMPORTS = {
    "java": {
        "glob": "**/*.java",
        "patterns": {
            "org.slf4j": "SLF4J",
            "org.apache.logging.log4j": "Log4j2",
            "org.apache.log4j": "Log4j",
            "java.util.logging": "JUL",
            "ch.qos.logback": "Logback",
            "io.micrometer": "Micrometer (Metrics)",
            "io.opentelemetry": "OpenTelemetry",
            "io.prometheus": "Prometheus Client",
            "com.datadoghq": "DataDog",
            "com.newrelic": "New Relic",
            "io.sentry": "Sentry",
        },
    },
    "python": {
        "glob": "**/*.py",
        "patterns": {
            "import logging": "Python logging",
            "from logging": "Python logging",
            "import structlog": "structlog",
            "import sentry_sdk": "Sentry",
            "from sentry_sdk": "Sentry",
            "import prometheus_client": "Prometheus Client",
            "from prometheus_client": "Prometheus Client",
            "import opentelemetry": "OpenTelemetry",
            "from opentelemetry": "OpenTelemetry",
            "import datadog": "DataDog",
            "from datadog": "DataDog",
            "import newrelic": "New Relic",
            "import statsd": "StatsD",
            "from statsd": "StatsD",
        },
    },
    "go": {
        "glob": "**/*.go",
        "patterns": {
            '"log"': "Go stdlib log",
            '"go.uber.org/zap"': "Zap",
            '"github.com/sirupsen/logrus"': "Logrus",
            '"github.com/rs/zerolog"': "Zerolog",
            '"github.com/prometheus/client_golang"': "Prometheus Client",
            '"go.opentelemetry.io"': "OpenTelemetry",
            '"github.com/DataDog/datadog-go"': "DataDog",
            '"github.com/getsentry/sentry-go"': "Sentry",
        },
    },
    "javascript": {
        "glob": "**/*.{js,ts}",
        "patterns": {
            "require('winston')": "Winston",
            "from 'winston'": "Winston",
            "require('pino')": "Pino",
            "from 'pino'": "Pino",
            "require('bunyan')": "Bunyan",
            "from 'bunyan'": "Bunyan",
            "@sentry/": "Sentry",
            "require('dd-trace')": "DataDog",
            "from 'dd-trace'": "DataDog",
            "prom-client": "Prometheus Client",
            "@opentelemetry/": "OpenTelemetry",
        },
    },
}


class MonitoringScanner:
    """Scans a repository for monitoring, logging, and observability tooling."""

    SKIP_DIRS = {".terraform", "node_modules", ".venv", "venv", "vendor",
                 ".git", "__pycache__", "dist", "build", "target"}

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    def scan(self) -> dict:
        """Scan the repo for monitoring and observability tooling."""
        result = {
            "terraform_monitoring": [],
            "config_files": [],
            "logging_frameworks": [],
            "health_checks": [],
        }

        if not self.repo_path.exists():
            return result

        self._scan_terraform(result)
        self._scan_config_files(result)
        self._scan_logging_frameworks(result)
        self._scan_health_checks(result)

        return result

    def _should_skip(self, path: Path) -> bool:
        return any(d in path.parts for d in self.SKIP_DIRS)

    def _scan_terraform(self, result: dict):
        """Scan .tf files for monitoring resources."""
        for tf_file in self.repo_path.rglob("*.tf"):
            if self._should_skip(tf_file):
                continue
            try:
                content = tf_file.read_text(encoding="utf-8", errors="replace")
            except (OSError, IOError):
                continue

            rel_path = str(tf_file.relative_to(self.repo_path))

            for res_type, category in TF_MONITORING_RESOURCES.items():
                pattern = re.compile(rf'resource\s+"{res_type}"\s+"(\w+)"')
                for match in pattern.finditer(content):
                    result["terraform_monitoring"].append({
                        "type": res_type,
                        "name": match.group(1),
                        "category": category,
                        "file": rel_path,
                    })

    def _scan_config_files(self, result: dict):
        """Scan for known monitoring configuration files."""
        for filename, tool in MONITORING_CONFIG_FILES.items():
            for match in self.repo_path.rglob(filename):
                if self._should_skip(match):
                    continue
                rel_path = str(match.relative_to(self.repo_path))
                result["config_files"].append({
                    "tool": tool,
                    "file": rel_path,
                })

    def _scan_logging_frameworks(self, result: dict):
        """Scan source code for logging/metrics framework imports."""
        found_frameworks = set()

        for lang, config in LOGGING_IMPORTS.items():
            glob_pattern = config["glob"]

            if "{" in glob_pattern:
                base, ext_part = glob_pattern.rsplit(".", 1)
                exts = ext_part.strip("{}").split(",")
                files = []
                for ext in exts:
                    files.extend(self.repo_path.rglob(f"{base}.{ext}"))
            else:
                files = list(self.repo_path.rglob(glob_pattern))

            files = [f for f in files if not self._should_skip(f)]

            for filepath in files:
                try:
                    content = filepath.read_text(encoding="utf-8", errors="replace")
                except (OSError, IOError):
                    continue

                rel_path = str(filepath.relative_to(self.repo_path))

                for import_str, framework in config["patterns"].items():
                    if import_str in content:
                        key = (framework, lang)
                        if key not in found_frameworks:
                            found_frameworks.add(key)
                            result["logging_frameworks"].append({
                                "framework": framework,
                                "language": lang,
                                "file": rel_path,
                            })

    def _scan_health_checks(self, result: dict):
        """Scan for health check endpoints and Dockerfile HEALTHCHECK."""
        # Dockerfile HEALTHCHECK
        for dockerfile in self.repo_path.rglob("Dockerfile*"):
            if self._should_skip(dockerfile):
                continue
            try:
                content = dockerfile.read_text(encoding="utf-8", errors="replace")
            except (OSError, IOError):
                continue

            if "HEALTHCHECK" in content:
                rel_path = str(dockerfile.relative_to(self.repo_path))
                result["health_checks"].append({
                    "type": "Docker HEALTHCHECK",
                    "file": rel_path,
                })

        # Health endpoint patterns in code
        health_patterns = [
            (re.compile(r'["\']/?health["\']'), "Health endpoint"),
            (re.compile(r'["\']/?healthz["\']'), "Kubernetes health probe"),
            (re.compile(r'["\']/?ready["\']'), "Readiness probe"),
            (re.compile(r'["\']/?readyz["\']'), "Kubernetes readiness probe"),
            (re.compile(r'["\']/?livez?["\']'), "Liveness probe"),
            (re.compile(r'["\']/?actuator/health["\']'), "Spring Actuator"),
        ]

        for ext_pattern in ["**/*.java", "**/*.go", "**/*.py", "**/*.js", "**/*.ts"]:
            for f in self.repo_path.rglob(ext_pattern):
                if self._should_skip(f):
                    continue
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                except (OSError, IOError):
                    continue

                rel_path = str(f.relative_to(self.repo_path))

                for pattern, check_type in health_patterns:
                    if pattern.search(content):
                        result["health_checks"].append({
                            "type": check_type,
                            "file": rel_path,
                        })
                        break  # One match per file

    def format_as_markdown(self, data: dict) -> str:
        """Format monitoring data as markdown."""
        tf_mon = data.get("terraform_monitoring", [])
        configs = data.get("config_files", [])
        frameworks = data.get("logging_frameworks", [])
        health = data.get("health_checks", [])

        all_items = tf_mon + configs + frameworks + health
        if not all_items:
            return ("*No monitoring, logging, or observability tooling detected.*\n\n"
                    "---\n*Generated by static analysis (ENABLE_AI=false)*")

        lines = []

        if tf_mon:
            lines.append("**Monitoring Resources (Terraform):**\n")
            lines.append("| Category | Resource Type | Name | File |")
            lines.append("|----------|--------------|------|------|")
            for m in sorted(tf_mon, key=lambda x: x["category"]):
                lines.append(f"| {m['category']} | `{m['type']}` | {m['name']} | {m['file']} |")
            lines.append("")

        if configs:
            lines.append("**Monitoring Configuration Files:**\n")
            lines.append("| Tool | File |")
            lines.append("|------|------|")
            for c in sorted(configs, key=lambda x: x["tool"]):
                lines.append(f"| {c['tool']} | `{c['file']}` |")
            lines.append("")

        if frameworks:
            lines.append("**Logging & Metrics Frameworks:**\n")
            lines.append("| Framework | Language | Example File |")
            lines.append("|-----------|----------|-------------|")
            for f in sorted(frameworks, key=lambda x: x["framework"]):
                lines.append(f"| {f['framework']} | {f['language']} | `{f['file']}` |")
            lines.append("")

        if health:
            lines.append("**Health Checks:**\n")
            lines.append("| Type | File |")
            lines.append("|------|------|")
            for h in sorted(health, key=lambda x: x["type"]):
                lines.append(f"| {h['type']} | `{h['file']}` |")

        lines.append("\n---")
        lines.append("*Generated by static analysis (ENABLE_AI=false)*")
        return "\n".join(lines)
