# Emoji Studio automation

The cloud comparison runs in the private `rk9595/emoji-studio-ops` repository.
The public repository contains reusable controller/evaluator source only.

`python3 ops/prepare_campaign.py` verifies all five adapter hashes and creates an
explicit 133 MB input archive under ignored `artifacts/amd-comparison-v1/`.
The private release holds this archive, a checksum-locked campaign, `state.json`,
incremental `live-results.tar.gz`, and final `results.tar.gz`.

The controller verifies the live hourly rate, creates one owned MI300X at a time,
checks that its independent expiry timer is active, uploads the verified bundle,
and runs the comparison in the tested ROCm container. It copies outputs every
45 seconds and verifies every final image before recording completion. Cleanup
also runs on errors; a separate hourly workflow reaps overdue owned instances.
The VM has a root-only self-deletion guard that does not require GitHub connectivity.
Its API credential is not bundled with artifacts. Provider/API failures can delay
deletion, so the $3 reserve is not an enforceable provider billing cap.

Completed October 13: all 144 images verified, all four allocated instances
deleted, approximately $0.99 estimated GPU cost within the $3 reserve.
See `reports/amd-comparison-v1.md`; private results and AI review are backed up
in release assets. No fifth allocation or reset of the completed campaign.
The serving adapter remains pilot step 25 after the AI diagnostic review.

Transport retries safe checks and reuses connections only after readiness.
Readiness uses fresh connections, completed cloud initialization and a clean
explicit sentinel: a persistent connection opened during provider bootstrap can
retain its temporary forced command even after the VM is ready. Worker launch
is idempotent through a named systemd unit. The consumed terminal state prevents
the scheduled controller from allocating again. Next queued work is offline;
see `docs/private-alpha-deployment-plan.md` for the new-spending gates.

## Codex continuation and memory

The local LaunchAgent runs `ops/codex_supervisor.py` every 15 minutes. It connects
to the existing app-server over its private Unix socket using the WebSocket
transport used by Codex itself. It uses `account/rateLimits/read` and respects
the latest reset across exhausted usage windows. It neither buys credits nor
switches accounts or models. Checks use no model tokens.

It reads `ops/work-queue.json`; a cloud-wait state only starts a model turn when
the remote job finishes or fails. It resumes the exact authorized thread, skips
active threads, uses a process lock, and waits at least 30 minutes between its own
continuations. Completed, paused, and user-wait states do not start turns. Every
six continuations it can request compaction if a fresh durable handoff exists.

Runtime configuration, locks and receipts are under ignored `var/automation/`.
The dependency is pinned in `ops/supervisor-requirements.txt`. Check operation:

```sh
var/automation/venv/bin/python ops/codex_supervisor.py --diagnostic
launchctl print gui/501/com.emoji-studio.codex-supervisor
```

To stop local continuation, set `enabled` to false in
`var/automation/supervisor.json`, or unload the LaunchAgent:

```sh
launchctl bootout gui/501/com.emoji-studio.codex-supervisor
```

This is a local scheduler, not a native cloud Codex schedule. It requires an
awake Mac and the app-server. The independent GPU job continues while the Mac
sleeps, saves evidence remotely, and can be picked up on wake. Exact reset-time
restart is not guaranteed: a local check runs at most every 15 minutes while awake.

References: [official scheduling documentation](https://learn.chatgpt.com/docs/automations),
[app-server usage and compaction API](https://learn.chatgpt.com/docs/app-server),
[official Unix-socket WebSocket transport](https://github.com/openai/codex/blob/main/codex-rs/app-server-transport/src/transport/unix_socket.rs).

Use `AGENTS.md` and `docs/automation-state.md` for compact working memory instead
of replaying old session logs. Never save credentials in those files.
