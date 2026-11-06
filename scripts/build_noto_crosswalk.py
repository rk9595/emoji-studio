"""Emit a conservative, unapplied split proposal for all 128 Noto rows."""
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALIASES = {
    'waving black flag': 'Black flag',
    'older woman': 'Old woman',
    'cat face with tears of joy': 'Cat with tears of joy',
    'clock face eight oclock': 'Eight oclock',
    'person with pouting face': 'Person pouting',
    'squared cjk unified ideograph-7a7a': 'Japanese vacancy button',
}


def build():
    path = ROOT / 'data/training/fluent-noto-v1/manifest.json'
    manifest = json.loads(path.read_text())
    normalize = lambda s: re.sub('[^a-z0-9]', '', s.lower())
    validation = {}
    for row in manifest['rows']:
        if row['included'] and row['split'] == 'validation' and 'codepoint' not in row:
            validation.setdefault(normalize(row['concept']), []).append(row)
    proposals = json.loads((ROOT / 'configs/noto-caption-proposals-v1.json').read_text())
    captions = {r['asset_id']: r for r in proposals['proposals']}
    rows = []
    for row in manifest['rows']:
        if 'codepoint' not in row or not row['included']:
            continue
        name = row['caption'].split(', noto')[0]
        target = ALIASES.get(name, name)
        matches = validation.get(normalize(target), [])
        status = ('candidate_alias' if name in ALIASES else 'exact_name') if matches else 'unresolved'
        proposal = captions.get(row['asset_id'])
        if proposal:
            assert proposal['image_sha256'] == row['sha256']
        rows.append({'asset_id': row['asset_id'], 'image_sha256': row['sha256'],
                     'original_caption': row['caption'], 'status': status,
                     'candidate_concept': target if matches else None,
                     'validation_asset_ids': [r['asset_id'] for r in matches],
                     'proposed_action': 'exclude_from_training' if matches else 'quarantine_pending_semantic_review',
                     'caption_proposal': proposal['proposed_caption'] if proposal else None})
    assert len(rows) == 128 and len({r['asset_id'] for r in rows}) == 128
    return {'status': 'proposal_only_not_applied', 'review_method': 'AI name-based triage; candidate aliases not visually confirmed',
            'manifest_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'counts': dict(Counter(r['status'] for r in rows)),
            'policy': 'Preserve 2493 Fluent training and 651 validation rows. Exclude matches; quarantine all unresolved Noto rows until reviewed. No Noto rows currently cleared for new training.',
            'training_authorized': False, 'rows': rows}


if __name__ == '__main__':
    print(json.dumps(build(), indent=2))
