"""
Unit tests for SecurityScanner -- hardcoded secret detection, auth framework
detection, K8s RBAC scanning, security tool configs, and security headers.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from investigator.core.static_analyzers.security_scanner import SecurityScanner


class TestSecurityScannerSecrets(unittest.TestCase):
    """Tests for hardcoded secret pattern detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_hardcoded_password_detected(self):
        """Hardcoded password assignment is detected."""
        self._write_file("config.py", 'password = "SuperSecret123!"\n')
        scanner = SecurityScanner(self.tmpdir)
        data = scanner.scan()
        types = {s["type"] for s in data["secret_findings"]}
        self.assertIn("Hardcoded password", types)

    def test_hardcoded_api_key_detected(self):
        """Hardcoded API key is detected."""
        self._write_file("settings.py", 'api_key = "abcdefghijklmnopqrstuvwxyz1234567890"\n')
        scanner = SecurityScanner(self.tmpdir)
        data = scanner.scan()
        types = {s["type"] for s in data["secret_findings"]}
        self.assertIn("Hardcoded API key", types)

    def test_aws_access_key_detected(self):
        """AWS access key ID pattern is detected."""
        self._write_file("deploy.sh", 'export AWS_KEY=AKIAIOSFODNN7EXAMPLE\n')
        scanner = SecurityScanner(self.tmpdir)
        data = scanner.scan()
        types = {s["type"] for s in data["secret_findings"]}
        self.assertIn("AWS Access Key ID", types)

    def test_github_token_detected(self):
        """GitHub token pattern is detected."""
        self._write_file("ci.yml", 'token: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnop\n')
        scanner = SecurityScanner(self.tmpdir)
        data = scanner.scan()
        types = {s["type"] for s in data["secret_findings"]}
        self.assertIn("GitHub Token", types)

    def test_private_key_detected(self):
        """Private key header is detected."""
        self._write_file("key.pem", '-----BEGIN RSA PRIVATE KEY-----\nMIIEpA...\n')
        scanner = SecurityScanner(self.tmpdir)
        data = scanner.scan()
        types = {s["type"] for s in data["secret_findings"]}
        self.assertIn("Private key file", types)

    def test_env_file_skipped(self):
        """Actual .env files are skipped (they're expected to have secrets)."""
        self._write_file(".env", 'password = "secret12345678"\n')
        scanner = SecurityScanner(self.tmpdir)
        data = scanner.scan()
        self.assertEqual(len(data["secret_findings"]), 0)

    def test_node_modules_skipped(self):
        """Files in node_modules are skipped."""
        self._write_file("node_modules/pkg/config.js",
                        'const api_key = "abcdefghijklmnopqrstuvwxyz1234567890";\n')
        scanner = SecurityScanner(self.tmpdir)
        data = scanner.scan()
        self.assertEqual(len(data["secret_findings"]), 0)


