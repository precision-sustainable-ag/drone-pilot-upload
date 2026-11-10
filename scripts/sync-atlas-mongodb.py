#!/usr/bin/env python3
"""Reconcile Atlas Slurm evidence and verified products into sandbox MongoDB.

Run with the application Apptainer Python environment on an authorized host.
No database writes occur in --dry-run mode.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from pymongo import MongoClient

DB = 'drone-pilot-atlas-sandbox'
COLLECTION = 'flight-information'
RECEIPT = 'odm-submission.submitted.json'
SNAPSHOT = 'odm-slurm-accounting.json'
PRODUCTS = {
    'orthophoto': 'odm/code/odm_orthophoto/odm_orthophoto.tif',
    'vari': 'odm/veg_indices/vari_image.tif',
    'gli': 'odm/veg_indices/gli_image.tif',
}
RUNNING = {'RUNNING', 'COMPLETING', 'CONFIGURING'}
WAITING = {'PENDING', 'REQUEUED', 'RESIZING', 'SUSPENDED'}
SUCCESS = {'COMPLETED'}
FAILURES = {'FAILED', 'CANCELLED', 'TIMEOUT', 'OUT_OF_MEMORY', 'NODE_FAIL',
            'BOOT_FAIL', 'PREEMPTED', 'DEADLINE', 'REVOKED'}


def guid(value):
    value = str(value)
    if str(UUID(value)) != value:
        raise ValueError(f'noncanonical GUID: {value}')
    return value


def nonempty(path):
    return path.is_file() and path.stat().st_size > 0


def utc_datetime(value):
    """Convert timezone-aware ISO 8601 text to a UTC BSON-compatible date."""
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError(f'timestamp lacks timezone: {value!r}; recollect Slurm accounting')
    return parsed.astimezone(timezone.utc)


def plan(path):
    folder = path.parent
    if folder.parent.name != 'flights':
        raise ValueError('invalid flight directory layout')
    org, flight = guid(folder.parent.parent.name), guid(folder.name)
    receipt = json.loads(path.read_text(encoding='utf-8'))
    if receipt.get('organization_id') != org or receipt.get('flight_id') != flight:
        raise ValueError('receipt identity mismatch')
    job_id = str(receipt.get('slurm_job_id', ''))
    if not job_id.isdigit():
        raise ValueError('invalid job ID')
    snapshot_path = folder / SNAPSHOT
    if not snapshot_path.is_file():
        raise ValueError(f'no Slurm evidence: {snapshot_path}')
    slurm = json.loads(snapshot_path.read_text(encoding='utf-8'))
    if (slurm.get('flight_id') != flight or slurm.get('organization_id') != org or
            str(slurm.get('slurm_job_id')) != job_id):
        raise ValueError('Slurm evidence does not match submission receipt')
    state = slurm.get('state')
    exit_code = slurm.get('exit_code')
    present = {name: nonempty(folder / relative) for name, relative in PRODUCTS.items()}
    artifacts = {
        'orthophoto': PRODUCTS['orthophoto'] if present['orthophoto'] else None,
        'vegetation_indices': {name: PRODUCTS[name] for name in ('vari', 'gli') if present[name]},
    }
    odm = 'succeeded' if present['orthophoto'] else 'pending'
    oi = 'succeeded' if present['vari'] and present['gli'] else 'pending'
    error = None
    if state in WAITING:
        overall = 'queued'
        odm, oi = 'pending', 'pending'
    elif state in RUNNING:
        overall = 'ortho generated' if present['orthophoto'] else 'processing'
        if not present['orthophoto']:
            odm = 'processing'
        if oi != 'succeeded':
            oi = 'processing' if present['orthophoto'] else 'pending'
    elif state in SUCCESS and exit_code == '0:0':
        if all(present.values()):
            overall, odm, oi = 'processed', 'succeeded', 'succeeded'
        else:
            overall = 'failed'
            error = 'Slurm completed but required products missing: ' + ', '.join(
                name for name, exists in present.items() if not exists
            )
            odm = 'succeeded' if present['orthophoto'] else 'failed'
            oi = 'succeeded' if present['vari'] and present['gli'] else 'failed'
    elif state in FAILURES or state in SUCCESS:
        overall = 'failed'
        error = f'Slurm state={state}, exit_code={exit_code}'
        odm = 'succeeded' if present['orthophoto'] else 'failed'
        oi = 'succeeded' if present['vari'] and present['gli'] else 'failed'
    else:
        raise ValueError(f'unknown Slurm state {state!r}; refusing to guess')

    payload = {
        'status': overall,
        'stages.odm.state': odm,
        'stages.ortho_intel.state': oi,
        'processing.engine': 'odm',
        'processing.slurm_job_id': job_id,
        'processing.partition': receipt.get('partition'),
        'processing.slurm_state': state,
        'processing.exit_code': exit_code,
        'processing.submitted_at': utc_datetime(receipt.get('submitted_at')),
        'processing.started_at': utc_datetime(slurm.get('started_at')),
        'processing.completed_at': utc_datetime(slurm.get('ended_at')) if state in SUCCESS | FAILURES else None,
        'processing.observed_at': datetime.now(timezone.utc),
        'processing.error': error,
        'artifacts': artifacts,
    }
    return flight, org, payload


def stored_value(document, dotted_key):
    """Read a field managed by this script, including dotted MongoDB paths."""
    value = document
    for key in dotted_key.split('.'):
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def same_value(actual, expected):
    """Compare BSON dates as UTC milliseconds (MongoDB drops microseconds)."""
    if isinstance(expected, datetime):
        if not isinstance(actual, datetime):
            return False
        def to_bson_utc(value):
            if value.tzinfo is None:  # PyMongo decodes UTC dates as naive by default.
                value = value.replace(tzinfo=timezone.utc)
            value = value.astimezone(timezone.utc)
            return value.replace(microsecond=(value.microsecond // 1000) * 1000)
        return to_bson_utc(actual) == to_bson_utc(expected)
    return actual == expected


def is_current(existing, payload):
    """Ignore the refreshed observation timestamp; compare only owned fields."""
    return all(
        same_value(stored_value(existing, field), value)
        for field, value in payload.items()
        if field != 'processing.observed_at'
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data-root', required=True, type=Path)
    ap.add_argument('--flight-id')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    root = args.data_root.expanduser().resolve(strict=True) / 'site-id'
    if args.flight_id:
        guid(args.flight_id)
    receipts = sorted(root.glob(f'*/flights/*/{RECEIPT}'))
    planned = []
    failures = 0
    for path in receipts:
        if args.flight_id and path.parent.name != args.flight_id:
            continue
        try:
            planned.append(plan(path))
        except Exception as exc:
            failures += 1
            print(f'ERROR: {path}: {exc}', file=sys.stderr, flush=True)

    if not planned:
        print(f'Reconciliation: 0 {"updates needed" if args.dry_run else "updated"}; '
              f'0 current; 0 preserved; {failures} errors', flush=True)
        return int(bool(failures))

    # A dry run must read the same sandbox records as an actual reconciliation,
    # but it must never write them.
    if (os.environ.get('DPU_MONGODB_DATABASE') != DB or
            os.environ.get('DPU_MONGODB_COLLECTION') != COLLECTION):
        ap.error('Refusing to access outside the dedicated Atlas sandbox collection')
    uri = os.environ.get('DPU_MONGODB_CONNECTION_STRING')
    if not uri:
        ap.error('Missing DPU_MONGODB_CONNECTION_STRING')

    updates = current = preserved = 0
    client = MongoClient(uri, serverSelectionTimeoutMS=10000)
    try:
        col = client[DB][COLLECTION]
        for flight, org, payload in planned:
            try:
                existing = col.find_one({'flight_id': flight})
                if not existing:
                    raise ValueError('flight has not been registered in MongoDB')
                if existing.get('organization_id') != org:
                    raise ValueError('MongoDB organization mismatch')
                prior_job = existing.get('processing', {}).get('slurm_job_id')
                if prior_job is not None and str(prior_job) != payload['processing.slurm_job_id']:
                    raise ValueError('Existing processing job differs; explicit retry handling required')
                if existing.get('status') == 'processed' and payload['status'] != 'processed':
                    preserved += 1
                    print(f'PRESERVED: {flight}: MongoDB completion retained (not demoting)', flush=True)
                    continue
                if is_current(existing, payload):
                    current += 1
                    print(f'CURRENT: {flight}: MongoDB matches verified results', flush=True)
                    continue
                if args.dry_run:
                    updates += 1
                    print(f'UPDATE NEEDED: {flight}: MongoDB differs from verified results', flush=True)
                    continue
                result = col.update_one(
                    {'_id': existing['_id'], 'organization_id': org},
                    {'$set': payload},
                )
                if result.matched_count != 1:
                    raise RuntimeError('MongoDB update did not match flight')
                updates += 1
                print(f'UPDATED: {flight}: MongoDB synchronized with verified results', flush=True)
            except Exception as exc:
                failures += 1
                print(f'ERROR: {flight}: {exc}', file=sys.stderr, flush=True)
    finally:
        client.close()

    count_label = 'updates needed' if args.dry_run else 'updated'
    print(f'Reconciliation: {updates} {count_label}; {current} current; '
          f'{preserved} preserved; {failures} errors', flush=True)
    if args.dry_run:
        print('MongoDB unchanged.', flush=True)
        if failures:
            print('Resolve errors before reconciliation.', flush=True)
        elif updates:
            print('Next action: scripts/atlas.sh reconcile', flush=True)
        else:
            print('No reconciliation necessary.', flush=True)
    return int(bool(failures))


if __name__ == '__main__':
    sys.exit(main())
