"""
Unit tests for EventDetector -- detection of event/messaging systems,
brokers, topics, and pub/sub patterns.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from investigator.core.static_analyzers.event_detector import EventDetector


class TestEventDetectorCodePatterns(unittest.TestCase):
    """Tests for event broker detection in source code."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_kafka_listener_java(self):
        """Java @KafkaListener annotation is detected."""
        self._write_file("src/Consumer.java", """\
import org.springframework.kafka.annotation.KafkaListener;

public class Consumer {
    @KafkaListener(topics = "orders")
    public void listen(String message) {}
}
""")
        detector = EventDetector(self.tmpdir)
        data = detector.scan()
        brokers = {b["broker"] for b in data["brokers"]}
        self.assertIn("Kafka", brokers)

    def test_kafka_python_import(self):
        """Python kafka import is detected."""
        self._write_file("producer.py", "from kafka import KafkaProducer\n")
        detector = EventDetector(self.tmpdir)
        data = detector.scan()
        brokers = {b["broker"] for b in data["brokers"]}
        self.assertIn("Kafka", brokers)

    def test_rabbitmq_java(self):
        """RabbitMQ @RabbitListener annotation is detected."""
        self._write_file("src/Listener.java", """\
import org.springframework.amqp.rabbit.annotation.RabbitListener;

@RabbitListener(queues = "tasks")
public class Listener {}
""")
        detector = EventDetector(self.tmpdir)
        data = detector.scan()
        brokers = {b["broker"] for b in data["brokers"]}
        self.assertIn("RabbitMQ", brokers)

    def test_sqs_python(self):
        """Python boto3 SQS client usage is detected."""
        self._write_file("worker.py", """\
import boto3
sqs = boto3.client('sqs')
sqs.send_message(QueueUrl=url, MessageBody='hello')
""")
        detector = EventDetector(self.tmpdir)
        data = detector.scan()
        brokers = {b["broker"] for b in data["brokers"]}
        self.assertIn("AWS SQS", brokers)

    def test_sns_python(self):
        """Python boto3 SNS client usage is detected."""
        self._write_file("notify.py", """\
import boto3
sns = boto3.client('sns')
sns.publish(TopicArn=arn, Message='alert')
""")
        detector = EventDetector(self.tmpdir)
        data = detector.scan()
        brokers = {b["broker"] for b in data["brokers"]}
        self.assertIn("AWS SNS", brokers)

    def test_nats_go(self):
        """Go NATS client usage is detected."""
        self._write_file("main.go", """\
package main
import "github.com/nats-io/nats.go"
func main() { nc, _ := nats.Connect("localhost") }
""")
        detector = EventDetector(self.tmpdir)
        data = detector.scan()
        brokers = {b["broker"] for b in data["brokers"]}
        self.assertIn("NATS", brokers)

    def test_google_pubsub_python(self):
        """Google Pub/Sub Python client is detected."""
        self._write_file("publisher.py", """\
from google.cloud.pubsub import PublisherClient
""")
        detector = EventDetector(self.tmpdir)
        data = detector.scan()
        brokers = {b["broker"] for b in data["brokers"]}
        self.assertIn("Google Pub/Sub", brokers)

    def test_multiple_brokers_detected(self):
        """Multiple brokers are all detected."""
        self._write_file("kafka_prod.py", "from kafka import KafkaProducer\n")
        self._write_file("rabbit.py", "import pika\npika.BlockingConnection()\n")
        detector = EventDetector(self.tmpdir)
        data = detector.scan()
        brokers = {b["broker"] for b in data["brokers"]}
        self.assertIn("Kafka", brokers)
        self.assertIn("RabbitMQ", brokers)


class TestEventDetectorConfigPatterns(unittest.TestCase):
    """Tests for broker config reference detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_spring_kafka_config(self):
        """spring.kafka config in application.yml is detected."""
        self._write_file("application.yml", """\
spring:
  kafka:
    bootstrap-servers: localhost:9092