class TestSecurityScannerAuthFrameworks(unittest.TestCase):
    """Tests for authentication framework detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_spring_security_detected(self):
        """Spring Security import is detected."""
        self._write_file("src/SecurityConfig.java", """\
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
@EnableWebSecurity
public class SecurityConfig {}
""")
        scanner = SecurityScanner(self.tmpdir)
        data = scanner.scan()
        frameworks = {a["framework"] for a in data["auth_frameworks"]}
        self.assertIn("Spring Security", frameworks)

    def test_jwt_detected(self):
        """JWT library usage is detected."""
        self._write_file("auth.py", "import jwt\ntoken = jwt.decode(encoded, secret)\n")
        # jwt.decode is in the patterns
        scanner = SecurityScanner(self.tmpdir)
        data = scanner.scan()
        frameworks = {a["framework"] for a in data["auth_frameworks"]}
        self.assertIn("JWT", frameworks)

    def test_passport_js_detected(self):
        """Passport.js usage is detected."""
        self._write_file("app.js", 'const passport = require("passport");\n')
        scanner = SecurityScanner(self.tmpdir)
        data = scanner.scan()
        frameworks = {a["framework"] for a in data["auth_frameworks"]}
        self.assertIn("Passport.js", frameworks)

    def test_keycloak_detected(self):
        """Keycloak config is detected."""
        self._write_file("application.yml", "keycloak:\n  realm: myrealm\n  auth-server-url: http://localhost\n")
        scanner = SecurityScanner(self.tmpdir)
        data = scanner.scan()
        frameworks = {a["framework"] for a in data["auth_frameworks"]}
        self.assertIn("Keycloak", frameworks)

    def test_oauth2_detected(self):
        """OAuth2 configuration is detected."""
        self._write_file("application.properties",
                        "spring.security.oauth2.client.registration.google.client-id=xxx\n")
        scanner = SecurityScanner(self.tmpdir)
        data = scanner.scan()
        frameworks = {a["framework"] for a in data["auth_frameworks"]}
        self.assertIn("OAuth2/OIDC", frameworks)

    def test_auth0_detected(self):
        """Auth0 SDK usage is detected."""
        self._write_file("auth.ts", 'import { Auth0Client } from "@auth0/auth0-spa-js";\n')
        scanner = SecurityScanner(self.tmpdir)
        data = scanner.scan()
        frameworks = {a["framework"] for a in data["auth_frameworks"]}
        self.assertIn("Auth0", frameworks)

    def test_multiple_frameworks_detected(self):
        """Multiple auth frameworks in the same repo are all detected."""
        self._write_file("SecurityConfig.java",
                        "import org.springframework.security.config.annotation.web.builders.HttpSecurity;\n")
        self._write_file("auth.js", 'const passport = require("passport");\n')
        scanner = SecurityScanner(self.tmpdir)
        data = scanner.scan()
        frameworks = {a["framework"] for a in data["auth_frameworks"]}
        self.assertIn("Spring Security", frameworks)
        self.assertIn("Passport.js", frameworks)


class TestSecurityScannerK8sRBAC(unittest.TestCase):
    """Tests for Kubernetes RBAC resource detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_role_detected(self):
        """K8s Role manifest is detected."""
        self._write_file("k8s/role.yaml", """\
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: pod-reader
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list"]
""")
        scanner = SecurityScanner(self.tmpdir)
        data = scanner.scan()
        types = {r["type"] for r in data["k8s_rbac"]}
        self.assertIn("K8s RBAC", types)

    def test_cluster_role_binding_detected(self):
        """K8s ClusterRoleBinding is detected."""
        self._write_file("rbac.yml", """\
kind: ClusterRoleBinding
metadata:
  name: admin-binding
""")
        scanner = SecurityScanner(self.tmpdir)
        data = scanner.scan()
        types = {r["type"] for r in data["k8s_rbac"]}
        self.assertIn("K8s RBAC", types)

    def test_service_account_detected(self):
        """K8s ServiceAccount is detected."""
        self._write_file("sa.yaml", "kind: ServiceAccount\nmetadata:\n  name: my-sa\n")
        scanner = SecurityScanner(self.tmpdir)
        data = scanner.scan()
        types = {r["type"] for r in data["k8s_rbac"]}
        self.assertIn("K8s ServiceAccount", types)

    def test_network_policy_detected(self):
        """K8s NetworkPolicy is detected."""
        self._write_file("netpol.yaml", "kind: NetworkPolicy\nmetadata:\n  name: deny-all\n")
        scanner = SecurityScanner(self.tmpdir)
        data = scanner.scan()
        types = {r["type"] for r in data["k8s_rbac"]}
        self.assertIn("K8s NetworkPolicy", types)


