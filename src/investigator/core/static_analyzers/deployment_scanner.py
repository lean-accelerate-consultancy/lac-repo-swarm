"""
DeploymentScanner -- scans for CI/CD pipelines, Dockerfiles, Helm charts,
and deployment-related configuration files.

Covers section: deployment
"""

import re
from pathlib import Path

# Known CI/CD file patterns
CI_CD_PATTERNS = {
    ".github/workflows/*.yml": "GitHub Actions",
    ".github/workflows/*.yaml": "GitHub Actions",
    "Jenkinsfile": "Jenkins",
    "Jenkinsfile.*": "Jenkins",
    ".gitlab-ci.yml": "GitLab CI",
    ".circleci/config.yml": "CircleCI",
    "azure-pipelines.yml": "Azure DevOps",
    "azure-pipelines.yaml": "Azure DevOps",
    "bitbucket-pipelines.yml": "Bitbucket Pipelines",
    ".travis.yml": "Travis CI",
    "appveyor.yml": "AppVeyor",
    "cloudbuild.yaml": "Google Cloud Build",
    "cloudbuild.yml": "Google Cloud Build",
    "buildspec.yml": "AWS CodeBuild",
    "buildspec.yaml": "AWS CodeBuild",
    ".drone.yml": "Drone CI",
    "Taskfile.yml": "Task",
    "Taskfile.yaml": "Task",
    "Earthfile": "Earthly",
}

# Container and deployment file patterns
DEPLOY_PATTERNS = {
    "Dockerfile": "Docker",
    "Dockerfile.*": "Docker",
    "*.Dockerfile": "Docker",
    "docker-compose.yml": "Docker Compose",
    "docker-compose.yaml": "Docker Compose",
    "docker-compose.*.yml": "Docker Compose",
    "compose.yml": "Docker Compose",
    "compose.yaml": "Docker Compose",
    "Chart.yaml": "Helm",
    "values.yaml": "Helm",
    "values.*.yaml": "Helm",
    "helmfile.yaml": "Helmfile",
    "kustomization.yaml": "Kustomize",
    "kustomization.yml": "Kustomize",
    "skaffold.yaml": "Skaffold",
    "Procfile": "Heroku",
    "app.yaml": "Google App Engine",
    "serverless.yml": "Serverless Framework",
    "serverless.yaml": "Serverless Framework",
    "sam-template.yaml": "AWS SAM",
    "template.yaml": "AWS SAM/CloudFormation",
    "cdk.json": "AWS CDK",
    "pulumi.yaml": "Pulumi",
}

# Build tool patterns
BUILD_PATTERNS = {
    "Makefile": "Make",
    "GNUmakefile": "Make",
    "makefile": "Make",
    "Rakefile": "Rake",
    "Gruntfile.js": "Grunt",
    "gulpfile.js": "Gulp",
    "webpack.config.js": "Webpack",
    "rollup.config.js": "Rollup",
    "vite.config.*": "Vite",
    "mise.toml": "mise",
    ".mise.toml": "mise",
}

# IaC and config management
IAC_PATTERNS = {
    "*.playbook.yml": "Ansible",
    "*.playbook.yaml": "Ansible",
    "playbook.yml": "Ansible",
    "playbook.yaml": "Ansible",
    "ansible.cfg": "Ansible",
    "site.yml": "Ansible",
    "site.yaml": "Ansible",
    "roles/*/tasks/main.yml": "Ansible",
    "Vagrantfile": "Vagrant",
    "Berksfile": "Chef",
    "Puppetfile": "Puppet",
}


