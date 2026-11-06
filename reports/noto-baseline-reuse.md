# Retained baseline reuse audit — 2026-11-06

Verified 144 historical comparison images and 24 campaign-e images locally.
All payload hashes passed. Each candidate prompt/seed has both a base and
pilot-25 counterpart: 48 existing baseline images can support an offline review.
No new GPU renders are needed to prepare that review.

Model revision, benchmark hash, prompt text, seeds, resolution, guidance and
inference steps agree. Recorded PyTorch, HIP and GPU identifiers also agree.
These are separate runs with potentially different application dependencies;
this supports a retrospective diagnostic, not a controlled experiment or a
sealed generalization test. No improvement or promotion is established.

Baseline report SHA-256:
`e479b4652c2ec6492e6c91309e4141a65eb51d93341d49da0869da2de9ba9d38`

Candidate report SHA-256:
`e7258d790309d157b6fcdea9bc97592f6030a9788b7af040b454e92d9f9ae54f`

Reproduce with `scripts/audit_noto_comparison.py --baseline runs/amd-comparison-v1
--candidate <campaign-e-training-results-directory>`. Restore candidate files
from private release `amd-noto-eval-20261105e`, archive `training-results.tar.gz`;
the completed campaign receipt records its archive hash. Local inspected copy:
`/private/tmp/emoji-noto-evidence.ppGBy7/extracted/training-results`.

Next: assemble a private shuffled review of base, pilot-25 and step-656 using
these existing files, score prompt criteria before decoding labels, and report
gesture and non-gesture outcomes separately. Training and promotion remain
separate decisions. Consumed campaigns stay closed.

Gallery preparation completed: `runs/noto-retrospective-review-v1/index.html`.
There are 24 groups and 72 images, with criteria and 32px thumbnails. All copied
hashes, template coverage and HTML image references verified. Rebuild using
`scripts/build_noto_review.py` with the same baseline/candidate arguments and a
fresh `--output` directory. Existing output directories are refused.
Mapping SHA-256: `1d04c90a0e444e4f1043ea10bc0510c60c9eac67f0b93158efe27d415dab90b7`.
Observations remain unscored. Prior exposure to source images prevents claiming
a fully blinded AI assessment, even though labels are shuffled.
