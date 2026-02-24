"""
Unit tests for FeatureFlagScanner -- detection of feature flag frameworks,
configuration files, and usage patterns in code.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from investigator.core.static_analyzers.feature_flag_scanner import FeatureFlagScanner


class TestFeatureFlagScannerImports(unittest.TestCase):
    """Tests for SDK import detection across languages."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_python_launchdarkly_import(self):
        """Python LaunchDarkly import is detected."""
        self._write_file("app.py", "import ldclient\nclient = ldclient.get()\n")
        scanner = FeatureFlagScanner(self.tmpdir)
        data = scanner.scan()
        frameworks = {f["framework"] for f in data["frameworks"]}
        self.assertIn("LaunchDarkly", frameworks)

    def test_python_unleash_from_import(self):
        """Python Unleash 'from' import is detected."""
        self._write_file("flags.py", "from unleash_client import UnleashClient\n")
        scanner = FeatureFlagScanner(self.tmpdir)
        data = scanner.scan()
        frameworks = {f["framework"] for f in data["frameworks"]}
        self.assertIn("Unleash", frameworks)

    def test_python_openfeature_import(self):
        """Python OpenFeature import is detected."""
        self._write_file("feature.py", "from openfeature import api\n")
        scanner = FeatureFlagScanner(self.tmpdir)
        data = scanner.scan()
        frameworks = {f["framework"] for f in data["frameworks"]}
        self.assertIn("OpenFeature", frameworks)

    def test_java_launchdarkly_import(self):
        """Java LaunchDarkly import is detected."""
        self._write_file("src/Main.java", """\
import com.launchdarkly.sdk.server.LDClient;

public class Main {
    LDClient client;
}
""")
        scanner = FeatureFlagScanner(self.tmpdir)
        data = scanner.scan()
        frameworks = {f["framework"] for f in data["frameworks"]}
        self.assertIn("LaunchDarkly", frameworks)

    def test_java_togglz_import(self):
        """Java Togglz import is detected."""
        self._write_file("src/Config.java", """\
import org.togglz.core.Feature;
""")
        scanner = FeatureFlagScanner(self.tmpdir)
        data = scanner.scan()
        frameworks = {f["framework"] for f in data["frameworks"]}
        self.assertIn("Togglz", frameworks)

    def test_go_launchdarkly_import(self):
        """Go LaunchDarkly import is detected."""
        self._write_file("main.go", """\
package main

import (
    "github.com/launchdarkly/go-server-sdk/v6"
)
""")
        scanner = FeatureFlagScanner(self.tmpdir)
        data = scanner.scan()
        frameworks = {f["framework"] for f in data["frameworks"]}
        self.assertIn("LaunchDarkly", frameworks)

    def test_javascript_unleash_import(self):
        """JavaScript Unleash import is detected."""
        self._write_file("src/flags.js", """\
const { UnleashClient } = require('@unleash/proxy-client');
""")
        scanner = FeatureFlagScanner(self.tmpdir)
        data = scanner.scan()
        frameworks = {f["framework"] for f in data["frameworks"]}
        self.assertIn("Unleash", frameworks)

    def test_typescript_openfeature_import(self):
        """TypeScript OpenFeature import is detected."""
        self._write_file("src/flags.ts", """\
import { OpenFeature } from '@openfeature/server-sdk';
""")
        scanner = FeatureFlagScanner(self.tmpdir)
        data = scanner.scan()
        frameworks = {f["framework"] for f in data["frameworks"]}
        self.assertIn("OpenFeature", frameworks)

    def test_multiple_frameworks_detected(self):
        """Multiple frameworks across languages are all detected."""
        self._write_file("app.py", "import ldclient\n")
        self._write_file("main.go", '"github.com/Unleash/unleash-client-go/v3"\n')
        scanner = FeatureFlagScanner(self.tmpdir)
        data = scanner.scan()
        frameworks = {f["framework"] for f in data["frameworks"]}
        self.assertIn("LaunchDarkly", frameworks)
        self.assertIn("Unleash", frameworks)


