# Qwen high-five candidate trial: preparation record

Update September 26: the trial and its approved recovery are complete. One candidate
was recovered before an SSH failure, then three more on the recovery run. All four
PNGs are verified, cleanup succeeded, and none are admitted to training. See the
[actual trial report](high-five-teacher-pilot.md) for results, costs and recovery status.
The preparation/preflight observations below are historical.

September 25, 2026. No GPU was rented and no model weights were downloaded in this
preparation. The account still showed zero instances and $6.1884668369 credit.

## Concrete workload

The trial generates four candidate images with Qwen-Image-2512, revision
`25468b98e3276ca6700de15c6628e51b7de54a26`. The source repository lists approximately
57.7 GB of model files and declares Apache-2.0. Its pinned model card was downloaded
and hashed; this does not license the separate built-in imagegen candidates from
the earlier phase. Sources: [repository](https://huggingface.co/Qwen/Qwen-Image-2512/tree/25468b98e3276ca6700de15c6628e51b7de54a26),
[model card](https://huggingface.co/Qwen/Qwen-Image-2512/blob/25468b98e3276ca6700de15c6628e51b7de54a26/README.md).

`configs/high-five-teacher-pilot.json` fixes four novel compositions: a wide V with
light/dark hands, offset-height medium/light hands, a shallow three-quarter
dark/medium view, and asymmetric golden hands. Seeds are 101/202/303/404. Settings
follow the model card's square example: 1328 pixels, 50 steps, true CFG 4.0, BF16.
Model CPU offload and VAE tiling are enabled to reduce GPU memory needs.

The selected machine requirements are one GPU with at least 48,000 MB VRAM,
128,000 MB host RAM, and 160 GB disk. These are conservative preparation requirements,
not measured proof that the workload fits. GPU imports, sampling quality, actual
memory use and runtime remain untested. A live marketplace query found zero offers
meeting these requirements and the proposed $0.70/hour ceiling; no limits were relaxed.

The sampler saves each PNG atomically with its actual prompt, seed, model/config
binding, timestamp, duration, memory peak and checksum. Snapshots capture the report
first and copy only its committed images, avoiding a race with ongoing sampling.
Every returned image must decode at the planned dimensions and match its receipt.
All outputs remain `curation_decision: pending`; this run cannot approve examples
or start training. Four images would only test whether this teacher is useful.

## Cleanup correction

The training/alpha watchdog had an identifiable flaw: it fetched credit after
computing that the deadline had expired. If billing failed, the exception handler
skipped destruction. Deadline teardown now runs without querying billing. The guard
also rechecks time after a slow billing request, stops after 120 seconds of missing
credit observations, and records heartbeat/poll-gap evidence. Tests simulate these
failure cases without creating resources.

This is a verified code defect, **not proof of the full cause** of the earlier
59.5-minute delay. The old guard already used `caffeinate -i`; merely adding that
command would not have fixed this defect. A sleeping/disconnected laptop or a failing
provider API can still delay destruction. No absolute billing guarantee is claimed.

The new trial launcher requires a live watchdog heartbeat before bootstrapping,
aborts on a stale heartbeat, reserves three minutes for cleanup, and triggers its
spending guard $0.15 below the approved cap. An independent remote timeout covers
setup and sampling, while the local launcher always attempts ownership-checked
instance destruction in `finally`. A remote process timeout alone does not stop
Vast billing. Cleanup precedes billing reconciliation so a billing failure cannot
prevent destruction.

## Prepared commands

```sh
uv run python scripts/sample_interaction_teacher.py plan
# On an already budgeted GPU, the sampler itself can be run with:
uv run python scripts/sample_interaction_teacher.py run --max-seconds 2400
uv run python scripts/sample_interaction_teacher.py verify
```

The Vast launcher is `scripts/vast_teacher_pilot.py --authorization <path>`. It
requires a fresh single-use record under `artifacts/vast-teacher-pilot/`, bound to
the plan, launcher, watchdog and helper hashes. It consumes an attempt before
calling the allocation API and never blindly retries an uncertain rental.

Approved scope (user: “yes continue”): one GPU, up to $1.50 total, at most
$0.70/hour including disk, and 60 elapsed minutes. Transfer charges count toward
the observed-credit guard. The prior alpha budget is expired and is not reused.

The approved launcher was invoked on September 25 and stopped at marketplace
preflight, before allocation: no offer met all its requirements at $0.70/hour.
The local hash-bound authorization remains unconsumed; no attempt record or rental
was created. A broader read-only diagnostic found offers at approximately
$0.75837/hour and $0.77778/hour that passed the other filters. Both advertised
49,140 MB GPU RAM and more than 128,000 MB host RAM. Cheaper listings failed host
RAM, reliability, or transfer-cost requirements. These are transient advertised
offers, not verified runtime hardware. No filter or budget was relaxed.

The user subsequently approved $0.80/hour while retaining the $1.50 total,
one-GPU and 60-minute limits. Launcher validation and tests were updated accordingly;
the earlier $0.70 authorization was superseded, not reused.

Local verification: 102 tests and Ruff passed. The actual upload archive was built
and inspected (27 entries, approximately 192 KB); it contains the locked workload,
not account credentials, alpha-user records, source datasets or adapters. The initial
draft plan was retained separately after the sampler gained image-dimension checks.

Current next step: see the actual trial report for the bounded recovery proposal.
