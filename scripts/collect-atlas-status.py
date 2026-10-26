#!/usr/bin/env python3
"""Collect Slurm accounting evidence for submitted Atlas ODM flights (login host)."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

RECEIPT = 'odm-submission.submitted.json'
SNAPSHOT = 'odm-slurm-accounting.json'


def guid(s):
    s = str(s)
    if str(UUID(s)) != s:
        raise ValueError(f'noncanonical GUID: {s}')
    return s


def atomic_json(path, data):
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.slurm-accounting-', delete=False) as f:
            temp = Path(f.name)
            json.dump(data, f, indent=2)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if temp and temp.exists():
            temp.unlink()


def sacct_utc(value):
    """Parse sacct's timestamp obtained with TZ=UTC into UTC ISO 8601."""
    if value in {'Unknown', 'None', ''}:
        return None
    parsed = datetime.fromisoformat(value)
    # TZ=UTC makes sacct's otherwise-naive time fields UTC.
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def collect(path, dry_run):
    flight_dir = path.parent
    if flight_dir.parent.name != 'flights':
        raise ValueError('invalid flight directory layout')
    org, flight = guid(flight_dir.parent.parent.name), guid(flight_dir.name)
    receipt = json.loads(path.read_text(encoding='utf-8'))
    if receipt.get('organization_id') != org or receipt.get('flight_id') != flight:
        raise ValueError('submission receipt does not match directory')
    job_id = str(receipt.get('slurm_job_id', ''))
    if not job_id.isdigit():
        raise ValueError('invalid Slurm job ID')
    command = ['sacct', '-n', '-P', '-X', '-j', job_id,
               '-o', 'JobIDRaw,State,ExitCode,Start,End,Partition']
    # Force sacct to emit UTC rather than local, timezone-less wall times.
    environment = dict(os.environ, TZ='UTC', SLURM_TIME_FORMAT='standard')
    result = subprocess.run(command, check=False, text=True, capture_output=True,
                            env=environment)
    if result.returncode:
        raise RuntimeError(f'sacct failed: {result.stderr.strip()}')
    records = [line.split('|') for line in result.stdout.splitlines() if line.strip()]
    matching = [r for r in records if len(r) == 6 and r[0] == job_id]
    if len(matching) != 1:
        raise RuntimeError(f'expected one Slurm accounting record, got {len(matching)}')
    _, state, exit_code, start, end, partition = matching[0]
    started_at, ended_at = sacct_utc(start), sacct_utc(end)
    # Do not silently mislabel local Slurm time as UTC if TZ is ignored.
    if started_at and receipt.get('submitted_at'):
        submitted = datetime.fromisoformat(receipt['submitted_at'].replace('Z', '+00:00'))
        if submitted.tzinfo is None:
            raise ValueError('submission timestamp has no timezone')
        if datetime.fromisoformat(started_at) < submitted - timedelta(minutes=2):
            raise ValueError('Slurm start predates submission; check sacct timezone')
    if started_at and ended_at and ended_at < started_at:
        raise ValueError('Slurm end predates start; check sacct timezone')
    snapshot = {
        'flight_id': flight, 'organization_id': org, 'slurm_job_id': job_id,
        'state': state.split()[0].split('+')[0].upper(), 'exit_code': exit_code,
        'started_at': started_at,
        'ended_at': ended_at,
        'partition': partition or receipt.get('partition'),
        'observed_at': datetime.now(timezone.utc).isoformat(),
    }
    if not dry_run:
        atomic_json(flight_dir / SNAPSHOT, snapshot)
    print(f"{'WOULD RECORD' if dry_run else 'RECORDED'}: {flight} job={job_id} state={snapshot['state']}", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data-root', required=True, type=Path)
    ap.add_argument('--flight-id', help='Limit to a single flight GUID')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    root = args.data_root.expanduser().resolve(strict=True) / 'site-id'
    if args.flight_id:
        guid(args.flight_id)
    receipts = sorted(root.glob(f'*/flights/*/{RECEIPT}'))
    errors = 0
    for path in receipts:
        if args.flight_id and path.parent.name != args.flight_id:
            continue
        try:
            collect(path, args.dry_run)
        except Exception as exc:
            errors += 1
            print(f'ERROR: {path}: {exc}', file=sys.stderr, flush=True)
    print(f'Slurm collection errors: {errors}', flush=True)
    return int(bool(errors))


if __name__ == '__main__':
    sys.exit(main())
