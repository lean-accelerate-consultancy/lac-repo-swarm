"""
APIScanner -- detects API definitions from OpenAPI/Swagger specs, route annotations,
and API Gateway resources in Terraform.

Covers section: APIs
"""

import re
import json
from pathlib import Path


# Route annotation patterns per framework
ROUTE_PATTERNS = {
    # Java Spring
    "java_spring": {
        "glob": "**/*.java",
        "patterns": [
            re.compile(r'@(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)\s*\(\s*(?:value\s*=\s*)?"([^"]*)"'),
            re.compile(r'@RequestMapping\s*\(\s*(?:value\s*=\s*)?\{[^}]*"([^"]*)"'),
        ],
        "method_map": {
            "GetMapping": "GET",
            "PostMapping": "POST",
            "PutMapping": "PUT",
            "DeleteMapping": "DELETE",
            "PatchMapping": "PATCH",
            "RequestMapping": "ANY",
        },
    },
    # Go (common routers)
    "go_router": {
        "glob": "**/*.go",
        "patterns": [
            re.compile(r'\.(Get|Post|Put|Delete|Patch|Handle|HandleFunc)\s*\(\s*"([^"]*)"'),
            re.compile(r'\.Methods\s*\(\s*"(GET|POST|PUT|DELETE|PATCH)"[^)]*\)\.Path\s*\(\s*"([^"]*)"'),
        ],
        "method_map": {
            "Get": "GET", "Post": "POST", "Put": "PUT",
            "Delete": "DELETE", "Patch": "PATCH",
            "Handle": "ANY", "HandleFunc": "ANY",
        },
    },
    # Python Flask/FastAPI
    "python_web": {
        "glob": "**/*.py",
        "patterns": [
            re.compile(r'@\w+\.(get|post|put|delete|patch|route)\s*\(\s*["\']([^"\']*)["\']'),
            re.compile(r'@app\.(get|post|put|delete|patch|route)\s*\(\s*["\']([^"\']*)["\']'),
        ],
        "method_map": {
            "get": "GET", "post": "POST", "put": "PUT",
            "delete": "DELETE", "patch": "PATCH", "route": "ANY",
        },
    },
    # JavaScript/TypeScript Express
    "js_express": {
        "glob": "**/*.{js,ts}",
        "patterns": [
            re.compile(r'\w+\.(get|post|put|delete|patch|all)\s*\(\s*["\']([^"\']*)["\']'),
        ],
        "method_map": {
            "get": "GET", "post": "POST", "put": "PUT",
            "delete": "DELETE", "patch": "PATCH", "all": "ANY",
        },
    },
}

# OAS/Swagger indicator keys
OAS_INDICATORS = {"openapi", "swagger", "paths"}

# Terraform API Gateway resource types
API_GW_RESOURCES = {
    "aws_api_gateway_rest_api",
    "aws_api_gateway_resource",
    "aws_api_gateway_method",
    "aws_api_gateway_integration",
    "aws_api_gateway_stage",
    "aws_api_gateway_deployment",
    "aws_apigatewayv2_api",
    "aws_apigatewayv2_route",
    "aws_apigatewayv2_stage",
    "aws_apigatewayv2_integration",
}


