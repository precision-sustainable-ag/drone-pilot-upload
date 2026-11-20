"""Fail-closed ODM retry planning and transaction tests (no live Slurm)."""
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
ORG = "11111111-1111-4111-8111-111111111111"
FLIGHT = "22222222-2222-4222-8222-222222222222"
OLD_JOB = "123456"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


retry = load("dpu_retry_test", "scripts/retry-odm.py")


class RetryTest(unittest.TestCase):
    def test_resource_failures_only(self):
        for state, accepted in (
            ("TIMEOUT", True), ("OUT_OF_MEMORY", True), ("COMPLETED", False),
            ("FAILED", False),
        ):
            with self.subTest(state=state), patch.object(
                retry.subprocess, "run",
                return_value=SimpleNamespace(returncode=0, stdout=f"{OLD_JOB}|{state}|1:0\n", stderr=""),
            ):
                if accepted:
                    self.assertEqual(retry.slurm_state(OLD_JOB), state)
                else:
                    with self.assertRaisesRegex(ValueError, "only TIMEOUT or OUT_OF_MEMORY"):
                        retry.slurm_state(OLD_JOB)

    def test_confirmation_required_before_side_effects(self):
        argv = [
            "retry-odm.py", "--data-root", "/not-a-real-data-root",
            "--repo", "/not-a-real-repo", "--sandbox", "atlas",
            "--flight-id", FLIGHT, "--failed-job-id", OLD_JOB,
            "--profile", "medium", "--submit",
        ]
        with patch.object(sys, "argv", argv), redirect_stderr(io.StringIO()) as errors:
            with self.assertRaises(SystemExit) as raised:
                retry.main()
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("--confirm-job-id", errors.getvalue())

    def test_marker_is_exclusive(self):
        with tempfile.TemporaryDirectory(prefix="dpu-marker-") as tmp:
            marker = Path(tmp) / "retry.submitting.json"
            retry.reserve_marker(marker, {"previous_slurm_job_id": OLD_JOB})
            original = marker.read_bytes()
            with self.assertRaises(FileExistsError):
                retry.reserve_marker(marker, {"previous_slurm_job_id": "other"})
            self.assertEqual(marker.read_bytes(), original)

    def setup_flight(self, root, with_inventory=True):
        folder = root / "site-id" / ORG / "flights" / FLIGHT
        images = folder / "images"
        images.mkdir(parents=True)
        (images / "a.jpg").write_bytes(b"abcd")
        (folder / "mongo-registration.done.json").write_text("{}")
        receipt = {
            "organization_id": ORG, "flight_id": FLIGHT,
            "slurm_job_id": OLD_JOB,
            "resource_profile": {"name": "small"},
        }
        if with_inventory:
            receipt["image_inventory"] = {"image_count": 1, "total_image_bytes": 4}
        (folder / retry.SUBMITTED).write_text(json.dumps(receipt))
        return folder

    def test_planning_both_clusters_is_read_only(self):
        for sandbox, walltime, gres in (
            ("atlas", "04:00:00", "gpu:a100:1"),
            ("ceres", "16:00:00", None),
        ):
            with self.subTest(sandbox=sandbox), tempfile.TemporaryDirectory(
                prefix="dpu-plan-"
            ) as tmp:
                data = Path(tmp)
                folder = self.setup_flight(data)
                original = (folder / retry.SUBMITTED).read_bytes()
                args = SimpleNamespace(
                    flight_id=FLIGHT, failed_job_id=OLD_JOB, sandbox=sandbox,
                    profile="medium", acknowledge_unverified_images=False,
                )
                with patch.object(retry, "slurm_state", return_value="TIMEOUT"):
                    planned_folder, submitting, submitted, command, record = (
                        retry.plan_retry(args, ROOT, data)
                    )
                self.assertEqual(planned_folder, folder)
                self.assertIn("processing_provenance", record)
                self.assertIn("version_hint", record["processing_provenance"]["odm_image"])
                self.assertIsNone(record["processing_provenance"]["odm_image"]["sha256"])
                self.assertEqual(record["requested_resources"]["memory"], "128G")
                self.assertEqual(record["requested_resources"]["walltime"], walltime)
                self.assertEqual(record["requested_resources"]["gres"], gres)
                self.assertEqual(command[-2:], ["--retry-from-job", OLD_JOB])
                self.assertFalse(submitting.exists())
                self.assertFalse(submitted.exists())
                self.assertFalse((folder / "odm-retries").exists())
                self.assertEqual((folder / retry.SUBMITTED).read_bytes(), original)

    def test_inventory_change_blocks_retry(self):
        with tempfile.TemporaryDirectory(prefix="dpu-integrity-") as tmp:
            root = Path(tmp)
            self.setup_flight(root)
            images = root / "site-id" / ORG / "flights" / FLIGHT / "images"
            (images / "extra.jpg").write_bytes(b"x")
            args = SimpleNamespace(
                flight_id=FLIGHT, failed_job_id=OLD_JOB, sandbox="atlas",
                profile="medium", acknowledge_unverified_images=False,
            )
            with patch.object(retry, "slurm_state") as slurm:
                with self.assertRaisesRegex(ValueError, "image count or bytes differ"):
                    retry.plan_retry(args, ROOT, root)
                slurm.assert_not_called()

    def fake_submission(self, folder, mode):
        original_path = folder / retry.SUBMITTED
        original_path.write_bytes(b'{"original": true}\n')
        before = original_path.read_bytes()
        submitting = folder / f"odm-retry-from-{OLD_JOB}.submitting.json"
        submitted = folder / f"odm-retry-from-{OLD_JOB}.submitted.json"
        record = {
            "previous_slurm_job_id": OLD_JOB, "previous_slurm_state": "TIMEOUT",
            "image_inventory": {"image_count": 1},
            "inventory_assurance": "synthetic test",
            "requested_resources": {"profile": "medium"},
            "retry_workspace": str(folder / "odm-retries" / f"retry-{OLD_JOB}"),
        }
        def plan(*_args):
            return folder, submitting, submitted, ["sbatch", "--parsable", "mock.sh"], dict(record)

        if mode == "success":
            response = SimpleNamespace(returncode=0, stdout="654321\n", stderr="")
        elif mode == "rejected":
            response = SimpleNamespace(returncode=1, stdout="", stderr="synthetic rejection")
        else:
            response = SimpleNamespace(returncode=0, stdout="ambiguous\n", stderr="")
        argv = [
            "retry-odm.py", "--data-root", str(folder.parent),
            "--repo", str(folder.parent), "--sandbox", "atlas",
            "--flight-id", FLIGHT, "--failed-job-id", OLD_JOB,
            "--profile", "medium", "--submit", "--confirm-job-id", OLD_JOB,
        ]
        with patch.object(sys, "argv", argv), patch.object(retry, "plan_retry", plan), \
                patch.object(retry.subprocess, "run", return_value=response), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            result = retry.main()
        self.assertEqual(original_path.read_bytes(), before)
        self.assertFalse((folder / "odm-retries").exists())
        return result, submitting, submitted

    def test_transaction_success_preserves_original(self):
        with tempfile.TemporaryDirectory(prefix="dpu-success-") as tmp:
            folder = Path(tmp) / "flight"
            folder.mkdir()
            result, submitting, submitted = self.fake_submission(folder, "success")
            self.assertEqual(result, 0)
            self.assertFalse(submitting.exists())
            receipt = json.loads(submitted.read_text())
            self.assertEqual(receipt["retry_slurm_job_id"], "654321")
            self.assertEqual(receipt["previous_slurm_job_id"], OLD_JOB)

    def test_transaction_failures_preserve_ambiguous_marker(self):
        for mode in ("rejected", "ambiguous"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(
                prefix="dpu-failure-"
            ) as tmp:
                folder = Path(tmp) / "flight"
                folder.mkdir()
                result, submitting, submitted = self.fake_submission(folder, mode)
                self.assertEqual(result, 1)
                self.assertTrue(submitting.is_file())
                self.assertFalse(submitted.exists())


if __name__ == "__main__":
    unittest.main()
