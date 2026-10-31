# Production path after the AMD API smoke

The October31 milestone proved that our API can produce two images on AMD and
that a bounded job cleans up. `reports/amd-api-live-result.json` records completion. It does not establish production quality, throughput,
availability or unit economics. Preserve the current serving adapter for this test.

## Noto is a candidate, not a prerequisite

The existing collection is Microsoft Fluent 3D, pinned in `configs/source.json`.
The imported review collection contains 3,145 PNGs / 1,595 concepts; later sampling
proposals refer to a selected subset. This is separate from Google's new Noto 3D
collection. The [Google design article](https://design.google/library/noto-3d-emoji-design)
is a useful style reference, but not a training specification.

The candidate audit pins `googlefonts/noto-emoji` at
`99701e07d3d1fe1bdbcdb14964547f0fd592966f`: 4,007 PNG files under `3D/png/512`,
4,006 distinct Git blobs, approximately 886 MB. These counts are files, not
independent concepts. No image import or training has started. Evidence:
`reports/noto-3d-candidate-audit.json`.

Resolve the asset-specific license before a commercial training run. At this
revision, the [README](https://github.com/googlefonts/noto-emoji/blob/99701e07d3d1fe1bdbcdb14964547f0fd592966f/README.md)
says most images use Apache 2.0, while its linked
[root LICENSE](https://github.com/googlefonts/noto-emoji/blob/99701e07d3d1fe1bdbcdb14964547f0fd592966f/LICENSE)
contains SIL OFL 1.1. There is no license file within `3D/png` in the inspected
tree. The gallery's CC BY 4.0 answer refers to animated assets, so it does not
resolve this PNG ambiguity. Do not claim blanket commercial training clearance
from the article's “open source” wording.

Our pinned [FLUX.2 Klein base 4B license](https://huggingface.co/black-forest-labs/FLUX.2-klein-base-4B/blob/a3b4f4849157f664bdbc776fd7453c2783562f4d/LICENSE.md)
is Apache 2.0. Preserve applicable licenses, notices and provenance in any model
release. This does not settle the separate dataset-license question.

Once terms are clear, import Noto into a separate versioned dataset. Audit alpha,
dimensions, duplicate bytes and visual duplicates; map Unicode sequences to
accurate captions. Split by concept/family before training so skin tones and
gender variants do not leak into held-out evaluation. Compare separate Fluent
and Noto style pilots before deciding whether mixing them helps. Include novel
compositions, hand anatomy, small-size readability and tone coverage. Existing
AI review found the gesture benchmark failed; style learning alone will not
necessarily solve those compositions.

## Subsequent milestones

1. Record AMD startup time, model-load cost, render latency, peak memory and
   visual review from this run. Distinguish inference acceptance from model quality.
2. Resolve data terms and captions, prepare a sealed evaluation split and a small
   explicit training allowance. Train only a bounded pilot before expanding.
3. Promote an adapter only after a documented quality decision on held-out outputs.
4. Exercise the durable API/worker with the real renderer: idempotency, retry and
   crash handling, quotas, artifact integrity, rate limits and tenant isolation.
   The legacy API smoke does not validate all durable-worker recovery guarantees.
5. Measure warm/cold throughput and cost, choose capacity and a recurring budget,
   then deploy a limited private production trial with HTTPS/authentication,
   monitoring, backups, retention, secret management, rollback and a spend cutoff.
   Public/persistent GPU hosting has not been started by this milestone.

## Findings from the completed API milestone

The apple and smile are semantically recognizable in AI visual review. The smile
retains a large gray shadow/background patch, so cutout/shadow treatment is the
next visible quality issue. Preserve the original generated files for comparison.
The run observed33.657s for the first render and3.952s for the second, with about
17.7GB peak allocated VRAM. A controlled throughput/cold-start benchmark is still
needed; these two differently prompted samples do not establish service capacity.
The GPU and all preceding test instances were independently confirmed deleted.
