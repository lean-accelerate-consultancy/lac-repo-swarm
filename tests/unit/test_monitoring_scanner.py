"""
Unit tests for MonitoringScanner -- monitoring, logging, metrics, and observability detection.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from investigator.core.static_analyzers.monitoring_scanner import MonitoringScanner


class TestMonitoringScannerTerraform(unittest.TestCase):
    """Tests for Terraform monitoring resource detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_cloudwatch_alarm_detected(self):
        """CloudWatch metric alarm resources are detected."""
        self._write_file("monitoring.tf", '''\
resource "aws_cloudwatch_metric_alarm" "cpu_high" {
  alarm_name = "cpu-high"
}
''')
        scanner = MonitoringScanner(self.tmpdir)
        data = scanner.scan()
        tf_mon = data["terraform_monitoring"]
        self.assertEqual(len(tf_mon), 1)
        self.assertEqual(tf_mon[0]["type"], "aws_cloudwatch_metric_alarm")
        self.assertEqual(tf_mon[0]["name"], "cpu_high")
        self.assertEqual(tf_mon[0]["category"], "CloudWatch Alarms")

    def test_sns_topic_detected(self):
        """SNS topic resources are detected."""
        self._write_file("alerts.tf", '''\
resource "aws_sns_topic" "alerts" {
  name = "alerts"
}
''')
        scanner = MonitoringScanner(self.tmpdir)
        data = scanner.scan()
        tf_mon = data["terraform_monitoring"]
        self.assertEqual(len(tf_mon), 1)
        self.assertEqual(tf_mon[0]["category"], "SNS (Alerting)")

    def test_cloudwatch_log_group_detected(self):
        """CloudWatch log group resources are detected."""
        self._write_file("logs.tf", '''\
resource "aws_cloudwatch_log_group" "app" {
  name = "/aws/ecs/app"
}
''')
        scanner = MonitoringScanner(self.tmpdir)
        data = scanner.scan()
        self.assertEqual(len(data["terraform_monitoring"]), 1)
        self.assertEqual(data["terraform_monitoring"][0]["category"], "CloudWatch Logs")

    def test_multiple_monitoring_resources(self):
        """Multiple monitoring resources in one file are all detected."""
        self._write_file("monitoring.tf", '''\
resource "aws_cloudwatch_metric_alarm" "cpu" {
  alarm_name = "cpu"
}
resource "aws_cloudwatch_log_group" "logs" {
  name = "app-logs"
}
resource "aws_sns_topic" "notify" {
  name = "notify"
}
''')
        scanner = MonitoringScanner(self.tmpdir)
        data = scanner.scan()
        self.assertEqual(len(data["terraform_monitoring"]), 3)


