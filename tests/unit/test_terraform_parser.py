"""
Unit tests for TerraformParser -- Terraform .tf file parsing for resources,
modules, variables, outputs, data sources, providers, and environments.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from investigator.core.static_analyzers.terraform_parser import (
    TerraformParser, AWS_SERVICE_CATEGORIES, OTHER_CATEGORIES,
)


class TestTerraformParserParsing(unittest.TestCase):
    """Tests for the parse() method with various Terraform constructs."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_tf(self, name, content):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_parse_resources(self):
        """Resources with type and name are extracted."""
        self._write_tf("main.tf", '''\
resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
}

resource "aws_subnet" "public" {
  vpc_id = aws_vpc.main.id
}
''')
        parser = TerraformParser(self.tmpdir)
        data = parser.parse()
        self.assertEqual(len(data["resources"]), 2)
        types = {r["type"] for r in data["resources"]}
        self.assertEqual(types, {"aws_vpc", "aws_subnet"})

    def test_parse_data_sources(self):
        """Data sources are extracted into data_sources list."""
        self._write_tf("data.tf", '''\
data "aws_ami" "latest" {
  most_recent = true
}
''')
        parser = TerraformParser(self.tmpdir)
        data = parser.parse()
        self.assertEqual(len(data["data_sources"]), 1)
        self.assertEqual(data["data_sources"][0]["type"], "aws_ami")
        self.assertEqual(data["data_sources"][0]["name"], "latest")

    def test_parse_modules(self):
        """Module blocks are extracted with source attribute."""
        self._write_tf("main.tf", '''\
module "vpc" {
  source = "./modules/vpc"
  cidr   = var.vpc_cidr
}

module "registry_mod" {
  source  = "hashicorp/consul/aws"
  version = "0.1.0"
}
''')
        parser = TerraformParser(self.tmpdir)
        data = parser.parse()
        self.assertEqual(len(data["modules"]), 2)
        names = {m["name"] for m in data["modules"]}
        self.assertEqual(names, {"vpc", "registry_mod"})
        vpc_mod = next(m for m in data["modules"] if m["name"] == "vpc")
        self.assertEqual(vpc_mod["source"], "./modules/vpc")
        self.assertEqual(vpc_mod["source_type"], "local")
        reg_mod = next(m for m in data["modules"] if m["name"] == "registry_mod")
        self.assertEqual(reg_mod["source_type"], "registry")

    def test_parse_variables(self):
        """Variable blocks extract name, description, and has_default."""
        self._write_tf("variables.tf", '''\
variable "region" {
  description = "AWS region"
  default     = "us-east-1"
}

variable "env" {
  description = "Environment name"
}
''')
        parser = TerraformParser(self.tmpdir)
        data = parser.parse()
        self.assertEqual(len(data["variables"]), 2)
        region_var = next(v for v in data["variables"] if v["name"] == "region")
        self.assertEqual(region_var["description"], "AWS region")
        self.assertTrue(region_var["has_default"])
        env_var = next(v for v in data["variables"] if v["name"] == "env")
        self.assertFalse(env_var["has_default"])

    def test_parse_outputs(self):
        """Output blocks are extracted."""
        self._write_tf("outputs.tf", '''\
output "vpc_id" {
  value = aws_vpc.main.id
}
''')
        parser = TerraformParser(self.tmpdir)
        data = parser.parse()
        self.assertEqual(len(data["outputs"]), 1)
        self.assertEqual(data["outputs"][0]["name"], "vpc_id")

    def test_parse_providers(self):
        """Provider blocks are extracted."""
        self._write_tf("providers.tf", '''\
provider "aws" {
  region = "us-east-1"
}

provider "kubernetes" {
  config_path = "~/.kube/config"
}
''')
        parser = TerraformParser(self.tmpdir)
        data = parser.parse()
        self.assertEqual(len(data["providers"]), 2)
        names = {p["name"] for p in data["providers"]}
        self.assertEqual(names, {"aws", "kubernetes"})

    def test_tfvars_files_detected(self):
        """.tfvars files are listed."""
        self._write_tf("prod.tfvars", 'region = "us-west-2"\n')
        self._write_tf("dev.tfvars", 'region = "us-east-1"\n')
        parser = TerraformParser(self.tmpdir)
        data = parser.parse()
        self.assertEqual(len(data["tfvars_files"]), 2)

    def test_skip_dot_terraform(self):
        """Files inside .terraform/ are skipped."""
        self._write_tf("main.tf", 'resource "aws_vpc" "main" { cidr_block = "10.0.0.0/16" }')
        self._write_tf(".terraform/providers/main.tf", 'resource "null_resource" "x" {}')
        parser = TerraformParser(self.tmpdir)
        data = parser.parse()
        self.assertEqual(len(data["resources"]), 1)
        self.assertEqual(data["resources"][0]["type"], "aws_vpc")

    def test_nonexistent_path(self):
        """Non-existent repo path returns empty result."""
        parser = TerraformParser("/nonexistent/path/12345")
        data = parser.parse()
        self.assertEqual(data["resources"], [])
        self.assertEqual(data["tf_files"], [])

    def test_empty_repo(self):
        """Empty directory returns empty result."""
        parser = TerraformParser(self.tmpdir)
        data = parser.parse()
        self.assertEqual(data["resources"], [])


