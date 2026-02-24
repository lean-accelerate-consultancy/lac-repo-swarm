"""
SecurityScanner -- detects security configurations, hardcoded secrets,
authentication/authorization patterns, and security policy files.

Covers sections: security_check, authentication, authorization
"""

import re
from pathlib import Path
from typing import List


# Hardcoded secret patterns (high-confidence, low false-positive)
SECRET_PATTERNS = [
    (re.compile(r'(?:password|passwd|pwd)\s*[=:]\s*["\'][^"\']{8,}["\']', re.IGNORECASE),
     "Hardcoded password"),
    (re.compile(r'(?:api_key|apikey|api-key)\s*[=:]\s*["\'][A-Za-z0-9_\-]{16,}["\']', re.IGNORECASE),
     "Hardcoded API key"),
    (re.compile(r'(?:secret_key|secret)\s*[=:]\s*["\'][A-Za-z0-9_\-/+=]{16,}["\']', re.IGNORECASE),
     "Hardcoded secret key"),
    (re.compile(r'(?:access_token|token)\s*[=:]\s*["\'][A-Za-z0-9_\-\.]{20,}["\']', re.IGNORECASE),
     "Hardcoded access token"),
    (re.compile(r'AKIA[0-9A-Z]{16}'), "AWS Access Key ID"),
    (re.compile(r'(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}'), "GitHub Token"),
    (re.compile(r'sk-[A-Za-z0-9]{20,}'), "OpenAI/Stripe-style Secret Key"),
    (re.compile(r'-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----'), "Private key file"),
]

# Auth framework detection patterns per language
AUTH_FRAMEWORK_PATTERNS = {
    "Spring Security": {
        "glob": ["**/*.java", "**/*.xml", "**/*.properties", "**/*.yml", "**/*.yaml"],
        "patterns": [
            "org.springframework.security",
            "spring.security",
            "spring-boot-starter-security",
            "@EnableWebSecurity",
            "WebSecurityConfigurerAdapter",
            "SecurityFilterChain",
        ],
    },
    "OAuth2/OIDC": {
        "glob": ["**/*.java", "**/*.py", "**/*.go", "**/*.js", "**/*.ts",
                 "**/*.yml", "**/*.yaml", "**/*.properties", "**/*.json"],
        "patterns": [
            "oauth2",
            "openid-connect",
            "oidc",
            "client_credentials",
            "authorization_code",
            "grant_type",
        ],
    },
    "JWT": {
        "glob": ["**/*.java", "**/*.py", "**/*.go", "**/*.js", "**/*.ts"],
        "patterns": [
            "jsonwebtoken",
            "io.jsonwebtoken",
            "jwt.decode",
            "jwt.verify",
            "jwt.sign",
            "JwtDecoder",
            "JwtEncoder",
            "golang-jwt",
            "pyjwt",
        ],
    },
    "Keycloak": {
        "glob": ["**/*.java", "**/*.py", "**/*.js", "**/*.ts",
                 "**/*.yml", "**/*.yaml", "**/*.json"],
        "patterns": [
            "keycloak",
            "org.keycloak",
            "keycloak-connect",
        ],
    },
    "Passport.js": {
        "glob": ["**/*.js", "**/*.ts"],
        "patterns": [
            "require('passport')",
            'require("passport")',
            "from 'passport'",
            'from "passport"',
            "passport-local",
            "passport-jwt",
            "passport-google",
        ],
    },
    "Auth0": {
        "glob": ["**/*.java", "**/*.py", "**/*.go", "**/*.js", "**/*.ts",
                 "**/*.yml", "**/*.yaml", "**/*.json"],
        "patterns": [
            "auth0",
            "@auth0/",
            "com.auth0",
        ],
    },
    "Devise (Rails)": {
        "glob": ["**/*.rb", "**/Gemfile"],
        "patterns": [
            "devise",
            "Devise",
        ],
    },
}

# K8s RBAC manifest patterns
K8S_RBAC_PATTERNS = [
    (re.compile(r'kind:\s*(?:Role|ClusterRole|RoleBinding|ClusterRoleBinding)', re.IGNORECASE),
     "K8s RBAC"),
    (re.compile(r'kind:\s*ServiceAccount', re.IGNORECASE),
     "K8s ServiceAccount"),
    (re.compile(r'kind:\s*NetworkPolicy', re.IGNORECASE),
     "K8s NetworkPolicy"),
    (re.compile(r'kind:\s*PodSecurityPolicy', re.IGNORECASE),
     "K8s PodSecurityPolicy"),
]

# Security config files
SECURITY_CONFIG_FILES = {
    ".snyk": "Snyk",
    "snyk.json": "Snyk",
    ".trivyignore": "Trivy",
    "trivy.yaml": "Trivy",
    ".checkov.yml": "Checkov",
    ".checkov.yaml": "Checkov",
    "tfsec.yml": "tfsec",
    ".tfsec.yml": "tfsec",
    "sonar-project.properties": "SonarQube",
    ".sonarcloud.properties": "SonarCloud",
    "security.txt": "security.txt",
    ".security.yml": "Security Policy",
    "SECURITY.md": "Security Policy",
    "codeql-config.yml": "CodeQL",
    ".github/codeql/codeql-config.yml": "CodeQL",
    "dependency-check-report.xml": "OWASP Dependency-Check",
    ".dependabot/config.yml": "Dependabot",
    ".github/dependabot.yml": "Dependabot",
}