class TestMonitoringScannerConfigFiles(unittest.TestCase):
    """Tests for monitoring configuration file detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content="# config"):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_prometheus_yml_detected(self):
        """prometheus.yml is detected."""
        self._write_file("prometheus.yml")
        scanner = MonitoringScanner(self.tmpdir)
        data = scanner.scan()
        tools = {c["tool"] for c in data["config_files"]}
        self.assertIn("Prometheus", tools)

    def test_grafana_ini_detected(self):
        """grafana.ini is detected."""
        self._write_file("grafana.ini")
        scanner = MonitoringScanner(self.tmpdir)
        data = scanner.scan()
        tools = {c["tool"] for c in data["config_files"]}
        self.assertIn("Grafana", tools)

    def test_datadog_yaml_detected(self):
        """datadog.yaml is detected."""
        self._write_file("datadog.yaml")
        scanner = MonitoringScanner(self.tmpdir)
        data = scanner.scan()
        tools = {c["tool"] for c in data["config_files"]}
        self.assertIn("DataDog", tools)

    def test_sentry_properties_detected(self):
        """sentry.properties is detected."""
        self._write_file("sentry.properties")
        scanner = MonitoringScanner(self.tmpdir)
        data = scanner.scan()
        tools = {c["tool"] for c in data["config_files"]}
        self.assertIn("Sentry", tools)

    def test_filebeat_yml_detected(self):
        """filebeat.yml is detected."""
        self._write_file("filebeat.yml")
        scanner = MonitoringScanner(self.tmpdir)
        data = scanner.scan()
        tools = {c["tool"] for c in data["config_files"]}
        self.assertIn("Filebeat", tools)

    def test_otel_config_detected(self):
        """otel-collector-config.yaml is detected."""
        self._write_file("otel-collector-config.yaml")
        scanner = MonitoringScanner(self.tmpdir)
        data = scanner.scan()
        tools = {c["tool"] for c in data["config_files"]}
        self.assertIn("OpenTelemetry", tools)


class TestMonitoringScannerLoggingFrameworks(unittest.TestCase):
    """Tests for logging framework import detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_python_logging_detected(self):
        """Python stdlib logging import is detected."""
        self._write_file("app.py", """\
import logging

logger = logging.getLogger(__name__)
logger.info("Starting app")
""")
        scanner = MonitoringScanner(self.tmpdir)
        data = scanner.scan()
        frameworks = {f["framework"] for f in data["logging_frameworks"]}
        self.assertIn("Python logging", frameworks)

    def test_python_sentry_detected(self):
        """Python sentry_sdk import is detected."""
        self._write_file("init.py", """\
import sentry_sdk
sentry_sdk.init(dsn="https://...")
""")
        scanner = MonitoringScanner(self.tmpdir)
        data = scanner.scan()
        frameworks = {f["framework"] for f in data["logging_frameworks"]}
        self.assertIn("Sentry", frameworks)

    def test_java_slf4j_detected(self):
        """Java SLF4J import is detected."""
        self._write_file("App.java", """\
package com.example;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class App {
    private static final Logger log = LoggerFactory.getLogger(App.class);
}
""")
        scanner = MonitoringScanner(self.tmpdir)
        data = scanner.scan()
        frameworks = {f["framework"] for f in data["logging_frameworks"]}
        self.assertIn("SLF4J", frameworks)

    def test_go_zap_detected(self):
        """Go Zap logger import is detected."""
        self._write_file("main.go", """\
package main

import "go.uber.org/zap"

func main() {
    logger, _ := zap.NewProduction()
}
""")
        scanner = MonitoringScanner(self.tmpdir)
        data = scanner.scan()
        frameworks = {f["framework"] for f in data["logging_frameworks"]}
        self.assertIn("Zap", frameworks)

    def test_js_winston_detected(self):
        """JavaScript Winston logger import is detected."""
        self._write_file("logger.js", """\
const winston = require('winston');
const logger = winston.createLogger();
""")
        scanner = MonitoringScanner(self.tmpdir)
        data = scanner.scan()
        frameworks = {f["framework"] for f in data["logging_frameworks"]}
        self.assertIn("Winston", frameworks)

    def test_deduplication(self):
        """Same framework is reported only once per language."""
        self._write_file("a.py", "import logging\nlogging.info('a')")
        self._write_file("b.py", "import logging\nlogging.info('b')")
        scanner = MonitoringScanner(self.tmpdir)
        data = scanner.scan()
        python_logging = [f for f in data["logging_frameworks"]
                          if f["framework"] == "Python logging" and f["language"] == "python"]
        self.assertEqual(len(python_logging), 1)


class TestMonitoringScannerHealthChecks(unittest.TestCase):
    """Tests for health check detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_dockerfile_healthcheck(self):
        """HEALTHCHECK in Dockerfile is detected."""
        self._write_file("Dockerfile", """\
FROM python:3.12
COPY . .
HEALTHCHECK --interval=30s CMD curl -f http://localhost:8080/health || exit 1
""")
        scanner = MonitoringScanner(self.tmpdir)
        data = scanner.scan()
        health = data["health_checks"]
        self.assertTrue(len(health) >= 1)
        types = {h["type"] for h in health}
        self.assertIn("Docker HEALTHCHECK", types)

    def test_health_endpoint_in_go(self):
        """Health endpoint pattern in Go code is detected."""
        self._write_file("main.go", """\