""")
        detector = EventDetector(self.tmpdir)
        data = detector.scan()
        config_brokers = {c["broker"] for c in data["config_refs"]}
        self.assertIn("Kafka", config_brokers)

    def test_rabbitmq_amqp_url(self):
        """AMQP URL in config is detected as RabbitMQ."""
        self._write_file("config.yml", "rabbitmq:\n  url: amqp://guest:guest@localhost\n")
        detector = EventDetector(self.tmpdir)
        data = detector.scan()
        config_brokers = {c["broker"] for c in data["config_refs"]}
        self.assertIn("RabbitMQ", config_brokers)

    def test_sqs_env_var(self):
        """SQS_QUEUE_URL in env config is detected."""
        self._write_file(".env.example", "SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/xxx/myqueue\n")
        detector = EventDetector(self.tmpdir)
        data = detector.scan()
        config_brokers = {c["broker"] for c in data["config_refs"]}
        self.assertIn("AWS SQS", config_brokers)

    def test_redis_config(self):
        """Redis URL in config is detected."""
        self._write_file("config.properties", "REDIS_URL=redis://localhost:6379\n")
        detector = EventDetector(self.tmpdir)
        data = detector.scan()
        config_brokers = {c["broker"] for c in data["config_refs"]}
        self.assertIn("Redis", config_brokers)


class TestEventDetectorTopics(unittest.TestCase):
    """Tests for topic/queue name extraction."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_kafka_listener_topic_extracted(self):
        """Topic name from @KafkaListener is extracted."""
        self._write_file("Consumer.java", '@KafkaListener(topics = "order-events")\n')
        detector = EventDetector(self.tmpdir)
        data = detector.scan()
        names = {t["name"] for t in data["topics"]}
        self.assertIn("order-events", names)

    def test_rabbit_listener_queue_extracted(self):
        """Queue name from @RabbitListener is extracted."""
        self._write_file("Worker.java", '@RabbitListener(queues = "task-queue")\n')
        detector = EventDetector(self.tmpdir)
        data = detector.scan()
        names = {t["name"] for t in data["topics"]}
        self.assertIn("task-queue", names)

    def test_topic_name_from_config(self):
        """Topic name from config properties is extracted."""
        self._write_file("application.properties", "topic-name=user-notifications\n")
        detector = EventDetector(self.tmpdir)
        data = detector.scan()
        names = {t["name"] for t in data["topics"]}
        self.assertIn("user-notifications", names)


class TestEventDetectorSchemas(unittest.TestCase):
    """Tests for event schema file detection."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_file(self, name, content=""):
        filepath = Path(self.tmpdir) / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")

    def test_avro_schema_detected(self):
        self._write_file("schemas/order.avsc", '{"type": "record", "name": "Order"}')
        detector = EventDetector(self.tmpdir)
        data = detector.scan()
        types = {s["type"] for s in data["schemas"]}
        self.assertIn("Avro", types)

    def test_protobuf_detected(self):
        self._write_file("proto/message.proto", 'syntax = "proto3";\nmessage Order {}\n')
        detector = EventDetector(self.tmpdir)
        data = detector.scan()
        types = {s["type"] for s in data["schemas"]}
        self.assertIn("Protobuf", types)

    def test_asyncapi_detected(self):
        self._write_file("asyncapi.yaml", "asyncapi: 2.0.0\ninfo:\n  title: My API\n")
        detector = EventDetector(self.tmpdir)
        data = detector.scan()
        types = {s["type"] for s in data["schemas"]}
        self.assertIn("AsyncAPI", types)


class TestEventDetectorEdgeCases(unittest.TestCase):
    """Tests for edge cases."""

    def test_nonexistent_path(self):
        detector = EventDetector("/nonexistent/path/12345")
        data = detector.scan()
        for key in data:
            self.assertEqual(data[key], [])

    def test_empty_repo(self):
        tmpdir = tempfile.mkdtemp()
        try:
            detector = EventDetector(tmpdir)
            data = detector.scan()
            for key in data:
                self.assertEqual(data[key], [])
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_vendor_dir_skipped(self):
        tmpdir = tempfile.mkdtemp()
        try:
            filepath = Path(tmpdir) / "vendor" / "kafka" / "client.go"
            filepath.parent.mkdir(parents=True)
            filepath.write_text('import "github.com/nats-io/nats.go"')
            detector = EventDetector(tmpdir)
            data = detector.scan()
            self.assertEqual(data["brokers"], [])
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestEventDetectorMarkdown(unittest.TestCase):
    """Tests for format_as_markdown() output."""

    def setUp(self):
        self.detector = EventDetector("/tmp/dummy")

    def test_empty_data(self):
        data = {"brokers": [], "topics": [], "config_refs": [], "schemas": []}
        md = self.detector.format_as_markdown(data)
        self.assertIn("No event/messaging", md)
        self.assertIn("ENABLE_AI=false", md)

    def test_brokers_table(self):
        data = {
            "brokers": [{"broker": "Kafka", "source": "code", "file": "prod.py"}],
            "topics": [],
            "config_refs": [],
            "schemas": [],
        }
        md = self.detector.format_as_markdown(data)
        self.assertIn("Kafka", md)
        self.assertIn("Broker Usage", md)

    def test_topics_table(self):
        data = {
            "brokers": [],
            "topics": [{"name": "orders", "type": "Kafka topic", "file": "consumer.java"}],
            "config_refs": [],
            "schemas": [],
        }
        md = self.detector.format_as_markdown(data)
        self.assertIn("Topics/Queues", md)
        self.assertIn("orders", md)

    def test_combined_view(self):
        data = {
            "brokers": [{"broker": "Kafka", "source": "code", "file": "prod.py"}],
            "topics": [],
            "config_refs": [{"broker": "Kafka", "file": "app.yml"}],
            "schemas": [],
        }
        md = self.detector.format_as_markdown(data)
        self.assertIn("Event/Messaging Systems Detected", md)
        self.assertIn("Kafka", md)


if __name__ == "__main__":
    unittest.main()