class DeploymentScanner:
    """Scans a repository for CI/CD, containerization, and deployment files."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    def scan(self) -> dict:
        """Scan the repo and return structured deployment data."""
        result = {
            "ci_cd": [],
            "containers": [],
            "build_tools": [],
            "iac": [],
            "deploy_scripts": [],
        }

        if not self.repo_path.exists():
            return result

        self._scan_patterns(CI_CD_PATTERNS, result["ci_cd"])
        self._scan_patterns(DEPLOY_PATTERNS, result["containers"])
        self._scan_patterns(BUILD_PATTERNS, result["build_tools"])
        self._scan_patterns(IAC_PATTERNS, result["iac"])
        self._scan_deploy_scripts(result["deploy_scripts"])

        # Parse GitHub Actions workflows for more detail
        for item in result["ci_cd"]:
            if item["tool"] == "GitHub Actions":
                self._parse_github_actions(item)

        return result

    def _scan_patterns(self, patterns: dict, target_list: list):
        """Scan for files matching known patterns."""
        for pattern, tool in patterns.items():
            if "*" in pattern:
                matches = list(self.repo_path.rglob(pattern))
            else:
                match = self.repo_path / pattern
                matches = [match] if match.exists() else []

            # Filter out .terraform, node_modules, .venv, vendor
            skip_dirs = {".terraform", "node_modules", ".venv", "venv", "vendor", ".git"}
            matches = [m for m in matches
                       if not any(d in m.parts for d in skip_dirs)]

            for match in matches:
                rel_path = str(match.relative_to(self.repo_path))
                target_list.append({
                    "tool": tool,
                    "file": rel_path,
                })

    def _scan_deploy_scripts(self, target_list: list):
        """Scan for deployment-related scripts."""
        skip_dirs = {".terraform", "node_modules", ".venv", "venv", "vendor", ".git"}
        script_patterns = ["scripts/deploy*", "scripts/release*", "scripts/build*",
                           "deploy/*", "deploy.*", "bin/deploy*"]
        for pattern in script_patterns:
            for match in self.repo_path.rglob(pattern):
                if not any(d in match.parts for d in skip_dirs):
                    rel_path = str(match.relative_to(self.repo_path))
                    target_list.append({
                        "tool": "Script",
                        "file": rel_path,
                    })

    def _parse_github_actions(self, item: dict):
        """Parse a GitHub Actions workflow file for trigger and job details."""
        filepath = self.repo_path / item["file"]
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
        except (OSError, IOError):
            return

        # Extract workflow name
        name_match = re.search(r'^name:\s*(.+)', content, re.MULTILINE)
        if name_match:
            item["workflow_name"] = name_match.group(1).strip().strip('"').strip("'")

        # Extract triggers
        triggers = []
        on_match = re.search(r'^on:\s*(.+)', content, re.MULTILINE)
        if on_match:
            val = on_match.group(1).strip()
            if val.startswith("["):
                triggers = [t.strip().strip('"').strip("'")
                            for t in val.strip("[]").split(",")]
            elif val and val != "":
                triggers = [val]

        # Also check for multi-line on: block
        on_block = re.findall(r'^on:\s*\n((?:\s+\w+.*\n)+)', content, re.MULTILINE)
        if on_block:
            for line in on_block[0].strip().split("\n"):
                trigger = line.strip().rstrip(":")
                if trigger and not trigger.startswith("#"):
                    triggers.append(trigger)

        if triggers:
            item["triggers"] = triggers

        # Extract job names
        jobs = re.findall(r'^\s{2}(\w[\w-]*):', content, re.MULTILINE)
        if jobs:
            item["jobs"] = jobs

    def format_as_markdown(self, data: dict) -> str:
        """Format deployment data as markdown."""
        ci_cd = data.get("ci_cd", [])
        containers = data.get("containers", [])
        build_tools = data.get("build_tools", [])
        iac = data.get("iac", [])
        deploy_scripts = data.get("deploy_scripts", [])

        all_items = ci_cd + containers + build_tools + iac + deploy_scripts
        if not all_items:
            return ("*No CI/CD, containerization, or deployment files detected.*\n\n"
                    "---\n*Generated by static analysis (ENABLE_AI=false)*")

        lines = []

        if ci_cd:
            lines.append("**CI/CD Pipelines:**\n")
            lines.append("| Tool | File | Details |")
            lines.append("|------|------|---------|")
            for item in sorted(ci_cd, key=lambda x: x["file"]):
                details = []
                if "workflow_name" in item:
                    details.append(f"Name: {item['workflow_name']}")
                if "triggers" in item:
                    details.append(f"Triggers: {', '.join(item['triggers'])}")
                if "jobs" in item:
                    details.append(f"Jobs: {', '.join(item['jobs'])}")
                detail_str = "; ".join(details) if details else "-"
                lines.append(f"| {item['tool']} | `{item['file']}` | {detail_str} |")

        if containers:
            lines.append("\n**Containerization & Orchestration:**\n")
            lines.append("| Tool | File |")
            lines.append("|------|------|")
            for item in sorted(containers, key=lambda x: x["file"]):
                lines.append(f"| {item['tool']} | `{item['file']}` |")

        if iac:
            lines.append("\n**Infrastructure as Code:**\n")
            lines.append("| Tool | File |")
            lines.append("|------|------|")
            for item in sorted(iac, key=lambda x: x["file"]):
                lines.append(f"| {item['tool']} | `{item['file']}` |")

        if build_tools:
            lines.append("\n**Build Tools:**\n")
            lines.append("| Tool | File |")
            lines.append("|------|------|")
            for item in sorted(build_tools, key=lambda x: x["file"]):
                lines.append(f"| {item['tool']} | `{item['file']}` |")

        if deploy_scripts:
            lines.append("\n**Deployment Scripts:**\n")
            for item in sorted(deploy_scripts, key=lambda x: x["file"]):
                lines.append(f"- `{item['file']}`")

        lines.append("\n---")
        lines.append("*Generated by static analysis (ENABLE_AI=false)*")
        return "\n".join(lines)
