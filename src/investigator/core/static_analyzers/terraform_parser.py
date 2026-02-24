"""
TerraformParser -- parses .tf files to extract resources, modules, variables, outputs,
data sources, providers, and environment configurations.

Covers sections: resources, service_dependencies, environments
"""

import re
from pathlib import Path
from collections import defaultdict


# AWS service category mapping for resource type prefixes
AWS_SERVICE_CATEGORIES = {
    "aws_vpc": "Networking",
    "aws_subnet": "Networking",
    "aws_route_table": "Networking",
    "aws_route": "Networking",
    "aws_internet_gateway": "Networking",
    "aws_nat_gateway": "Networking",
    "aws_network": "Networking",
    "aws_eip": "Networking",
    "aws_security_group": "Security",
    "aws_iam": "IAM",
    "aws_emr": "Compute/EMR",
    "aws_instance": "Compute/EC2",
    "aws_launch": "Compute/EC2",
    "aws_autoscaling": "Compute/EC2",
    "aws_ecs": "Compute/ECS",
    "aws_eks": "Compute/EKS",
    "aws_lambda": "Compute/Lambda",
    "aws_s3": "Storage/S3",
    "aws_dynamodb": "Database/DynamoDB",
    "aws_rds": "Database/RDS",
    "aws_elasticache": "Database/ElastiCache",
    "aws_redshift": "Database/Redshift",
    "aws_sqs": "Messaging/SQS",
    "aws_sns": "Messaging/SNS",
    "aws_cloudwatch": "Monitoring",
    "aws_cloudformation": "CloudFormation",
    "aws_api_gateway": "API Gateway",
    "aws_apigatewayv2": "API Gateway",
    "aws_lb": "Load Balancing",
    "aws_alb": "Load Balancing",
    "aws_elb": "Load Balancing",
    "aws_cloudfront": "CDN",
    "aws_route53": "DNS",
    "aws_acm": "Certificates",
    "aws_kms": "Encryption",
    "aws_secretsmanager": "Secrets",
    "aws_ssm": "Systems Manager",
    "aws_codepipeline": "CI/CD",
    "aws_codebuild": "CI/CD",
    "aws_codecommit": "CI/CD",
    "aws_codedeploy": "CI/CD",
    "aws_ecr": "Container Registry",
    "aws_kinesis": "Streaming",
    "aws_sagemaker": "ML/SageMaker",
    "aws_glue": "ETL/Glue",
    "aws_athena": "Analytics/Athena",
    "aws_elasticsearch": "Search",
    "aws_opensearch": "Search",
    "aws_waf": "Security/WAF",
    "aws_config": "Compliance",
    "aws_guardduty": "Security",
    "aws_macie": "Security",
}

# Non-AWS providers
OTHER_CATEGORIES = {
    "azurerm_": "Azure",
    "google_": "GCP",
    "kubernetes_": "Kubernetes",
    "helm_": "Helm",
    "docker_": "Docker",
    "null_": "Utility",
    "local_": "Utility",
    "random_": "Utility",
    "template_": "Utility",
    "tls_": "Security/TLS",
    "archive_": "Utility",
}


