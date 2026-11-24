# Queue-aware ODM selection (Issue #38)

Initial advisory and explicitly opted-in implementation. Existing scheduled coordinators are unchanged.

On an isolated checkout on Atlas:

```bash
python3 scripts/submit-pending-odm.py --sandbox atlas \
  --data-root "/project/dash_drone/user/$USER/dpu-data" --repo "$PWD" \
  --apply-resource-profile --queue-aware --allow-candidate l40s \
  --allow-candidate v100 --compare-inventory 48 1073741824 --dry-run
```

On Ceres use --sandbox ceres --allow-candidate cpu8 --allow-candidate cpu16 instead of the Atlas options. This probes the actual batch script using sbatch --test-only; it does not upload, reserve markers, submit jobs, or alter MongoDB. Without compare-inventory, dry run inspects actual pending flights. Do not use live submission from an isolated worktree against the unattended sandbox queue: the existing coordinator may compete and the worktree needs access to the correct SIF and processing dependencies. Explicit operator approval and an isolated test flight are required before enabling alternatives for live work.

Initial hypotheses (48 images, including postprocessing): A100 30 min, L40S 35, V100 45, Ceres 4/8/16 CPUs 55/35/25. Estimates scale provisionally by image count, with a lower bound; only small workload profiles participate. Ceres 16 CPUs requests 128G. Actual timings may differ substantially. Alternatives require explicit allow flags. Unavailable default predictions retain the established profile; unavailable alternative predictions are excluded. No changes to already submitted jobs. Atlas CPU-only and MIG execution, scavenger, cross-cluster routing and automatic activation are deferred. Alternative GPU compatibility and Ceres scaling must be exercised before unattended activation. Slurm predictions are advisory, not reservations. Host timezone must correspond to Slurm's output timezone.

On November 24, test-only requests for A100, L40S, V100 and Atlas CPU all predicted 12:47:04; Ceres 4/8/16 CPUs (64G each) all predicted 12:48:00. The new 16-CPU 128G candidate requires a fresh test-only probe. No real jobs were submitted by these probes.

Run python3 -m unittest discover -s tests -p 'test_odm_*.py' -v and bash -n scripts/odm-atlas-flight.sh scripts/odm-ceres-flight.sh. Then compare live Slurm reports and authorize a targeted test on each cluster. Receipt decision evidence records alternatives and estimates; actual accounting remains in existing #28 collection.