# Security header patterns in code
SECURITY_HEADER_PATTERNS = [
    (re.compile(r'(?:Strict-Transport-Security|HSTS)', re.IGNORECASE), "HSTS"),
    (re.compile(r'Content-Security-Policy', re.IGNORECASE), "CSP"),
    (re.compile(r'X-Frame-Options', re.IGNORECASE), "X-Frame-Options"),
    (re.compile(r'X-Content-Type-Options', re.IGNORECASE), "X-Content-Type-Options"),
    (re.compile(r'X-XSS-Protection', re.IGNORECASE), "X-XSS-Protection"),
    (re.compile(r'Referrer-Policy', re.IGNORECASE), "Referrer-Policy"),
]


class SecurityScanner:
    """Scans a repository for security configurations, secrets, auth patterns, and RBAC."""

    SKIP_DIRS = {".terraform", "node_modules", ".venv", "venv", "vendor",
                 ".git", "__pycache__", "dist", "build", "target",
                 ".gradle", ".m2", ".npm"}

    CODE_EXTENSIONS = {
        ".java", ".py", ".go", ".js", ".ts", ".rb", ".cs", ".php",
        ".yml", ".yaml", ".json", ".xml", ".properties", ".toml",
        ".cfg", ".conf", ".ini", ".env.example", ".env.sample",
        ".sh", ".bash", ".pem", ".key", ".tf",
    }

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    def scan(self) -> dict:
        """Scan the repo for security-related patterns."""
        result = {
            "secret_findings": [],
            "auth_frameworks": [],
            "k8s_rbac": [],
            "security_configs": [],
            "security_headers": [],
        }

        if not self.repo_path.exists():
            return result

        self._scan_secrets(result)
        self._scan_auth_frameworks(result)
        self._scan_k8s_rbac(result)
        self._scan_security_configs(result)
        self._scan_security_headers(result)

        return result

    def _should_skip(self, path: Path) -> bool:
        return any(d in path.parts for d in self.SKIP_DIRS)

    def _scan_secrets(self, result: dict):
        """Scan code files for hardcoded secret patterns."""
        found_files = set()

        for f in self.repo_path.rglob("*"):
            if not f.is_file():
                continue
            if self._should_skip(f):
                continue
            if f.suffix not in self.CODE_EXTENSIONS:
                continue
            # Skip actual .env files (likely secrets) -- we flag .env.example
            if f.name == ".env" or f.name == ".env.local":
                continue
            if f.stat().st_size > 500_000:
                continue

            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except (OSError, IOError):
                continue

            rel_path = str(f.relative_to(self.repo_path))

            for pattern, desc in SECRET_PATTERNS:
                if pattern.search(content) and rel_path not in found_files:
                    found_files.add(rel_path)
                    result["secret_findings"].append({
                        "type": desc,
                        "file": rel_path,
                    })
                    break  # One finding per file

    def _scan_auth_frameworks(self, result: dict):
        """Scan for authentication/authorization framework usage."""
        found = set()

        for framework, config in AUTH_FRAMEWORK_PATTERNS.items():
            if framework in found:
                continue

            for glob_pattern in config["glob"]:
                if framework in found:
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

                    for pattern_str in config["patterns"]:
                        if pattern_str in content:
                            found.add(framework)
                            rel_path = str(f.relative_to(self.repo_path))
                            result["auth_frameworks"].append({
                                "framework": framework,
                                "file": rel_path,
                            })
                            break

                    if framework in found:
                        break

    def _scan_k8s_rbac(self, result: dict):
        """Scan K8s manifests for RBAC resources."""
        for f in self.repo_path.rglob("*.yaml"):
            if self._should_skip(f):
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except (OSError, IOError):
                continue

            rel_path = str(f.relative_to(self.repo_path))

            for pattern, desc in K8S_RBAC_PATTERNS:
                if pattern.search(content):
                    result["k8s_rbac"].append({
                        "type": desc,
                        "file": rel_path,
                    })
                    break  # One match per file

        # Also scan .yml files
        for f in self.repo_path.rglob("*.yml"):
            if self._should_skip(f):
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except (OSError, IOError):
                continue

            rel_path = str(f.relative_to(self.repo_path))
            if any(r["file"] == rel_path for r in result["k8s_rbac"]):
                continue

            for pattern, desc in K8S_RBAC_PATTERNS:
                if pattern.search(content):
                    result["k8s_rbac"].append({
                        "type": desc,
                        "file": rel_path,
                    })
                    break

    def _scan_security_configs(self, result: dict):
        """Scan for known security tool configuration files."""
        for filename, tool in SECURITY_CONFIG_FILES.items():
            matches = list(self.repo_path.rglob(filename))
            for match in matches:
                if self._should_skip(match):
                    continue
                rel_path = str(match.relative_to(self.repo_path))
                result["security_configs"].append({
                    "tool": tool,
                    "file": rel_path,
                })

    def _scan_security_headers(self, result: dict):
        """Scan code for security header configuration."""
        found_headers = set()

        for ext_pattern in ["**/*.java", "**/*.py", "**/*.go", "**/*.js", "**/*.ts",
                           "**/*.rb", "**/*.php"]:
            for f in self.repo_path.rglob(ext_pattern):
                if self._should_skip(f):
                    continue
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                except (OSError, IOError):
                    continue

                rel_path = str(f.relative_to(self.repo_path))

                for pattern, header_name in SECURITY_HEADER_PATTERNS:
                    if header_name not in found_headers and pattern.search(content):
                        found_headers.add(header_name)
                        result["security_headers"].append({
                            "header": header_name,
                            "file": rel_path,
                        })

    def format_security_check(self, data: dict) -> str:
        """Format security check results as markdown (for security_check section)."""
        secrets = data.get("secret_findings", [])
        configs = data.get("security_configs", [])
        headers = data.get("security_headers", [])

        if not secrets and not configs and not headers:
            return ("*No security findings, security tool configs, or security headers detected.*\n\n"
                    "---\n*Generated by static analysis (ENABLE_AI=false)*")

        lines = []

        if secrets:
            lines.append("**Potential Hardcoded Secrets:**\n")
            lines.append("| Finding | File |")
            lines.append("|---------|------|")
            for s in sorted(secrets, key=lambda x: x["file"]):
                lines.append(f"| {s['type']} | `{s['file']}` |")
            lines.append("")
            lines.append("*Warning: Review these files for hardcoded credentials. "
                        "Use environment variables or a secrets manager instead.*")
            lines.append("")

        if configs:
            lines.append("**Security Tool Configurations:**\n")
            lines.append("| Tool | File |")
            lines.append("|------|------|")
            for c in sorted(configs, key=lambda x: x["tool"]):
                lines.append(f"| {c['tool']} | `{c['file']}` |")
            lines.append("")

        if headers:
            lines.append("**Security Headers Configured:**\n")
            lines.append("| Header | File |")
            lines.append("|--------|------|")
            for h in sorted(headers, key=lambda x: x["header"]):
                lines.append(f"| {h['header']} | `{h['file']}` |")
            lines.append("")

        lines.append("*Note: This is automated pattern detection. A full security audit requires manual review.*")
        lines.append("\n---")
        lines.append("*Generated by static analysis (ENABLE_AI=false)*")
        return "\n".join(lines)

    def format_authentication(self, data: dict) -> str:
        """Format authentication results as markdown (for authentication section)."""
        auth = data.get("auth_frameworks", [])
        k8s = [r for r in data.get("k8s_rbac", []) if r["type"] == "K8s ServiceAccount"]

        if not auth and not k8s:
            return ("*No authentication frameworks or configurations detected.*\n\n"
                    "---\n*Generated by static analysis (ENABLE_AI=false)*")

        lines = []

        if auth:
            lines.append("**Authentication Frameworks:**\n")
            lines.append("| Framework | Detected In |")
            lines.append("|-----------|------------|")
            for a in sorted(auth, key=lambda x: x["framework"]):
                lines.append(f"| {a['framework']} | `{a['file']}` |")
            lines.append("")

        if k8s:
            lines.append("**Kubernetes Service Accounts:**\n")
            for sa in sorted(k8s, key=lambda x: x["file"]):
                lines.append(f"- `{sa['file']}`")
            lines.append("")

        lines.append("\n---")
        lines.append("*Generated by static analysis (ENABLE_AI=false)*")
        return "\n".join(lines)

    def format_authorization(self, data: dict) -> str:
        """Format authorization results as markdown (for authorization section)."""
        k8s_rbac = [r for r in data.get("k8s_rbac", []) if r["type"] != "K8s ServiceAccount"]
        # Auth frameworks that imply authorization
        auth_authz = [a for a in data.get("auth_frameworks", [])
                      if a["framework"] in ("Spring Security", "Keycloak", "Auth0")]

        if not k8s_rbac and not auth_authz:
            return ("*No authorization/RBAC patterns detected.*\n\n"
                    "---\n*Generated by static analysis (ENABLE_AI=false)*")

        lines = []

        if k8s_rbac:
            lines.append("**Kubernetes RBAC Resources:**\n")
            lines.append("| Type | File |")
            lines.append("|------|------|")
            for r in sorted(k8s_rbac, key=lambda x: x["type"]):
                lines.append(f"| {r['type']} | `{r['file']}` |")
            lines.append("")

        if auth_authz:
            lines.append("**Authorization Frameworks:**\n")
            for a in sorted(auth_authz, key=lambda x: x["framework"]):
                lines.append(f"- **{a['framework']}** detected in `{a['file']}`")
            lines.append("")

        lines.append("\n---")
        lines.append("*Generated by static analysis (ENABLE_AI=false)*")
        return "\n".join(lines)
