"""
Unit tests for DatabaseScanner -- database detection from Terraform, Docker Compose,
connection strings, and application config files.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from investigator.core.static_analyzers.database_scanner import DatabaseScanner


class TestDatabaseScannerTerraform(unittest.TestCase):
    """Tests for Terraform database resource detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_rds_instance_detected(self):
        """RDS instance resources are detected."""
        self._write_file("db.tf", '''\
resource "aws_db_instance" "main" {
  engine         = "postgres"
  instance_class = "db.t3.micro"
}
''')
        scanner = DatabaseScanner(self.tmpdir)
        data = scanner.scan()
        tf_dbs = data["terraform_dbs"]
        self.assertEqual(len(tf_dbs), 1)
        self.assertEqual(tf_dbs[0]["type"], "aws_db_instance")
        self.assertEqual(tf_dbs[0]["name"], "main")
        self.assertEqual(tf_dbs[0]["engine"], "postgres")

    def test_dynamodb_table_detected(self):
        """DynamoDB table resources are detected."""
        self._write_file("dynamo.tf", '''\
resource "aws_dynamodb_table" "users" {
  name = "users"
  hash_key = "id"
}
''')
        scanner = DatabaseScanner(self.tmpdir)
        data = scanner.scan()
        tf_dbs = data["terraform_dbs"]
        self.assertEqual(len(tf_dbs), 1)
        self.assertEqual(tf_dbs[0]["type"], "aws_dynamodb_table")

    def test_elasticache_detected(self):
        """ElastiCache resources are detected."""
        self._write_file("cache.tf", '''\
resource "aws_elasticache_cluster" "redis" {
  engine = "redis"
  num_cache_nodes = 1
}
''')
        scanner = DatabaseScanner(self.tmpdir)
        data = scanner.scan()
        tf_dbs = data["terraform_dbs"]
        self.assertEqual(len(tf_dbs), 1)
        self.assertEqual(tf_dbs[0]["engine"], "redis")

    def test_multiple_db_resources(self):
        """Multiple database resources in one file are all detected."""
        self._write_file("main.tf", '''\
resource "aws_db_instance" "primary" {
  engine = "mysql"
}

resource "aws_elasticache_cluster" "cache" {
  engine = "redis"
}

resource "aws_dynamodb_table" "sessions" {
  name = "sessions"
}
''')
        scanner = DatabaseScanner(self.tmpdir)
        data = scanner.scan()
        self.assertEqual(len(data["terraform_dbs"]), 3)


class TestDatabaseScannerDockerCompose(unittest.TestCase):
    """Tests for Docker Compose database service detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_postgres_detected(self):
        """PostgreSQL image in docker-compose is detected."""
        self._write_file("docker-compose.yml", """\
version: '3'
services:
  db:
    image: postgres:15
    ports:
      - "5432:5432"
""")
        scanner = DatabaseScanner(self.tmpdir)
        data = scanner.scan()
        docker_dbs = data["docker_dbs"]
        self.assertTrue(len(docker_dbs) >= 1)
        types = {d["type"] for d in docker_dbs}
        self.assertIn("PostgreSQL", types)

    def test_redis_detected(self):
        """Redis image in docker-compose is detected."""
        self._write_file("docker-compose.yml", """\
version: '3'
services:
  cache:
    image: redis:7-alpine
""")
        scanner = DatabaseScanner(self.tmpdir)
        data = scanner.scan()
        types = {d["type"] for d in data["docker_dbs"]}
        self.assertIn("Redis", types)

    def test_multiple_dbs_in_compose(self):
        """Multiple database images in compose are detected."""
        self._write_file("docker-compose.yml", """\
version: '3'
services:
  db:
    image: postgres:15
  cache:
    image: redis:7
  mongo:
    image: mongo:6