class TestTerraformParserCategorization(unittest.TestCase):
    """Tests for resource type categorization."""

    def setUp(self):
        self.parser = TerraformParser("/tmp/dummy")

    def test_aws_vpc_is_networking(self):
        self.assertEqual(self.parser._categorize_resource("aws_vpc"), "Networking")

    def test_aws_subnet_is_networking(self):
        self.assertEqual(self.parser._categorize_resource("aws_subnet"), "Networking")

    def test_aws_instance_is_ec2(self):
        self.assertEqual(self.parser._categorize_resource("aws_instance"), "Compute/EC2")

    def test_aws_emr_cluster_is_emr(self):
        self.assertEqual(self.parser._categorize_resource("aws_emr_cluster"), "Compute/EMR")

    def test_aws_s3_bucket_is_storage(self):
        self.assertEqual(self.parser._categorize_resource("aws_s3_bucket"), "Storage/S3")

    def test_aws_dynamodb_table_is_database(self):
        self.assertEqual(self.parser._categorize_resource("aws_dynamodb_table"), "Database/DynamoDB")

    def test_aws_security_group_is_security(self):
        self.assertEqual(self.parser._categorize_resource("aws_security_group"), "Security")

    def test_azurerm_prefix_is_azure(self):
        self.assertEqual(self.parser._categorize_resource("azurerm_cosmosdb_account"), "Azure")

    def test_google_prefix_is_gcp(self):
        self.assertEqual(self.parser._categorize_resource("google_compute_instance"), "GCP")

    def test_null_resource_is_utility(self):
        self.assertEqual(self.parser._categorize_resource("null_resource"), "Utility")

    def test_unknown_resource_is_other(self):
        self.assertEqual(self.parser._categorize_resource("custom_unknown_thing"), "Other")


class TestTerraformParserModuleClassification(unittest.TestCase):
    """Tests for module source classification."""

    def setUp(self):
        self.parser = TerraformParser("/tmp/dummy")

    def test_local_source(self):
        self.assertEqual(self.parser._classify_module_source("./modules/vpc"), "local")

    def test_relative_parent_source(self):
        self.assertEqual(self.parser._classify_module_source("../shared/db"), "local")

    def test_github_source(self):
        self.assertEqual(self.parser._classify_module_source("github.com/hashicorp/consul"), "git")

    def test_git_prefix_source(self):
        self.assertEqual(self.parser._classify_module_source("git::https://example.com/mod.git"), "git")

    def test_s3_source(self):
        self.assertEqual(self.parser._classify_module_source("s3::https://bucket/mod.zip"), "s3")

    def test_registry_source(self):
        self.assertEqual(self.parser._classify_module_source("hashicorp/consul/aws"), "registry")

    def test_empty_source(self):
        self.assertEqual(self.parser._classify_module_source(""), "unknown")