class TestFeatureFlagScannerConfigFiles(unittest.TestCase):
    """Tests for feature flag config file detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content=""):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_unleash_yml_detected(self):
        """unleash.yml is detected as Unleash config."""
        self._write_file("unleash.yml", "version: 1\n")
        scanner = FeatureFlagScanner(self.tmpdir)
        data = scanner.scan()
        tools = {c["tool"] for c in data["config_files"]}
        self.assertIn("Unleash", tools)

    def test_flags_json_detected(self):
        """flags.json is detected as Custom config."""
        self._write_file("flags.json", '{"flags": []}')
        scanner = FeatureFlagScanner(self.tmpdir)
        data = scanner.scan()
        tools = {c["tool"] for c in data["config_files"]}
        self.assertIn("Custom", tools)

    def test_feature_flags_yaml_detected(self):
        """feature-flags.yaml is detected."""
        self._write_file("feature-flags.yaml", "flags:\n  - enabled: true\n")
        scanner = FeatureFlagScanner(self.tmpdir)
        data = scanner.scan()
        self.assertTrue(len(data["config_files"]) >= 1)

    def test_nested_config_detected(self):
        """Config files in subdirectories are found."""
        self._write_file("config/flags.yml", "flags: []\n")
        scanner = FeatureFlagScanner(self.tmpdir)
        data = scanner.scan()
        self.assertTrue(len(data["config_files"]) >= 1)

    def test_config_in_node_modules_skipped(self):
        """Config files in node_modules are skipped."""
        self._write_file("node_modules/pkg/flags.json", '{}')
        scanner = FeatureFlagScanner(self.tmpdir)
        data = scanner.scan()
        self.assertEqual(len(data["config_files"]), 0)


class TestFeatureFlagScannerUsagePatterns(unittest.TestCase):
    """Tests for code usage pattern detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_feature_flag_reference(self):
        """Generic 'feature_flag' reference in code is detected."""
        self._write_file("app.py", 'config = {"feature_flag_enabled": True}\n')
        scanner = FeatureFlagScanner(self.tmpdir)
        data = scanner.scan()
        types = {u["type"] for u in data["usage_patterns"]}
        self.assertIn("Feature flag reference", types)

    def test_is_enabled_call(self):
        """is_enabled('flag_name') pattern is detected."""
        self._write_file("service.py", 'if client.is_enabled("dark-mode"):\n    pass\n')
        scanner = FeatureFlagScanner(self.tmpdir)
        data = scanner.scan()
        types = {u["type"] for u in data["usage_patterns"]}
        self.assertIn("Feature check", types)

    def test_feature_constant(self):
        """FEATURE_* constant assignment is detected."""
        self._write_file("config.py", 'FEATURE_DARK_MODE = True\nFEATURE_NEW_UI = False\n')
        scanner = FeatureFlagScanner(self.tmpdir)
        data = scanner.scan()
        types = {u["type"] for u in data["usage_patterns"]}
        self.assertIn("Feature constant", types)

    def test_toggle_call(self):
        """toggle('flag_name') pattern is detected."""
        self._write_file("toggler.js", 'const val = toggle("new-checkout");\n')
        scanner = FeatureFlagScanner(self.tmpdir)
        data = scanner.scan()
        types = {u["type"] for u in data["usage_patterns"]}
        self.assertIn("Toggle call", types)

    def test_one_match_per_file(self):
        """Only one usage pattern is reported per file."""
        self._write_file("multi.py", """\
FEATURE_A = True
FEATURE_B = False
feature_flag_check()
is_enabled("x")
""")
        scanner = FeatureFlagScanner(self.tmpdir)
        data = scanner.scan()
        files = [u["file"] for u in data["usage_patterns"]]
        self.assertEqual(len(files), len(set(files)), "Should have at most one match per file")


class TestFeatureFlagScannerEdgeCases(unittest.TestCase):
    """Tests for edge cases."""

    def test_nonexistent_path(self):
        scanner = FeatureFlagScanner("/nonexistent/path/12345")
        data = scanner.scan()
        for key in data:
            self.assertEqual(data[key], [])

    def test_empty_repo(self):
        tmpdir = tempfile.mkdtemp()
        try:
            scanner = FeatureFlagScanner(tmpdir)
            data = scanner.scan()
            for key in data:
                self.assertEqual(data[key], [])
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_skip_vendor_dir(self):
        tmpdir = tempfile.mkdtemp()
        try:
            filepath = Path(tmpdir) / "vendor" / "pkg" / "flags.go"
            filepath.parent.mkdir(parents=True)
            filepath.write_text('"github.com/launchdarkly/go-server-sdk"')
            scanner = FeatureFlagScanner(tmpdir)
            data = scanner.scan()
            self.assertEqual(data["frameworks"], [])
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestFeatureFlagScannerMarkdown(unittest.TestCase):
    """Tests for format_as_markdown() output."""

    def setUp(self):
        self.scanner = FeatureFlagScanner("/tmp/dummy")

    def test_empty_data(self):
        data = {"frameworks": [], "config_files": [], "usage_patterns": []}
        md = self.scanner.format_as_markdown(data)
        self.assertIn("No feature flag frameworks", md)
        self.assertIn("ENABLE_AI=false", md)

    def test_frameworks_table(self):
        data = {
            "frameworks": [
                {"framework": "LaunchDarkly", "language": "python", "file": "app.py"},
            ],
            "config_files": [],
            "usage_patterns": [],
        }
        md = self.scanner.format_as_markdown(data)
        self.assertIn("Feature Flag Frameworks", md)
        self.assertIn("LaunchDarkly", md)
        self.assertIn("python", md)

    def test_config_files_table(self):
        data = {
            "frameworks": [],
            "config_files": [{"tool": "Custom", "file": "flags.json"}],
            "usage_patterns": [],
        }
        md = self.scanner.format_as_markdown(data)
        self.assertIn("Configuration Files", md)
        self.assertIn("flags.json", md)

    def test_usage_patterns_table(self):
        data = {
            "frameworks": [],
            "config_files": [],
            "usage_patterns": [{"type": "Feature check", "file": "service.py"}],
        }
        md = self.scanner.format_as_markdown(data)
        self.assertIn("Usage Patterns", md)
        self.assertIn("Feature check", md)

    def test_all_sections_present(self):
        data = {
            "frameworks": [
                {"framework": "Unleash", "language": "java", "file": "App.java"},
            ],
            "config_files": [{"tool": "Unleash", "file": "unleash.yml"}],
            "usage_patterns": [{"type": "Feature flag reference", "file": "cfg.java"}],
        }
        md = self.scanner.format_as_markdown(data)
        self.assertIn("Feature Flag Frameworks", md)
        self.assertIn("Configuration Files", md)
        self.assertIn("Usage Patterns", md)


if __name__ == "__main__":
    unittest.main()
