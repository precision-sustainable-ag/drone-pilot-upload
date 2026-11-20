"""Resource sizing and Slurm command regression tests (stdlib only)."""
import importlib.util
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


submit = load("dpu_submit_test", "scripts/submit-pending-odm.py")
provenance = load("dpu_provenance_test", "scripts/processing_provenance.py")


class ResourceProfilesTest(unittest.TestCase):
    def test_image_count_and_bytes_boundaries(self):
        gib = 1024 ** 3
        cases = (
            (100, 10 * gib, "small"),
            (101, 10 * gib, "medium"),
            (100, 10 * gib + 1, "medium"),
            (500, 50 * gib, "medium"),
            (501, 50 * gib, "large"),
            (500, 50 * gib + 1, "large"),
        )
        for sandbox in ("atlas", "ceres"):
            for count, size, expected in cases:
                with self.subTest(sandbox=sandbox, count=count, size=size):
                    profile, reason = submit.preview_resource_profile(
                        sandbox, {"image_count": count, "total_image_bytes": size}
                    )
                    self.assertEqual(profile["name"], expected)
                    self.assertIn("provisional", reason)

    def test_cluster_profiles(self):
        for sandbox, partition, gres, times in (
            ("atlas", "gpu-a100", "gpu:a100:1", ("01:00:00", "04:00:00", "12:00:00")),
            ("ceres", "ceres", None, ("08:00:00", "16:00:00", "48:00:00")),
        ):
            with self.subTest(sandbox=sandbox):
                profiles = submit.RESOURCE_PROFILES[sandbox]
                self.assertEqual([p["name"] for p in profiles], ["small", "medium", "large"])
                self.assertEqual([p["mem"] for p in profiles], ["64G", "128G", "256G"])
                self.assertEqual([p["time"] for p in profiles], list(times))
                self.assertTrue(all(p["partition"] == partition for p in profiles))
                self.assertTrue(all(p["gres"] == gres and p["cpus"] == 4 for p in profiles))

    def test_sbatch_profile_only_when_opted_in(self):
        job_script = Path("/fake/odm-atlas-flight.sh")
        flight = Path("/fake/flight")
        profile = submit.RESOURCE_PROFILES["atlas"][1]
        for chosen in (None, profile):
            with self.subTest(profile=chosen is not None):
                cmd = submit.build_sbatch_command(
                    job_script, flight, "org", "flight", "gpu-a100", "gpu:a100:1", chosen
                )
                self.assertEqual(cmd[0:2], ["sbatch", "--parsable"])
                self.assertIn("--gres=gpu:a100:1", cmd)
                self.assertEqual(cmd[-3:], [str(job_script), "org", "flight"])
                self.assertEqual("--mem=128G" in cmd, chosen is not None)
                self.assertEqual("--time=04:00:00" in cmd, chosen is not None)
                self.assertEqual("--cpus-per-task=4" in cmd, chosen is not None)

    def test_image_inventory_ignores_nonimages_and_symlinks(self):
        with tempfile.TemporaryDirectory(prefix="dpu-inventory-") as tmp:
            images = Path(tmp)
            (images / "a.JPG").write_bytes(b"abcd")
            (images / "b.tiff").write_bytes(b"xyz")
            (images / "notes.txt").write_text("not an image")
            (images / "link.jpeg").symlink_to(images / "a.JPG")
            result = submit.image_inventory(images)
            self.assertEqual(result, {"image_count": 2, "total_image_bytes": 7})


    def test_scheduled_paths_apply_workload_profiles(self):
        """Catch accidental regression to fixed resource coordinator settings."""
        for script, sandbox in (
            ("scripts/register-and-submit-atlas.sh", "atlas"),
            ("scripts/coordinate-ceres.sh", "ceres"),
        ):
            with self.subTest(script=script):
                body = (ROOT / script).read_text(encoding="utf-8")
                self.assertIn("submit-pending-odm.py", body)
                self.assertIn(f"--sandbox {sandbox}", body)
                self.assertIn("--apply-resource-profile", body)

    def test_processing_provenance_captures_versions_without_hashing_sif(self):
        with tempfile.TemporaryDirectory(prefix="dpu-provenance-") as tmp:
            root = Path(tmp)
            (root / "scripts").mkdir()
            (root / "sif_files").mkdir()
            job = root / "scripts" / "odm-atlas-flight.sh"
            job.write_bytes(b"#!/bin/bash\nexit 0\n")
            submitter = root / "scripts" / "submit-pending-odm.py"
            submitter.write_bytes(b"# submitter\n")
            image = root / "sif_files" / "odm-3.6.2-gpu.sif"
            image.write_bytes(b"synthetic image (not a real SIF)")
            with patch.dict(os.environ, {"DPU_ODM_SIF": str(image)}), \
                    patch.object(provenance, "_git", side_effect=["a" * 40, ""]):
                record = provenance.capture_processing_provenance(
                    root, "atlas", submitter
                )
            self.assertEqual(record["git_commit"], "a" * 40)
            self.assertEqual(record["working_tree"], "clean")
            self.assertEqual(record["job_script_sha256"],
                             hashlib.sha256(job.read_bytes()).hexdigest())
            self.assertEqual(record["submitter_script_sha256"],
                             hashlib.sha256(submitter.read_bytes()).hexdigest())
            self.assertEqual(record["odm_image"]["resolved_path"], str(image))
            self.assertEqual(record["odm_image"]["size_bytes"], image.stat().st_size)
            self.assertIsNone(record["odm_image"]["sha256"])
            with patch.object(provenance, "_git", side_effect=[None, None]), \
                    patch.dict(os.environ, {"DPU_ODM_SIF": str(image)}):
                unknown = provenance.capture_processing_provenance(
                    root, "atlas", submitter
                )
            self.assertIsNone(unknown["git_commit"])
            self.assertEqual(unknown["working_tree"], "unknown")

    def test_atlas_direct_sbatch_defaults_match_scheduled_gpu(self):
        """Manual sbatch should not silently switch to legacy L40S defaults."""
        script = (ROOT / "scripts/odm-atlas-flight.sh").read_text(encoding="utf-8")
        directives = [line.strip() for line in script.splitlines()
                      if line.startswith("#SBATCH")]
        self.assertIn("#SBATCH --partition=gpu-a100", directives)
        self.assertIn("#SBATCH --gres=gpu:a100:1", directives)
        self.assertNotIn("#SBATCH --partition=gpu-l40s", directives)


if __name__ == "__main__":
    unittest.main()
