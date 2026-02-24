"""
Unit tests for DataMappingScanner -- PII field detection in entity definitions,
database schemas, and configuration files.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from investigator.core.static_analyzers.data_mapping_scanner import DataMappingScanner


class TestDataMappingScannerEntityFiles(unittest.TestCase):
    """Tests for PII detection in entity/model source files."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_email_field_detected(self):
        """Email fields in Python models are detected."""
        self._write_file("models.py", """\
class User:
    email = Column(String)
    name = Column(String)
""")
        scanner = DataMappingScanner(self.tmpdir)
        data = scanner.scan()
        pii_types = {p["pii_type"] for p in data["pii_fields"]}
        self.assertIn("Email", pii_types)

    def test_phone_field_detected(self):
        """Phone number fields are detected."""
        self._write_file("user.py", """\
class Contact:
    phone_number = CharField()
    address = TextField()
""")
        scanner = DataMappingScanner(self.tmpdir)
        data = scanner.scan()
        pii_types = {p["pii_type"] for p in data["pii_fields"]}
        self.assertIn("Phone", pii_types)

    def test_java_entity_pii_detected(self):
        """PII fields in Java entities are detected."""
        self._write_file("src/User.java", """\
@Entity
public class User {
    private String email;
    private String ssn;
    private String first_name;
    private String last_name;
}
""")
        scanner = DataMappingScanner(self.tmpdir)
        data = scanner.scan()
        pii_types = {p["pii_type"] for p in data["pii_fields"]}
        self.assertIn("Email", pii_types)
        self.assertIn("National ID", pii_types)
        self.assertIn("Name", pii_types)

    def test_go_struct_pii_detected(self):
        """PII fields in Go structs are detected."""
        self._write_file("models/user.go", """\
type User struct {
    Email       string
    DateOfBirth time.Time
    Password    string
}
""")
        scanner = DataMappingScanner(self.tmpdir)
        data = scanner.scan()
        pii_types = {p["pii_type"] for p in data["pii_fields"]}
        self.assertIn("Credential", pii_types)

    def test_typescript_model_pii(self):
        """PII fields in TypeScript interfaces are detected."""
        self._write_file("src/types.ts", """\
interface UserProfile {
    email: string;
    phone: string;
    credit_card: string;
    ip_address: string;
}
""")
        scanner = DataMappingScanner(self.tmpdir)
        data = scanner.scan()
        pii_types = {p["pii_type"] for p in data["pii_fields"]}
        self.assertIn("Email", pii_types)
        self.assertIn("Phone", pii_types)
        self.assertIn("Credit Card", pii_types)
        self.assertIn("IP Address", pii_types)

    def test_multiple_pii_types_per_file(self):
        """A file with multiple PII types reports all types."""
        self._write_file("patient.py", """\
class Patient:
    email = Field()
    phone = Field()
    ssn = Field()
    medical = Field()
    salary = Field()
""")
        scanner = DataMappingScanner(self.tmpdir)
        data = scanner.scan()
        pii_types = {p["pii_type"] for p in data["pii_fields"]}
        self.assertTrue(len(pii_types) >= 4)

    def test_sensitive_files_tracked(self):
        """Files with PII are tracked in sensitive_files."""
        self._write_file("user.py", "email = Column(String)\n")
        scanner = DataMappingScanner(self.tmpdir)
        data = scanner.scan()
        self.assertTrue(len(data["sensitive_files"]) >= 1)
        self.assertEqual(data["sensitive_files"][0]["file"], "user.py")


class TestDataMappingScannerSchemaFiles(unittest.TestCase):
    """Tests for PII detection in SQL schema and migration files."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_sql_schema_pii_detected(self):
        """PII columns in SQL CREATE TABLE are detected."""
        self._write_file("schema.sql", """\
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    phone_number VARCHAR(20),
    date_of_birth DATE,
    ssn VARCHAR(11)
);
""")
        scanner = DataMappingScanner(self.tmpdir)
        data = scanner.scan()
        pii_types = {p["pii_type"] for p in data["pii_fields"]}
        self.assertIn("Email", pii_types)
        self.assertIn("Phone", pii_types)
        self.assertIn("Date of Birth", pii_types)
        self.assertIn("National ID", pii_types)

    def test_migration_file_pii_detected(self):
        """PII in migration files is detected."""
        self._write_file("migrations/001_create_users.sql", """\
