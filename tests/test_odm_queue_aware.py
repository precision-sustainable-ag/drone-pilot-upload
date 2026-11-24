import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch
from subprocess import CompletedProcess
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from queue_aware_odm import choose, predict_start

NOW = datetime(2026, 11, 24, 12, tzinfo=timezone.utc)
INV = {"image_count": 48, "total_image_bytes": 1073741824}

class QueueAwareTests(unittest.TestCase):
    def pick(self, sandbox, allowed, delays, name="small"):
        profile = {"name": name, "partition": "gpu-a100" if sandbox == "atlas" else "ceres",
                   "gres": "gpu:a100:1" if sandbox == "atlas" else None,
                   "cpus": 4, "mem": "64G", "time": "01:00:00"}
        def predict(command, **kwargs):
            delay = delays.get(command[0])
            return NOW + timedelta(minutes=delay) if delay is not None else None
        return choose(sandbox, profile, INV, allowed,
                      lambda p: [p["partition"] if sandbox == "atlas" else p["cpus"]],
                      predictor=predict, now=NOW)

    def test_alternative_gpu(self):
        p, d = self.pick("atlas", ["l40s"], {"gpu-a100": 40, "gpu-l40s": 0})
        self.assertEqual(p["gres"], "gpu:l40s:1")
        self.assertEqual(d["selected"], "l40s")

    def test_default_when_equal(self):
        p, _ = self.pick("atlas", ["l40s"], {"gpu-a100": 0, "gpu-l40s": 0})
        self.assertEqual(p["partition"], "gpu-a100")

    def test_ceres_more_cpus(self):
        p, _ = self.pick("ceres", ["cpu8", "cpu16"], {4: 0, 8: 0, 16: 0})
        self.assertEqual((p["cpus"], p["mem"]), (16, "128G"))

    def test_missing_baseline(self):
        p, _ = self.pick("atlas", ["l40s"], {"gpu-l40s": 0})
        self.assertEqual(p["partition"], "gpu-a100")

    def test_no_opt_in(self):
        p, d = self.pick("ceres", [], {4: 0, 16: 0})
        self.assertEqual(p["cpus"], 4)
        self.assertEqual(len(d["alternatives"]), 1)

    def test_large_fallback(self):
        p, d = self.pick("ceres", ["cpu16"], {4: 0, 16: 0}, "large")
        self.assertEqual(p["cpus"], 4)
        self.assertFalse(d["alternatives"])

    @patch("queue_aware_odm.subprocess.run")
    def test_probe_does_not_submit(self, run):
        run.return_value = CompletedProcess([], 0, "", "sbatch: Job 123 to start at 2026-11-24T12:47:04 a using 4 processors")
        self.assertIsNotNone(predict_start(["sbatch", "--parsable", "job.sh"]))
        self.assertEqual(run.call_args.args[0], ["sbatch", "--test-only", "job.sh"])