package main

func main() {
    http.HandleFunc("/health", healthHandler)
}
""")
        scanner = MonitoringScanner(self.tmpdir)
        data = scanner.scan()
        types = {h["type"] for h in data["health_checks"]}
        self.assertIn("Health endpoint", types)

    def test_kubernetes_readiness_probe(self):
        """Kubernetes readiness probe endpoint is detected."""
        self._write_file("server.py", """\
@app.get("/readyz")
def readiness():
    return {"status": "ok"}
""")
        scanner = MonitoringScanner(self.tmpdir)
        data = scanner.scan()
        types = {h["type"] for h in data["health_checks"]}
        self.assertIn("Kubernetes readiness probe", types)

    def test_spring_actuator(self):
        """Spring Actuator health endpoint is detected."""
        self._write_file("HealthConfig.java", """\
package com.example;

public class HealthConfig {
    String endpoint = "/actuator/health";
}
""")
        scanner = MonitoringScanner(self.tmpdir)
        data = scanner.scan()
        types = {h["type"] for h in data["health_checks"]}
        self.assertIn("Spring Actuator", types)


class TestMonitoringScannerEdgeCases(unittest.TestCase):
    """Tests for edge cases."""

    def test_nonexistent_path(self):
        scanner = MonitoringScanner("/nonexistent/path/12345")
        data = scanner.scan()
        for key in data:
            self.assertEqual(data[key], [])

    def test_empty_repo(self):
        tmpdir = tempfile.mkdtemp()
        try:
            scanner = MonitoringScanner(tmpdir)
            data = scanner.scan()
            for key in data:
                self.assertEqual(data[key], [])
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_skip_node_modules(self):
        tmpdir = tempfile.mkdtemp()
        try:
            filepath = Path(tmpdir) / "node_modules" / "winston" / "index.js"
            filepath.parent.mkdir(parents=True)
            filepath.write_text("const winston = require('winston');")
            scanner = MonitoringScanner(tmpdir)
            data = scanner.scan()
            self.assertEqual(data["logging_frameworks"], [])
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestMonitoringScannerMarkdown(unittest.TestCase):
    """Tests for format_as_markdown() output."""

    def setUp(self):
        self.scanner = MonitoringScanner("/tmp/dummy")

    def test_empty_data(self):
        data = {"terraform_monitoring": [], "config_files": [], "logging_frameworks": [], "health_checks": []}
        md = self.scanner.format_as_markdown(data)
        self.assertIn("No monitoring", md)
        self.assertIn("ENABLE_AI=false", md)

    def test_terraform_monitoring_table(self):
        data = {
            "terraform_monitoring": [
                {"type": "aws_cloudwatch_metric_alarm", "name": "cpu_high",
                 "category": "CloudWatch Alarms", "file": "monitoring.tf"},
            ],
            "config_files": [],
            "logging_frameworks": [],
            "health_checks": [],
        }
        md = self.scanner.format_as_markdown(data)
        self.assertIn("Monitoring Resources (Terraform)", md)
        self.assertIn("CloudWatch Alarms", md)

    def test_logging_frameworks_table(self):
        data = {
            "terraform_monitoring": [],
            "config_files": [],
            "logging_frameworks": [
                {"framework": "SLF4J", "language": "java", "file": "App.java"},
            ],
            "health_checks": [],
        }
        md = self.scanner.format_as_markdown(data)
        self.assertIn("Logging & Metrics Frameworks", md)
        self.assertIn("SLF4J", md)

    def test_health_checks_table(self):
        data = {
            "terraform_monitoring": [],
            "config_files": [],
            "logging_frameworks": [],
            "health_checks": [
                {"type": "Docker HEALTHCHECK", "file": "Dockerfile"},
            ],
        }
        md = self.scanner.format_as_markdown(data)
        self.assertIn("Health Checks", md)
        self.assertIn("Docker HEALTHCHECK", md)


if __name__ == "__main__":
    unittest.main()
