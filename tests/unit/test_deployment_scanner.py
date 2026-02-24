"""
Unit tests for DeploymentScanner -- CI/CD, containers, build tools, and IaC detection.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from investigator.core.static_analyzers.deployment_scanner import DeploymentScanner


class TestDeploymentScannerCICD(unittest.TestCase):
    """Tests for CI/CD pipeline detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content=""):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_github_actions_detected(self):
        """GitHub Actions workflow YAML is detected."""
        self._write_file(".github/workflows/ci.yml", """\
name: CI
on: [push, pull_request]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo "test"
""")
        scanner = DeploymentScanner(self.tmpdir)
        data = scanner.scan()
        ci_cd = data["ci_cd"]
        self.assertTrue(len(ci_cd) >= 1)
        gh_action = next(i for i in ci_cd if i["tool"] == "GitHub Actions")
        self.assertEqual(gh_action["workflow_name"], "CI")
        self.assertIn("push", gh_action.get("triggers", []))

    def test_jenkinsfile_detected(self):
        """Jenkinsfile is detected."""
        self._write_file("Jenkinsfile", "pipeline { stages { } }")
        scanner = DeploymentScanner(self.tmpdir)
        data = scanner.scan()
        tools = {i["tool"] for i in data["ci_cd"]}
        self.assertIn("Jenkins", tools)

    def test_gitlab_ci_detected(self):
        """GitLab CI YAML is detected."""
        self._write_file(".gitlab-ci.yml", "stages:\n  - build\n  - test")
        scanner = DeploymentScanner(self.tmpdir)
        data = scanner.scan()
        tools = {i["tool"] for i in data["ci_cd"]}
        self.assertIn("GitLab CI", tools)

    def test_circleci_detected(self):
        """CircleCI config is detected."""
        self._write_file(".circleci/config.yml", "version: 2.1")
        scanner = DeploymentScanner(self.tmpdir)
        data = scanner.scan()
        tools = {i["tool"] for i in data["ci_cd"]}
        self.assertIn("CircleCI", tools)


class TestDeploymentScannerContainers(unittest.TestCase):
    """Tests for container and deployment file detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content=""):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_dockerfile_detected(self):
        """Dockerfile is detected."""
        self._write_file("Dockerfile", "FROM python:3.12\nRUN pip install flask")
        scanner = DeploymentScanner(self.tmpdir)
        data = scanner.scan()
        tools = {i["tool"] for i in data["containers"]}
        self.assertIn("Docker", tools)

    def test_docker_compose_detected(self):
        """docker-compose.yml is detected."""
        self._write_file("docker-compose.yml", "version: '3'\nservices:\n  web:\n    image: nginx")
        scanner = DeploymentScanner(self.tmpdir)
        data = scanner.scan()
        tools = {i["tool"] for i in data["containers"]}
        self.assertIn("Docker Compose", tools)

    def test_helm_chart_detected(self):
        """Chart.yaml is detected as Helm (must be at repo root for non-glob pattern)."""
        self._write_file("Chart.yaml", "name: myapp\nversion: 1.0.0")
        self._write_file("values.yaml", "replicas: 1")
        scanner = DeploymentScanner(self.tmpdir)
        data = scanner.scan()
        tools = {i["tool"] for i in data["containers"]}
        self.assertIn("Helm", tools)

    def test_kustomization_detected(self):
        """kustomization.yaml is detected as Kustomize (must be at repo root for non-glob pattern)."""
        self._write_file("kustomization.yaml", "resources:\n  - deployment.yaml")
        scanner = DeploymentScanner(self.tmpdir)
        data = scanner.scan()
        tools = {i["tool"] for i in data["containers"]}
        self.assertIn("Kustomize", tools)


class TestDeploymentScannerBuildTools(unittest.TestCase):
    """Tests for build tool detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content=""):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_makefile_detected(self):
        """Makefile is detected as Make."""
        self._write_file("Makefile", "build:\n\tgo build .")
        scanner = DeploymentScanner(self.tmpdir)
        data = scanner.scan()
        tools = {i["tool"] for i in data["build_tools"]}
        self.assertIn("Make", tools)

    def test_mise_toml_detected(self):
        """mise.toml is detected."""
        self._write_file("mise.toml", "[tasks.build]\nrun = 'go build .'")
        scanner = DeploymentScanner(self.tmpdir)
        data = scanner.scan()
        tools = {i["tool"] for i in data["build_tools"]}
        self.assertIn("mise", tools)


