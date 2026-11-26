"""Opt-in queue-aware ODM selection using provisional runtime estimates."""
import re
import os
from pathlib import Path
import subprocess
from datetime import datetime, timezone, timedelta

OPTIONS = {
    "atlas": {"a100": (4, "gpu-a100", "gpu:a100:1", 30),
              "l40s": (4, "gpu-l40s", "gpu:l40s:1", 35),
              "v100": (4, "gpu-v100", "gpu:v100:1", 45)},
    "ceres": {"cpu4": (4, "ceres", None, 55),
              "cpu8": (8, "ceres", None, 35),
              "cpu16": (16, "ceres", None, 25)},
}
DEFAULT = {"atlas": "a100", "ceres": "cpu4"}
START = re.compile(r"\bto start at (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\s|$)")


def predict_start(command, *, env=None):
    """Probe the actual batch request without submitting a job."""
    if not command or command[0] != "sbatch":
        raise ValueError("Expected sbatch command")
    probe = ["sbatch", "--test-only"] + [a for a in command[1:] if a != "--parsable"]
    try:
        result = subprocess.run(probe, env=env, capture_output=True, text=True,
                                timeout=15, check=False)
        match = START.search(result.stdout + "\n" + result.stderr)
        if result.returncode or not match:
            return None
        # Slurm reports cluster-local time; assume the invoking host agrees.
        return datetime.fromisoformat(match.group(1)).astimezone(timezone.utc)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def choose(sandbox, profile, inventory, allowed, command_for, *, env=None,
           predictor=predict_start, now=None):
    now = now or datetime.now(timezone.utc)
    default = DEFAULT[sandbox]
    if set(allowed) - set(OPTIONS[sandbox]):
        raise ValueError("Unknown candidate for sandbox")
    decision = {"model": "provisional-48-image-v1", "evaluated_at": now.isoformat(),
                "selected": default, "alternatives": [], "reason": ""}
    if profile["name"] != "small":
        decision["reason"] = "Only small workloads eligible for initial selection"
        return dict(profile), decision
    ranked = []
    for name, (cpus, partition, gres, minutes) in OPTIONS[sandbox].items():
        if name != default and name not in allowed:
            continue
        candidate = dict(profile, cpus=cpus, partition=partition, gres=gres)
        if name == "cpu16":
            candidate["mem"] = "128G"
        minutes = max(10, round(minutes * max(0.5, inventory["image_count"] / 48)))
        start = predictor(command_for(candidate), env=env)
        finish = max(start, now) + timedelta(minutes=minutes) if start else None
        decision["alternatives"].append({
            "name": name, "partition": partition, "gres": gres, "cpus": cpus,
            "memory": candidate["mem"], "walltime": candidate["time"],
            "estimated_runtime_minutes": minutes,
            "estimated_start": start.isoformat() if start else None,
            "estimated_completion": finish.isoformat() if finish else None,
        })
        if finish is not None:
            ranked.append((finish, name != default, name, candidate))
    if not any(row[2] == default for row in ranked):
        decision["reason"] = "Default start estimate unavailable; retain established profile"
        return dict(profile), decision
    _, _, name, candidate = min(ranked)
    decision.update(selected=name, reason="Earliest estimated completion among eligible resources")
    return candidate, decision


def load_coordinator_policy(sandbox, *, home=None, environ=None):
    """Read non-executable, cluster-local configuration. Missing means disabled.

    Environment variables override the file, including explicit disable (0).
    Invalid configuration stops submissions rather than silently enabling resources.
    """
    environ = os.environ if environ is None else environ
    home = Path.home() if home is None else Path(home)
    path = home / ".config" / "drone-pilot-upload" / f"{sandbox}-sandbox" / "queue-aware.env"
    values = {}
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        content = ""
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or key not in ("DPU_QUEUE_AWARE", "DPU_QUEUE_CANDIDATES") or key in values:
            raise ValueError(f"Unsupported or duplicate setting in {path}")
        values[key] = value.strip()
    for key in ("DPU_QUEUE_AWARE", "DPU_QUEUE_CANDIDATES"):
        if key in environ:
            values[key] = environ[key]
    enabled = values.get("DPU_QUEUE_AWARE", "0")
    if enabled not in ("0", "1"):
        raise ValueError("DPU_QUEUE_AWARE must be 0 or 1")
    if enabled == "0":
        return False, []
    raw = values.get("DPU_QUEUE_CANDIDATES", "")
    candidates = [value.strip() for value in raw.split(",")] if raw else []
    if set(candidates) - set(OPTIONS[sandbox]):
        raise ValueError("Unknown DPU_QUEUE_CANDIDATES entry for sandbox")
    return True, list(dict.fromkeys(candidates))