class APIScanner:
    """Scans a repository for API definitions and endpoints."""

    SKIP_DIRS = {".terraform", "node_modules", ".venv", "venv", "vendor",
                 ".git", "__pycache__", "dist", "build", "target"}

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    def scan(self) -> dict:
        """Scan the repo for API definitions."""
        result = {
            "oas_specs": [],
            "route_endpoints": [],
            "api_gateway_resources": [],
        }

        if not self.repo_path.exists():
            return result

        self._scan_oas_specs(result)
        self._scan_route_annotations(result)
        self._scan_terraform_api_gw(result)

        return result

    def _should_skip(self, path: Path) -> bool:
        return any(d in path.parts for d in self.SKIP_DIRS)

    def _scan_oas_specs(self, result: dict):
        """Find and parse OpenAPI/Swagger specification files."""
        # Check YAML files
        for pattern in ["**/*.yaml", "**/*.yml"]:
            for f in self.repo_path.rglob(pattern):
                if self._should_skip(f):
                    continue
                if self._is_oas_file(f):
                    spec = self._parse_oas(f)
                    if spec:
                        result["oas_specs"].append(spec)

        # Check JSON files
        for f in self.repo_path.rglob("**/*.json"):
            if self._should_skip(f):
                continue
            if self._is_oas_file(f):
                spec = self._parse_oas(f)
                if spec:
                    result["oas_specs"].append(spec)

    def _is_oas_file(self, filepath: Path) -> bool:
        """Quick check if a file looks like an OAS/Swagger spec."""
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")[:2000]
        except (OSError, IOError):
            return False
        content_lower = content.lower()
        return any(indicator in content_lower for indicator in ("openapi", "swagger"))

    def _parse_oas(self, filepath: Path) -> dict:
        """Parse an OAS/Swagger file and extract endpoints."""
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
        except (OSError, IOError):
            return None

        rel_path = str(filepath.relative_to(self.repo_path))

        # Try JSON first
        if filepath.suffix == ".json":
            try:
                data = json.loads(content)
                return self._extract_oas_data(data, rel_path)
            except json.JSONDecodeError:
                return None

        # Try YAML
        try:
            import yaml
            data = yaml.safe_load(content)
            if isinstance(data, dict):
                return self._extract_oas_data(data, rel_path)
        except Exception:
            pass

        return None

    def _extract_oas_data(self, data: dict, file_path: str) -> dict:
        """Extract API info from parsed OAS data."""
        if not isinstance(data, dict):
            return None

        version = data.get("openapi", data.get("swagger", ""))
        if not version:
            return None

        info = data.get("info", {})
        paths = data.get("paths", {})

        endpoints = []
        for path, methods in paths.items():
            if not isinstance(methods, dict):
                continue
            for method, details in methods.items():
                if method.upper() in ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"):
                    summary = ""
                    if isinstance(details, dict):
                        summary = details.get("summary", details.get("description", ""))
                        if summary and len(summary) > 80:
                            summary = summary[:77] + "..."
                    endpoints.append({
                        "method": method.upper(),
                        "path": path,
                        "summary": summary,
                    })

        return {
            "file": file_path,
            "version": str(version),
            "title": info.get("title", ""),
            "api_version": info.get("version", ""),
            "endpoint_count": len(endpoints),
            "endpoints": endpoints,
        }

    def _scan_route_annotations(self, result: dict):
        """Scan source files for route annotations."""
        for framework, config in ROUTE_PATTERNS.items():
            glob_pattern = config["glob"]
            # Handle {ext1,ext2} patterns manually
            if "{" in glob_pattern:
                # Split into individual patterns
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

                for pattern in config["patterns"]:
                    for match in pattern.finditer(content):
                        method_key = match.group(1)
                        path = match.group(2)
                        method = config["method_map"].get(method_key, method_key.upper())
                        result["route_endpoints"].append({
                            "method": method,
                            "path": path,
                            "file": rel_path,
                            "framework": framework,
                        })

    def _scan_terraform_api_gw(self, result: dict):
        """Scan Terraform files for API Gateway resources."""
        for tf_file in self.repo_path.rglob("*.tf"):
            if self._should_skip(tf_file):
                continue
            try:
                content = tf_file.read_text(encoding="utf-8", errors="replace")
            except (OSError, IOError):
                continue

            rel_path = str(tf_file.relative_to(self.repo_path))
            for res_type in API_GW_RESOURCES:
                pattern = re.compile(rf'resource\s+"{res_type}"\s+"([^"]*)"')
                for match in pattern.finditer(content):
                    result["api_gateway_resources"].append({
                        "type": res_type,
                        "name": match.group(1),
                        "file": rel_path,
                    })

    def format_as_markdown(self, data: dict) -> str:
        """Format API data as markdown."""
        oas = data.get("oas_specs", [])
        routes = data.get("route_endpoints", [])
        api_gw = data.get("api_gateway_resources", [])

        if not oas and not routes and not api_gw:
            return ("*No API definitions, route annotations, or API Gateway resources detected.*\n\n"
                    "---\n*Generated by static analysis (ENABLE_AI=false)*")

        lines = []

        if oas:
            for spec in oas:
                title = spec["title"] or "Untitled API"
                lines.append(f"**OpenAPI Spec: {title}**")
                lines.append(f"- File: `{spec['file']}`")
                lines.append(f"- Version: {spec['version']}")
                if spec["api_version"]:
                    lines.append(f"- API Version: {spec['api_version']}")
                lines.append(f"- Endpoints: {spec['endpoint_count']}")

                if spec["endpoints"]:
                    lines.append("")
                    lines.append("| Method | Path | Summary |")
                    lines.append("|--------|------|---------|")
                    for ep in spec["endpoints"][:30]:
                        lines.append(f"| {ep['method']} | `{ep['path']}` | {ep['summary']} |")
                    if len(spec["endpoints"]) > 30:
                        lines.append(f"| ... | *{len(spec['endpoints']) - 30} more endpoints* | |")
                lines.append("")

        if routes:
            lines.append("**Route Endpoints (from code):**\n")
            lines.append("| Method | Path | File |")
            lines.append("|--------|------|------|")
            seen = set()
            for r in sorted(routes, key=lambda x: (x["path"], x["method"])):
                key = (r["method"], r["path"])
                if key not in seen:
                    seen.add(key)
                    lines.append(f"| {r['method']} | `{r['path']}` | {r['file']} |")
            lines.append("")

        if api_gw:
            lines.append("**API Gateway Resources (Terraform):**\n")
            lines.append("| Resource Type | Name | File |")
            lines.append("|--------------|------|------|")
            for r in sorted(api_gw, key=lambda x: x["type"]):
                lines.append(f"| `{r['type']}` | {r['name']} | {r['file']} |")

        lines.append("\n---")
        lines.append("*Generated by static analysis (ENABLE_AI=false)*")
        return "\n".join(lines)
