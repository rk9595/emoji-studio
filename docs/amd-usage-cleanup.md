# GPU cleanup before model usage limits

The user explicitly requested this on October 30, together with authorization to
run the prepared third API attempt. It supplements the existing cloud expiry;
the GPU must never be left idle waiting for model quota to reset.

`ops/amd_usage_guard.py` runs as ordinary detached local code. It reads the
[documented app-server rate-limit endpoint](https://learn.chatgpt.com/docs/app-server)
every 30 seconds, considers every reported bucket and both primary/secondary
windows, and requests cleanup at **85% used**. Two consecutive unavailable or
invalid readings also request cleanup. It does not consume reset credits, change
OpenAI account settings or send messages.

The request is an immutable `stop-request.json` asset in the private campaign
release, bound to the campaign and exact Actions run. No AMD credential is needed
locally. Both the cloud controller and independent watchdog verify that identity.
The controller checks during boot, before launch and while waiting; the watchdog
also deletes early, including if the controller is unavailable. Authenticated
exact-resource 404 remains the criterion for verified deletion.

The watcher records its receipt under `var/amd-api-live/`, stops when the exact
cloud run finishes, and has a 40-minute outer lifetime. No model tokens are needed
for its polling. If the Mac sleeps, the socket disappears, the watcher dies or
usage changes abruptly, early warning may be unavailable. Therefore the cloud
watchdog and on-instance minute-26 self-expiry remain mandatory, with work stopped
at minute25 and the outer deletion deadline at minute30. Provider outages can
still delay deletion; these controls are not an absolute billing guarantee.

Four usage-policy tests cover either quota window, multiple metered buckets,
unknown/invalid signals and a classified reached limit. The controller tests
verify stop requests cannot target a different run. The separate SSH master uses
non-pipe output descriptors to avoid preventing probe completion; command output
is framed independently of provider banners. The prepared transport/cleanup suite
contains 16 tests, and exact cloud-receipt monitoring has eight more.

Active execution is recorded in `ops/work-queue.json`, not inferred from an older
release. Use the active run/source/release in that queue. The supervisor also recognizes
`waiting_usage` and defers model continuation until the recorded reset and a fresh
reading below85%. Do not reset older allocation claims.