class TestTerraformParserFormatResources(unittest.TestCase):
    """Tests for format_resources() markdown output."""

    def setUp(self):
        self.parser = TerraformParser("/tmp/dummy")

    def test_empty_resources(self):
        md = self.parser.format_resources({"resources": [], "data_sources": []})
        self.assertIn("No Terraform resources found", md)
        self.assertIn("ENABLE_AI=false", md)

    def test_resources_table_rendered(self):
        data = {
            "resources": [
                {"type": "aws_vpc", "name": "main", "category": "Networking", "file": "main.tf"},
            ],
            "data_sources": [],
        }
        md = self.parser.format_resources(data)
        self.assertIn("Infrastructure Resources", md)
        self.assertIn("| `aws_vpc` | main | Networking | main.tf |", md)
        self.assertIn("Total Resources:** 1", md)

    def test_data_sources_section(self):
        data = {
            "resources": [],
            "data_sources": [
                {"type": "aws_ami", "name": "latest", "category": "Other", "file": "data.tf"},
            ],
        }
        md = self.parser.format_resources(data)
        self.assertIn("Data Sources", md)
        self.assertIn("aws_ami", md)


class TestTerraformParserFormatEnvironments(unittest.TestCase):
    """Tests for format_environments() markdown output."""

    def setUp(self):
        self.parser = TerraformParser("/tmp/dummy")

    def test_infer_prod_env(self):
        self.assertIn("Prod", self.parser._infer_env_from_filename("prod.tfvars"))

    def test_infer_dev_env(self):
        self.assertIn("Dev", self.parser._infer_env_from_filename("dev.tfvars"))

    def test_infer_staging_env(self):
        self.assertIn("Staging", self.parser._infer_env_from_filename("staging.tfvars"))

    def test_infer_default_terraform(self):
        self.assertEqual(self.parser._infer_env_from_filename("terraform.tfvars"), "Default")

    def test_infer_custom_env(self):
        self.assertEqual(self.parser._infer_env_from_filename("myapp.tfvars"), "Custom")

    def test_env_related_variables_detected(self):
        self.assertTrue(self.parser._is_env_related_var("environment"))
        self.assertTrue(self.parser._is_env_related_var("aws_region"))
        self.assertTrue(self.parser._is_env_related_var("cluster_name"))
        self.assertFalse(self.parser._is_env_related_var("cidr_block"))
        self.assertFalse(self.parser._is_env_related_var("instance_type"))

    def test_format_with_tfvars(self):
        data = {
            "tfvars_files": ["prod.tfvars", "dev.tfvars"],
            "variables": [
                {"name": "environment", "description": "Env name", "has_default": False, "file": "vars.tf"},
            ],
        }
        md = self.parser.format_environments(data)
        self.assertIn("prod.tfvars", md)
        self.assertIn("dev.tfvars", md)
        self.assertIn("Environment-Related Variables", md)

    def test_format_no_tfvars(self):
        data = {"tfvars_files": [], "variables": []}
        md = self.parser.format_environments(data)
        self.assertIn("No .tfvars files found", md)


class TestTerraformParserFormatServiceDeps(unittest.TestCase):
    """Tests for format_service_dependencies() markdown output."""

    def setUp(self):
        self.parser = TerraformParser("/tmp/dummy")

    def test_empty_deps(self):
        data = {"modules": [], "providers": [], "outputs": [], "resources": [], "data_sources": []}
        md = self.parser.format_service_dependencies(data)
        self.assertIn("No module or provider dependencies found", md)

    def test_module_table(self):
        data = {
            "modules": [
                {"name": "vpc", "source": "./modules/vpc", "source_type": "local", "file": "main.tf"},
            ],
            "providers": [],
            "outputs": [],
            "resources": [],
            "data_sources": [],
        }
        md = self.parser.format_service_dependencies(data)
        self.assertIn("Module Dependencies", md)
        self.assertIn("vpc", md)
        self.assertIn("local", md)

    def test_remote_state_deps(self):
        data = {
            "modules": [],
            "providers": [{"name": "aws", "file": "main.tf"}],
            "outputs": [],
            "resources": [],
            "data_sources": [
                {"type": "terraform_remote_state", "name": "network", "category": "Other", "file": "data.tf"},
            ],
        }
        md = self.parser.format_service_dependencies(data)
        self.assertIn("Remote State Dependencies", md)
        self.assertIn("network", md)


if __name__ == "__main__":
    unittest.main()
