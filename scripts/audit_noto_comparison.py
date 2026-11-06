"""Verify retained comparison payloads and campaign-e pairing without GPU work."""
import argparse
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(baseline, candidate, root):
    old = json.loads((baseline / 'report.json').read_text())
    new = json.loads((candidate / 'report.json').read_text())
    config = json.loads((root / 'configs/amd-comparison.json').read_text())
    recipe = json.loads((root / 'configs/lora-fluent-noto-v1.json').read_text())
    assert old['status'] == new['status'] == 'completed'
    assert old['config_sha256'] == digest(root / 'configs/amd-comparison.json')
    assert old['benchmark_sha256'] == digest(root / config['benchmark'])
    assert new['recipe_sha256'] == digest(root / 'configs/lora-fluent-noto-v1.json')
    assert recipe['evaluation']['sha256'] == old['benchmark_sha256']
    for key in ('steps', 'guidance_scale', 'resolution', 'seeds'):
        assert config[key] == recipe['evaluation'][key], key
    assert config['model_revision'] == recipe['model_revision']
    assert config['model_id'] == recipe['model_id']
    expected_adapter = '8dc022f06b20e73a0c5cbaa935730225f54f6e191e3ef3a2a89e33d8ff0102f9'
    assert new['files']['step-656.safetensors']['sha256'] == expected_adapter
    for name, meta in new['files'].items():
        path = (candidate / name).resolve()
        assert path.is_relative_to(candidate.resolve())
        assert digest(path) == meta['sha256'] and path.stat().st_size == meta['bytes']
    conditions = {c['id']: c for c in config['conditions']}
    rows = {}
    for row in old['images']:
        path = (baseline / row['image']).resolve()
        assert path.is_relative_to(baseline.resolve()) and digest(path) == row['sha256']
        assert row['adapter_sha256'] == conditions[row['condition']]['sha256']
        key = (row['condition'], row['prompt'], row['seed'])
        assert key not in rows
        rows[key] = row
    seen = set()
    for row in new['images']:
        key = (row['prompt'], row['seed'])
        assert key not in seen
        seen.add(key)
        assert row['adapter_sha256'] == expected_adapter and row['steps'] == 50
        for condition in ('base', 'pilot-25'):
            assert (condition, *key) in rows
    assert len(seen) == 24 and len(rows) == 144
    return {'baseline_images_verified': len(rows), 'candidate_images_verified': len(seen),
            'reusable_baseline_images': 48, 'new_gpu_renders_needed_for_offline_review': 0,
            'baseline_environment': old['environment'], 'candidate_environment': new['environment'],
            'baseline_report_sha256': digest(baseline / 'report.json'),
            'candidate_report_sha256': digest(candidate / 'report.json'),
            'limitation': 'Retrospective comparison across separate runs; environment equality does not establish identical installed dependencies or a sealed test.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.baseline, args.candidate, Path(__file__).resolve().parents[1]), indent=2))