class TestDeploymentScannerIaC(unittest.TestCase):
    """Tests for IaC detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content=""):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_ansible_playbook_detected(self):
        """playbook.yml is detected as Ansible."""
        self._write_file("playbook.yml", "---\n- hosts: all\n  tasks:\n    - name: Install pkg")
        scanner = DeploymentScanner(self.tmpdir)
        data = scanner.scan()
        tools = {i["tool"] for i in data["iac"]}
        self.assertIn("Ansible", tools)

    def test_vagrantfile_detected(self):
        """Vagrantfile is detected as Vagrant."""
        self._write_file("Vagrantfile", 'Vagrant.configure("2") do |config|\nend')
        scanner = DeploymentScanner(self.tmpdir)
        data = scanner.scan()
        tools = {i["tool"] for i in data["iac"]}
        self.assertIn("Vagrant", tools)


class TestDeploymentScannerDeployScripts(unittest.TestCase):
    """Tests for deploy script detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content=""):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_deploy_script_detected(self):
        """scripts/deploy.sh is detected."""
        self._write_file("scripts/deploy.sh", "#!/bin/bash\nkubectl apply -f .")
        scanner = DeploymentScanner(self.tmpdir)
        data = scanner.scan()
        self.assertTrue(len(data["deploy_scripts"]) >= 1)
        self.assertEqual(data["deploy_scripts"][0]["tool"], "Script")


class TestDeploymentScannerEdgeCases(unittest.TestCase):
    """Tests for edge cases and skip directories."""

    def test_nonexistent_path(self):
        scanner = DeploymentScanner("/nonexistent/path/12345")
        data = scanner.scan()
        for key in data:
            self.assertEqual(data[key], [])

    def test_empty_repo(self):
        tmpdir = tempfile.mkdtemp()
        try:
            scanner = DeploymentScanner(tmpdir)
            data = scanner.scan()
            for key in data:
                self.assertEqual(data[key], [])
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_node_modules_skipped(self):
        tmpdir = tempfile.mkdtemp()
        try:
            filepath = Path(tmpdir) / "node_modules" / "pkg" / "Dockerfile"
            filepath.parent.mkdir(parents=True)
            filepath.write_text("FROM node:18")
            scanner = DeploymentScanner(tmpdir)
            data = scanner.scan()
            self.assertEqual(data["containers"], [])
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestDeploymentScannerMarkdown(unittest.TestCase):
    """Tests for format_as_markdown() output."""

    def setUp(self):
        self.scanner = DeploymentScanner("/tmp/dummy")

    def test_empty_data(self):
        data = {"ci_cd": [], "containers": [], "build_tools": [], "iac": [], "deploy_scripts": []}
        md = self.scanner.format_as_markdown(data)
        self.assertIn("No CI/CD", md)
        self.assertIn("ENABLE_AI=false", md)

    def test_ci_cd_table(self):
        data = {
            "ci_cd": [{"tool": "GitHub Actions", "file": ".github/workflows/ci.yml",
                        "workflow_name": "CI", "triggers": ["push"]}],
            "containers": [],
            "build_tools": [],
            "iac": [],
            "deploy_scripts": [],
        }
        md = self.scanner.format_as_markdown(data)
        self.assertIn("CI/CD Pipelines", md)
        self.assertIn("GitHub Actions", md)
        self.assertIn("Name: CI", md)

    def test_containers_table(self):
        data = {
            "ci_cd": [],
            "containers": [{"tool": "Docker", "file": "Dockerfile"}],
            "build_tools": [],
            "iac": [],
            "deploy_scripts": [],
        }
        md = self.scanner.format_as_markdown(data)
        self.assertIn("Containerization", md)
        self.assertIn("Docker", md)


if __name__ == "__main__":
    unittest.main()
