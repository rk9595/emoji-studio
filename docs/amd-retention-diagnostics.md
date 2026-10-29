# Private runtime retention diagnostics and recovery review

The diagnostics milestone is complete as offline preparation. No workflow was
dispatched, publication re-enabled, registry version created or GPU allocated.
`scripts/retention_stage.py` is integrated into both identical retention workflow
copies. `configs/amd-image-retention-proposal.json` still disables publication;
pricing/source/privacy checks still precede any write stage.

## Records that survive a failed job

Each wrapped operation emits `RETENTION_STAGE_RECEIPT` with an allowlisted stage,
validated run/source identity and deadline before invocation. On completion it emits
exit code, monotonic elapsed milliseconds, timeout flag, tail-truncation flag and a
fixed classification. No command, arguments, filename, raw diagnostic, response
body, token, signed URL or environment value is reflected into these records.
A start record without a finish record means uncertain completion, not success or
absence. Actions logs retain these records; no artifact/cache upload is added.

The nine stages distinguish initial/repeated preflight, publication login, copy,
remote metadata verification, fresh-runner metadata check/login/pull and final
verification. Build/audit output remains as before. Successful final acceptance
still requires the original `RETENTION_RECEIPT` after fresh pull and CPU audit;
a successful stage record alone is not image acceptance.

Raw stdout/stderr go only to exclusively created 0600 files in RUNNER_TEMP. The
classifier examines at most the last 64 KiB. Named JSON outputs are similarly
private and refuse overwrite/symlink paths. CLI/transport exceptions are sanitized;
invalid arguments are not echoed. Credentials pass through stdin to login rather
than entering command arguments or image layers. Existing auth-file cleanup remains.
Raw log files live only on the disposable runner; their full size is not capped by
the classifier and they are never printed or uploaded.

Classification uses a small allowlist of verifier error codes and fixed textual
hints for access, capacity, rate limiting, connection, timeout and digest issues.
Hints are not proof of cause: a string in an untrusted error could trigger one.
Only the wrapper's actual elapsed-time timeout produces `stage_deadline_exceeded`;
a child exiting 124 alone does not. Unknown/malformed output becomes a fixed
unclassified failure. Successful exit is reported as success regardless of log text.

One process is launched, with no command retry. On deadline, the helper terminates
then kills the process group, including children, with bounded shutdown waits.
Copy remains 600 seconds and fresh pull 1200 seconds; process cleanup can add up to
ten seconds within the unchanged 45/30-minute job limits. Login is bounded to 60
seconds; preflight to 120; metadata verification to 180. Runner loss/cancellation
can still prevent a final receipt and leave publication ambiguous. Reconcile the
original tag before any later write; do not turn diagnostics into a replay policy.

## Review of the failed attempt and copy budget

The October 25 run `40170595914` passed all CPU checks, then exited 1 in a combined
publication step after approximately 570 seconds. The private copy log was not
retained. That evidence does not distinguish a copy error from another substage,
and does not establish timeout, authentication failure or insufficient throughput.
The historical log cannot be retroactively classified by this new helper.

The pinned base has 12,763,439,494 compressed bytes. **If all those bytes needed to
cross the connection within 600 seconds**, payload throughput alone would need
about 21.27 MB/s (20.29 MiB/s). That excludes additional layers and local processing
and does not account for registry blob reuse. It is a planning calculation, not a
measurement of the failed runner, upload bytes, or registry behavior. There is no
evidence yet to change compression/format, expand time, switch registry, or pay for
a larger runner. Keep the reviewed Skopeo command and its zero command retries.

## Proposed next recovery step — gated, not launched

Review activation against fresh evidence before a deliberate new run:

1. Recheck current GHCR/public-standard-runner cost rules and same-owner package
   visibility/version state. The October 29 signed-in owner UI showed no packages;
   the earlier owner-check request is satisfied, but that listing is not an atomic
   absence guarantee. Inspect the original tag if evidence indicates it exists.
2. Reconcile the existing one-private-version scope with the consumed attempt.
   There must be no automatic rerun, second version, overwrite, deletion, public
   visibility change, paid fallback or comparison reuse. If scope/authority cannot
   be resolved within the existing delegation, mark waiting_user with the concrete
   remaining decision instead of dispatching.
3. Only after that deliberate review, refresh the pricing date, explicitly resolve
   the publication gate and bind the exact source commit. Preflight still refuses
   known existing versions and wrong visibility/identity. Keep both source and
   first-run-attempt checks; do not weaken 404 ambiguity or privacy verification.
4. One reviewed run would keep the same native CPU build, private namespace,
   45-minute publication/30-minute verification jobs, ten-minute single copy,
   twenty-minute fresh pull and final CPU audit. Record its exact run/head/workflow
   for ordinary receipt monitoring, avoiding model polling.
5. If it fails, use the earliest failed stage plus the immutable original tag to
   decide the next read-only investigation. Do not automatically retry that stage.

Validation: 15 new diagnostic tests; combined **94 tests/143 subtests** passed.
Tests cover credential stdin, redaction of adversarial output, fixed error codes,
missing executables, signal exits, process-tree timeout cleanup, private exclusive
outputs, no repeated command, invalid CLI input, closed publication preflight and
workflow limits. Ruff, YAML, Bash syntax and the unchanged 38-file context passed.
See `reports/amd-retention-diagnostics.json` for source fingerprints.