ALTER TABLE users ADD COLUMN passport_number VARCHAR(20);
ALTER TABLE users ADD COLUMN home_address TEXT;
""")
        scanner = DataMappingScanner(self.tmpdir)
        data = scanner.scan()
        pii_types = {p["pii_type"] for p in data["pii_fields"]}
        self.assertIn("Passport", pii_types)
        self.assertIn("Address", pii_types)


class TestDataMappingScannerEdgeCases(unittest.TestCase):
    """Tests for edge cases."""

    def test_nonexistent_path(self):
        scanner = DataMappingScanner("/nonexistent/path/12345")
        data = scanner.scan()
        self.assertEqual(data["pii_fields"], [])
        self.assertEqual(data["sensitive_files"], [])

    def test_empty_repo(self):
        tmpdir = tempfile.mkdtemp()
        try:
            scanner = DataMappingScanner(tmpdir)
            data = scanner.scan()
            self.assertEqual(data["pii_fields"], [])
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_skip_test_directories(self):
        """Files in test directories are skipped."""
        tmpdir = tempfile.mkdtemp()
        try:
            filepath = Path(tmpdir) / "tests" / "test_user.py"
            filepath.parent.mkdir(parents=True)
            filepath.write_text("email = 'test@example.com'\nssn = '123-45-6789'\n")
            scanner = DataMappingScanner(tmpdir)
            data = scanner.scan()
            self.assertEqual(data["pii_fields"], [])
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_skip_node_modules(self):
        """Files in node_modules are skipped."""
        tmpdir = tempfile.mkdtemp()
        try:
            filepath = Path(tmpdir) / "node_modules" / "pkg" / "model.js"
            filepath.parent.mkdir(parents=True)
            filepath.write_text("const email = 'user@test.com';\n")
            scanner = DataMappingScanner(tmpdir)
            data = scanner.scan()
            self.assertEqual(data["pii_fields"], [])
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_deduplication(self):
        """Duplicate PII field entries are deduplicated."""
        tmpdir = tempfile.mkdtemp()
        try:
            # Write a file that matches both entity and schema patterns
            filepath = Path(tmpdir) / "models.py"
            filepath.write_text("email = Field()\nemail_address = Field()\n")
            scanner = DataMappingScanner(tmpdir)
            data = scanner.scan()
            # Should not have duplicates for same type in same file
            email_entries = [p for p in data["pii_fields"]
                          if p["pii_type"] == "Email" and p["file"] == "models.py"]
            # May have 1 or 2 entries (email vs email_address are distinct fields)
            # but should not have exact duplicates
            seen = set()
            for entry in email_entries:
                key = (entry["pii_type"], entry["field"], entry["file"])
                self.assertNotIn(key, seen, f"Duplicate entry: {entry}")
                seen.add(key)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestDataMappingScannerMarkdown(unittest.TestCase):
    """Tests for format_as_markdown() output."""

    def setUp(self):
        self.scanner = DataMappingScanner("/tmp/dummy")

    def test_empty_data(self):
        data = {"pii_fields": [], "sensitive_files": []}
        md = self.scanner.format_as_markdown(data)
        self.assertIn("No PII fields", md)
        self.assertIn("ENABLE_AI=false", md)

    def test_sensitive_files_table(self):
        data = {
            "pii_fields": [{"pii_type": "Email", "field": "email", "file": "user.py"}],
            "sensitive_files": [{"file": "user.py", "pii_types": ["Email"], "count": 1}],
        }
        md = self.scanner.format_as_markdown(data)
        self.assertIn("Files with Sensitive Data Fields", md)
        self.assertIn("user.py", md)

    def test_pii_fields_table(self):
        data = {
            "pii_fields": [
                {"pii_type": "Email", "field": "email", "file": "user.py"},
                {"pii_type": "Phone", "field": "phone", "file": "user.py"},
            ],
            "sensitive_files": [],
        }
        md = self.scanner.format_as_markdown(data)
        self.assertIn("PII Field Detections", md)
        self.assertIn("Email", md)
        self.assertIn("Phone", md)

    def test_total_count_shown(self):
        data = {
            "pii_fields": [
                {"pii_type": "Email", "field": "email", "file": "a.py"},
                {"pii_type": "Phone", "field": "phone", "file": "b.py"},
                {"pii_type": "Name", "field": "first_name", "file": "c.py"},
            ],
            "sensitive_files": [],
        }
        md = self.scanner.format_as_markdown(data)
        self.assertIn("Total PII Fields Detected:** 3", md)


if __name__ == "__main__":
    unittest.main()