""")
        scanner = DatabaseScanner(self.tmpdir)
        data = scanner.scan()
        types = {d["type"] for d in data["docker_dbs"]}
        self.assertIn("PostgreSQL", types)
        self.assertIn("Redis", types)
        self.assertIn("MongoDB", types)


class TestDatabaseScannerConnectionStrings(unittest.TestCase):
    """Tests for connection string detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_jdbc_postgresql(self):
        """JDBC PostgreSQL connection string is detected."""
        self._write_file("config.properties", """\
spring.datasource.url=jdbc:postgresql://localhost:5432/mydb
""")
        scanner = DatabaseScanner(self.tmpdir)
        data = scanner.scan()
        types = {cs["type"] for cs in data["connection_strings"]}
        self.assertIn("PostgreSQL", types)

    def test_jdbc_mysql(self):
        """JDBC MySQL connection string is detected."""
        self._write_file("app.yml", """\
datasource:
  url: jdbc:mysql://localhost:3306/mydb
""")
        scanner = DatabaseScanner(self.tmpdir)
        data = scanner.scan()
        types = {cs["type"] for cs in data["connection_strings"]}
        self.assertIn("MySQL", types)

    def test_mongodb_connection(self):
        """MongoDB connection string is detected."""
        self._write_file("config.json", '{"db": "mongodb://localhost:27017/mydb"}')
        scanner = DatabaseScanner(self.tmpdir)
        data = scanner.scan()
        types = {cs["type"] for cs in data["connection_strings"]}
        self.assertIn("MongoDB", types)

    def test_redis_connection(self):
        """Redis connection string is detected."""
        self._write_file("settings.toml", '[cache]\nurl = "redis://localhost:6379"')
        scanner = DatabaseScanner(self.tmpdir)
        data = scanner.scan()
        types = {cs["type"] for cs in data["connection_strings"]}
        self.assertIn("Redis", types)


class TestDatabaseScannerConfigFiles(unittest.TestCase):
    """Tests for Spring/application config file scanning."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_spring_datasource_postgresql(self):
        """Spring datasource config with PostgreSQL is detected."""
        self._write_file("src/main/resources/application.properties", """\
spring.datasource.url=jdbc:postgresql://db:5432/app
spring.datasource.driver-class-name=org.postgresql.Driver
""")
        scanner = DatabaseScanner(self.tmpdir)
        data = scanner.scan()
        self.assertTrue(len(data["config_dbs"]) >= 1)
        self.assertEqual(data["config_dbs"][0]["type"], "PostgreSQL")

    def test_spring_datasource_mysql(self):
        """Spring datasource config with MySQL is detected."""
        self._write_file("src/main/resources/application.properties", """\
spring.datasource.url=jdbc:mysql://localhost:3306/db
spring.datasource.driver-class-name=com.mysql.cj.jdbc.Driver
""")
        scanner = DatabaseScanner(self.tmpdir)
        data = scanner.scan()
        self.assertTrue(len(data["config_dbs"]) >= 1)
        self.assertEqual(data["config_dbs"][0]["type"], "MySQL")


class TestDatabaseScannerEdgeCases(unittest.TestCase):
    """Tests for edge cases."""

    def test_nonexistent_path(self):
        scanner = DatabaseScanner("/nonexistent/path/12345")
        data = scanner.scan()
        for key in data:
            self.assertEqual(data[key], [])

    def test_empty_repo(self):
        tmpdir = tempfile.mkdtemp()
        try:
            scanner = DatabaseScanner(tmpdir)
            data = scanner.scan()
            for key in data:
                self.assertEqual(data[key], [])
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_skip_dot_terraform(self):
        tmpdir = tempfile.mkdtemp()
        try:
            filepath = Path(tmpdir) / ".terraform" / "providers" / "db.tf"
            filepath.parent.mkdir(parents=True)
            filepath.write_text('resource "aws_db_instance" "x" { engine = "postgres" }')
            scanner = DatabaseScanner(tmpdir)
            data = scanner.scan()
            self.assertEqual(data["terraform_dbs"], [])
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestDatabaseScannerMarkdown(unittest.TestCase):
    """Tests for format_as_markdown() output."""

    def setUp(self):
        self.scanner = DatabaseScanner("/tmp/dummy")

    def test_empty_data(self):
        data = {"terraform_dbs": [], "docker_dbs": [], "connection_strings": [], "config_dbs": []}
        md = self.scanner.format_as_markdown(data)
        self.assertIn("No database resources", md)
        self.assertIn("ENABLE_AI=false", md)

    def test_terraform_dbs_table(self):
        data = {
            "terraform_dbs": [
                {"type": "aws_db_instance", "name": "main", "engine": "postgres", "file": "db.tf"},
            ],
            "docker_dbs": [],
            "connection_strings": [],
            "config_dbs": [],
        }
        md = self.scanner.format_as_markdown(data)
        self.assertIn("Database Resources (Terraform)", md)
        self.assertIn("aws_db_instance", md)
        self.assertIn("postgres", md)

    def test_docker_dbs_table(self):
        data = {
            "terraform_dbs": [],
            "docker_dbs": [{"type": "PostgreSQL", "source": "docker-compose", "file": "docker-compose.yml"}],
            "connection_strings": [],
            "config_dbs": [],
        }
        md = self.scanner.format_as_markdown(data)
        self.assertIn("Database Services (Docker Compose)", md)
        self.assertIn("PostgreSQL", md)


if __name__ == "__main__":
    unittest.main()