class TerraformParser:
    """Parses Terraform (.tf) files to extract infrastructure definitions."""

    # Regex for top-level blocks: resource "type" "name" {
    BLOCK_RE = re.compile(
        r'^(resource|data|module|variable|output|provider|terraform|locals)\s+'
        r'"([^"]*)"(?:\s+"([^"]*)")?\s*\{',
        re.MULTILINE,
    )

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    def parse(self) -> dict:
        """Parse all .tf files and return structured data."""
        result = {
            "resources": [],
            "data_sources": [],
            "modules": [],
            "variables": [],
            "outputs": [],
            "providers": [],
            "tf_files": [],
            "tfvars_files": [],
        }

        if not self.repo_path.exists():
            return result

        tf_files = list(self.repo_path.rglob("*.tf"))
        # Skip .terraform directory (downloaded providers/modules)
        tf_files = [f for f in tf_files if ".terraform" not in str(f)]
        result["tf_files"] = [str(f.relative_to(self.repo_path)) for f in tf_files]

        # Find .tfvars files
        tfvars = list(self.repo_path.rglob("*.tfvars"))
        tfvars += list(self.repo_path.rglob("*.tfvars.json"))
        tfvars = [f for f in tfvars if ".terraform" not in str(f)]
        result["tfvars_files"] = [str(f.relative_to(self.repo_path)) for f in tfvars]

        for tf_file in tf_files:
            try:
                content = tf_file.read_text(encoding="utf-8", errors="replace")
            except (OSError, IOError):
                continue

            rel_path = str(tf_file.relative_to(self.repo_path))
            self._parse_blocks(content, rel_path, result)

        return result

    def _parse_blocks(self, content: str, file_path: str, result: dict):
        """Extract all block declarations from a .tf file."""
        for match in self.BLOCK_RE.finditer(content):
            block_type = match.group(1)
            type_or_name = match.group(2)
            name = match.group(3)

            if block_type == "resource":
                result["resources"].append({
                    "type": type_or_name,
                    "name": name or "",
                    "file": file_path,
                    "category": self._categorize_resource(type_or_name),
                })
            elif block_type == "data":
                result["data_sources"].append({
                    "type": type_or_name,
                    "name": name or "",
                    "file": file_path,
                    "category": self._categorize_resource(type_or_name),
                })
            elif block_type == "module":
                source = self._extract_module_source(content, match.start())
                result["modules"].append({
                    "name": type_or_name,
                    "source": source,
                    "file": file_path,
                    "source_type": self._classify_module_source(source),
                })
            elif block_type == "variable":
                desc = self._extract_attribute(content, match.start(), "description")
                default = self._extract_attribute(content, match.start(), "default")
                result["variables"].append({
                    "name": type_or_name,
                    "description": desc,
                    "has_default": default is not None,
                    "file": file_path,
                })
            elif block_type == "output":
                result["outputs"].append({
                    "name": type_or_name,
                    "file": file_path,
                })
            elif block_type == "provider":
                result["providers"].append({
                    "name": type_or_name,
                    "file": file_path,
                })

    def _categorize_resource(self, resource_type: str) -> str:
        """Map a resource type to a service category."""
        # Check AWS categories (match longest prefix first)
        for prefix, category in sorted(AWS_SERVICE_CATEGORIES.items(), key=lambda x: -len(x[0])):
            if resource_type.startswith(prefix):
                return category
        # Check other providers
        for prefix, category in OTHER_CATEGORIES.items():
            if resource_type.startswith(prefix):
                return category
        return "Other"

    def _extract_module_source(self, content: str, block_start: int) -> str:
        """Extract the source attribute from a module block."""
        # Find the closing brace for this block
        block_content = self._extract_block_content(content, block_start)
        source_match = re.search(r'source\s*=\s*"([^"]*)"', block_content)
        return source_match.group(1) if source_match else ""

    def _extract_attribute(self, content: str, block_start: int, attr_name: str):
        """Extract a simple string attribute from a block."""
        block_content = self._extract_block_content(content, block_start)
        match = re.search(rf'{attr_name}\s*=\s*"([^"]*)"', block_content)
        if match:
            return match.group(1)
        # Check for non-string values
        match = re.search(rf'{attr_name}\s*=\s*(\S+)', block_content)
        return match.group(1) if match else None

    def _extract_block_content(self, content: str, block_start: int) -> str:
        """Extract content between { and matching } starting from block_start."""
        brace_start = content.find("{", block_start)
        if brace_start == -1:
            return ""
        depth = 0
        for i in range(brace_start, min(len(content), brace_start + 5000)):
            if content[i] == "{":
                depth += 1
            elif content[i] == "}":
                depth -= 1
                if depth == 0:
                    return content[brace_start:i + 1]
        return content[brace_start:brace_start + 2000]

    def _classify_module_source(self, source: str) -> str:
        """Classify a module source as local, git, or registry."""
        if not source:
            return "unknown"
        if source.startswith("./") or source.startswith("../"):
            return "local"
        if "github.com" in source or source.startswith("git::"):
            return "git"
        if "s3::" in source:
            return "s3"
        if "/" in source and not source.startswith("http"):
            return "registry"
        return "other"

    # --- Formatters for .arch.md sections ---

    def format_resources(self, data: dict) -> str:
        """Format the resources section."""
        resources = data.get("resources", [])
        data_sources = data.get("data_sources", [])

        if not resources and not data_sources:
            return self._no_terraform("No Terraform resources found.")

        lines = []

        if resources:
            # Group by category
            by_category = defaultdict(list)
            for r in resources:
                by_category[r["category"]].append(r)

            lines.append("**Infrastructure Resources:**\n")
            lines.append("| Resource Type | Name | Category | File |")
            lines.append("|--------------|------|----------|------|")
            for category in sorted(by_category.keys()):
                for r in sorted(by_category[category], key=lambda x: x["type"]):
                    lines.append(f"| `{r['type']}` | {r['name']} | {category} | {r['file']} |")

            lines.append(f"\n**Total Resources:** {len(resources)}")

            # Category summary
            lines.append("\n**Resources by Category:**\n")
            lines.append("| Category | Count |")
            lines.append("|----------|------:|")
            for cat in sorted(by_category.keys()):
                lines.append(f"| {cat} | {len(by_category[cat])} |")

        if data_sources:
            lines.append("\n**Data Sources:**\n")
            lines.append("| Data Source Type | Name | File |")
            lines.append("|-----------------|------|------|")
            for d in sorted(data_sources, key=lambda x: x["type"]):
                lines.append(f"| `{d['type']}` | {d['name']} | {d['file']} |")

        lines.append("\n---")
        lines.append("*Generated by static analysis (ENABLE_AI=false)*")
        return "\n".join(lines)

    def format_service_dependencies(self, data: dict) -> str:
        """Format the service_dependencies section."""
        modules = data.get("modules", [])
        providers = data.get("providers", [])
        outputs = data.get("outputs", [])
        resources = data.get("resources", [])

        if not modules and not providers:
            return self._no_terraform("No module or provider dependencies found.")

        lines = []

        if modules:
            lines.append("**Module Dependencies:**\n")
            lines.append("| Module | Source | Type | File |")
            lines.append("|--------|--------|------|------|")
            for m in sorted(modules, key=lambda x: x["name"]):
                lines.append(f"| `{m['name']}` | {m['source']} | {m['source_type']} | {m['file']} |")

            # Show module dependency chain from output references
            local_modules = [m for m in modules if m["source_type"] == "local"]
            if local_modules:
                lines.append("\n**Module Dependency Chain:**")
                lines.append("```")
                for m in local_modules:
                    lines.append(f"  root -> {m['name']} (source: {m['source']})")
                lines.append("```")

        if providers:
            lines.append("\n**Providers:**\n")
            lines.append("| Provider | File |")
            lines.append("|----------|------|")
            seen = set()
            for p in sorted(providers, key=lambda x: x["name"]):
                if p["name"] not in seen:
                    seen.add(p["name"])
                    lines.append(f"| `{p['name']}` | {p['file']} |")

        # Check for remote state references
        remote_states = [d for d in data.get("data_sources", [])
                         if d["type"] == "terraform_remote_state"]
        if remote_states:
            lines.append("\n**Remote State Dependencies:**\n")
            for rs in remote_states:
                lines.append(f"- `{rs['name']}` (in {rs['file']})")

        if outputs:
            lines.append(f"\n**Outputs Exposed:** {len(outputs)}")
            for o in sorted(outputs, key=lambda x: x["name"])[:20]:
                lines.append(f"- `{o['name']}` ({o['file']})")
            if len(outputs) > 20:
                lines.append(f"- ... and {len(outputs) - 20} more")

        lines.append("\n---")
        lines.append("*Generated by static analysis (ENABLE_AI=false)*")
        return "\n".join(lines)

    def format_environments(self, data: dict) -> str:
        """Format the environments section."""
        tfvars = data.get("tfvars_files", [])
        variables = data.get("variables", [])

        lines = []

        if tfvars:
            lines.append("**Environment Configuration Files:**\n")
            lines.append("| File | Inferred Environment |")
            lines.append("|------|---------------------|")
            for f in sorted(tfvars):
                env_name = self._infer_env_from_filename(f)
                lines.append(f"| `{f}` | {env_name} |")
        else:
            lines.append("*No .tfvars files found.*\n")

        if variables:
            env_vars = [v for v in variables if self._is_env_related_var(v["name"])]
            if env_vars:
                lines.append("\n**Environment-Related Variables:**\n")
                lines.append("| Variable | Description | Has Default | File |")
                lines.append("|----------|-------------|:-----------:|------|")
                for v in sorted(env_vars, key=lambda x: x["name"]):
                    desc = v["description"] or "-"
                    default = "Yes" if v["has_default"] else "No"
                    lines.append(f"| `{v['name']}` | {desc} | {default} | {v['file']} |")

            lines.append(f"\n**Total Variables:** {len(variables)} ({len(env_vars)} environment-related)")
        else:
            lines.append("\n*No Terraform variables found.*")

        lines.append("\n---")
        lines.append("*Generated by static analysis (ENABLE_AI=false)*")
        return "\n".join(lines)

    def _infer_env_from_filename(self, filename: str) -> str:
        """Infer environment name from a .tfvars filename."""
        name = Path(filename).stem.lower()
        for env in ("prod", "production", "staging", "stage", "dev", "development",
                     "test", "testing", "qa", "uat", "sandbox", "demo"):
            if env in name:
                return env.capitalize()
        if name == "terraform":
            return "Default"
        return "Custom"

    def _is_env_related_var(self, var_name: str) -> bool:
        """Check if a variable name is environment-related."""
        env_keywords = ("env", "environment", "region", "profile", "account",
                        "stage", "workspace", "domain", "zone", "cluster_name")
        name_lower = var_name.lower()
        return any(kw in name_lower for kw in env_keywords)

    def _no_terraform(self, message: str) -> str:
        return f"*{message}*\n\n---\n*Generated by static analysis (ENABLE_AI=false)*"
