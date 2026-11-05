# Campaign e evaluation review

Status: complete, no promotion. This is an AI review, not a human quality decision.

- Private run `41998689039` rendered all 24 planned images from the unchanged
  step-656 adapter. No training occurred.
- All 24 PNGs are 512x512 and match the completed report's SHA-256 records. The
  adapter hash also matches. Results archive SHA-256:
  `1a72454f8e11db3a51e069f0c1d0628e79339aad6e8ecaf4d0e4a691c75821c1`.
- GPU `616116808` was deleted by the controller and independently confirmed
  absent by the watchdog.
- Estimated campaign cost is $0.2199; aggregate training/evaluation cost is
  $1.0613 of the $10 reserve.

Visual findings:

- Face, firefighter, backpack, and bicycle prompts are visually coherent.
- `evaluation-20.png` and `evaluation-21.png` resemble prayer/pressed hands,
  not two people's hands meeting in a high-five.
- `evaluation-04.png` through `evaluation-13.png` are inconsistent or ambiguous
  as crossed fingers; several read primarily as a raised index finger.
- Pinky-promise outputs `evaluation-22.png` and `evaluation-23.png` are mixed.
- This evaluation has no matched baseline, so it does not establish improvement.

Do not promote step-656. Production serving remains on the reviewed step-25
pilot. Any new training direction needs user judgment plus a fresh immutable
plan and allocation claim.
