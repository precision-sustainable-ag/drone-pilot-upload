"""Read-only retry Slurm accounting and publication safeguard tests."""
import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
ORG = "11111111-1111-4111-8111-111111111111"
FLIGHT = "22222222-2222-4222-8222-222222222222"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


inspect = load("dpu_inspector_test", "scripts/inspect-odm-retry.py")


class RetryAccountingTest(unittest.TestCase):
    def products(self, attempt, names=("orthophoto", "vari", "gli")):
        for name in names:
            path = attempt / inspect.PRODUCTS[name]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"synthetic product")

    def publication(self, flight, attempt, sandbox="atlas", state="COMPLETED", exit_code="0:0"):
        with redirect_stdout(io.StringIO()) as output:
            result = inspect.review_publication(flight, attempt, sandbox, state, exit_code)
        return result, output.getvalue()

    def test_missing_ceres_indices_block_publication(self):
        with tempfile.TemporaryDirectory(prefix="dpu-ceres-review-") as tmp:
            flight = Path(tmp)
            attempt = flight / "odm-retries" / "retry-123456"
            self.products(attempt, ("orthophoto",))
            allowed, report = self.publication(flight, attempt, "ceres")
            self.assertFalse(allowed)
            self.assertIn("Ceres indices require isolated postprocessing", report)

    def test_existing_original_workspace_and_previews_block(self):
        with tempfile.TemporaryDirectory(prefix="dpu-preserve-") as tmp:
            flight = Path(tmp)
            attempt = flight / "odm-retries" / "retry-123456"
            self.products(attempt)
            (flight / "odm").mkdir()
            (flight / "previews").mkdir()
            allowed, report = self.publication(flight, attempt)
            self.assertFalse(allowed)
            self.assertIn("Existing odm must be archived", report)
            self.assertIn("Existing previews must be preserved", report)
            self.assertTrue((flight / "odm").is_dir())
            self.assertTrue((flight / "previews").is_dir())

    def test_successful_preliminary_review_only(self):
        with tempfile.TemporaryDirectory(prefix="dpu-review-") as tmp:
            flight = Path(tmp)
            attempt = flight / "odm-retries" / "retry-123456"
            self.products(attempt)
            allowed, report = self.publication(flight, attempt)
            self.assertTrue(allowed)
            self.assertIn("GeoTIFF validity and publication still require operator review", report)
            self.assertFalse((flight / "odm").exists())

    def test_failed_slurm_blocks_even_when_products_exist(self):
        with tempfile.TemporaryDirectory(prefix="dpu-state-review-") as tmp:
            flight = Path(tmp)
            attempt = flight / "odm-retries" / "retry-123456"
            self.products(attempt)
            allowed, report = self.publication(flight, attempt, state="OUT_OF_MEMORY", exit_code="1:0")
            self.assertFalse(allowed)
            self.assertIn("Retry Slurm job is not successful", report)

    def test_inspector_reads_retry_without_replacing_original_receipt(self):
        with tempfile.TemporaryDirectory(prefix="dpu-inspect-") as tmp:
            root = Path(tmp)
            flight = root / "site-id" / ORG / "flights" / FLIGHT
            attempt = flight / "odm-retries" / "retry-123456"
            attempt.mkdir(parents=True)
            original = {
                "organization_id": ORG, "flight_id": FLIGHT, "slurm_job_id": "123456"
            }
            retry_receipt = {
                "organization_id": ORG, "flight_id": FLIGHT,
                "previous_slurm_job_id": "123456", "retry_slurm_job_id": "654321",
                "retry_workspace": str(attempt),
            }
            original_path = flight / "odm-submission.submitted.json"
            original_path.write_text(json.dumps(original))
            (flight / "odm-retry-from-123456.submitted.json").write_text(
                json.dumps(retry_receipt)
            )
            self.products(attempt)
            response = SimpleNamespace(
                returncode=0, stderr="", stdout=(
                    "654321|COMPLETED|0:0|2026-11-20T10:00:00|"
                    "2026-11-20T10:05:00|gpu-a100|00:05:00|128G|\n"
                    "654321.batch|COMPLETED|0:0||||00:05:00||10000000K\n"
                ),
            )
            with patch.object(inspect.subprocess, "run", return_value=response) as sacct, \
                    redirect_stdout(io.StringIO()) as output:
                result = inspect.inspect_retry(root, FLIGHT, "123456", "atlas")
            self.assertEqual(result, 0)
            self.assertEqual(sacct.call_count, 1)
            report = output.getvalue()
            self.assertIn("elapsed=00:05:00", report)
            self.assertIn("requested=128G", report)
            self.assertIn("RETRY PRODUCTS READY", report)
            self.assertEqual(json.loads(original_path.read_text()), original)
            self.assertFalse((flight / "odm").exists())

    def test_missing_retry_receipt_rejected(self):
        with tempfile.TemporaryDirectory(prefix="dpu-no-retry-") as tmp:
            with self.assertRaisesRegex(ValueError, "exactly one submitted retry receipt"):
                inspect.inspect_retry(Path(tmp), FLIGHT, "123456", "atlas")


if __name__ == "__main__":
    unittest.main()