class TestSecurityScannerConfigs(unittest.TestCase):
    """Tests for security tool config file detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content=""):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_snyk_config_detected(self):
        self._write_file(".snyk", "ignore: {}")
        scanner = SecurityScanner(self.tmpdir)
        data = scanner.scan()
        tools = {c["tool"] for c in data["security_configs"]}
        self.assertIn("Snyk", tools)

    def test_dependabot_detected(self):
        self._write_file(".github/dependabot.yml", "version: 2\n")
        scanner = SecurityScanner(self.tmpdir)
        data = scanner.scan()
        tools = {c["tool"] for c in data["security_configs"]}
        self.assertIn("Dependabot", tools)

    def test_security_md_detected(self):
        self._write_file("SECURITY.md", "# Security Policy\n")
        scanner = SecurityScanner(self.tmpdir)
        data = scanner.scan()
        tools = {c["tool"] for c in data["security_configs"]}
        self.assertIn("Security Policy", tools)

    def test_sonarqube_detected(self):
        self._write_file("sonar-project.properties", "sonar.projectKey=myapp\n")
        scanner = SecurityScanner(self.tmpdir)
        data = scanner.scan()
        tools = {c["tool"] for c in data["security_configs"]}
        self.assertIn("SonarQube", tools)


class TestSecurityScannerHeaders(unittest.TestCase):
    """Tests for security header detection in code."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_hsts_header_detected(self):
        self._write_file("security.py",
                        'response.headers["Strict-Transport-Security"] = "max-age=31536000"\n')
        scanner = SecurityScanner(self.tmpdir)
        data = scanner.scan()
        headers = {h["header"] for h in data["security_headers"]}
        self.assertIn("HSTS", headers)

    def test_csp_header_detected(self):
        self._write_file("middleware.js",
                        'res.setHeader("Content-Security-Policy", "default-src self");\n')
        scanner = SecurityScanner(self.tmpdir)
        data = scanner.scan()
        headers = {h["header"] for h in data["security_headers"]}
        self.assertIn("CSP", headers)

    def test_x_frame_options_detected(self):
        self._write_file("config.java",
                        'response.addHeader("X-Frame-Options", "DENY");\n')
        scanner = SecurityScanner(self.tmpdir)
        data = scanner.scan()
        headers = {h["header"] for h in data["security_headers"]}
        self.assertIn("X-Frame-Options", headers)


class TestSecurityScannerEdgeCases(unittest.TestCase):
    """Tests for edge cases."""

    def test_nonexistent_path(self):
        scanner = SecurityScanner("/nonexistent/path/12345")
        data = scanner.scan()
        for key in data:
            self.assertEqual(data[key], [])

    def test_empty_repo(self):
        tmpdir = tempfile.mkdtemp()
        try:
            scanner = SecurityScanner(tmpdir)
            data = scanner.scan()
            for key in data:
                self.assertEqual(data[key], [])
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestSecurityScannerMarkdown(unittest.TestCase):
    """Tests for markdown formatting methods."""

    def setUp(self):
        self.scanner = SecurityScanner("/tmp/dummy")

    def test_security_check_empty(self):
        data = {"secret_findings": [], "security_configs": [], "security_headers": []}
        md = self.scanner.format_security_check(data)
        self.assertIn("No security findings", md)
        self.assertIn("ENABLE_AI=false", md)

    def test_security_check_with_secrets(self):
        data = {
            "secret_findings": [{"type": "Hardcoded password", "file": "config.py"}],
            "security_configs": [],
            "security_headers": [],
        }
        md = self.scanner.format_security_check(data)
        self.assertIn("Hardcoded Secrets", md)
        self.assertIn("config.py", md)

    def test_authentication_empty(self):
        data = {"auth_frameworks": [], "k8s_rbac": []}
        md = self.scanner.format_authentication(data)
        self.assertIn("No authentication", md)

    def test_authentication_with_frameworks(self):
        data = {
            "auth_frameworks": [{"framework": "Spring Security", "file": "SecurityConfig.java"}],
            "k8s_rbac": [],
        }
        md = self.scanner.format_authentication(data)
        self.assertIn("Spring Security", md)

    def test_authorization_empty(self):
        data = {"k8s_rbac": [], "auth_frameworks": []}
        md = self.scanner.format_authorization(data)
        self.assertIn("No authorization", md)

    def test_authorization_with_rbac(self):
        data = {
            "k8s_rbac": [{"type": "K8s RBAC", "file": "role.yaml"}],
            "auth_frameworks": [],
        }
        md = self.scanner.format_authorization(data)
        self.assertIn("K8s RBAC", md)


if __name__ == "__main__":
    unittest.main()
