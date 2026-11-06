"""Report exact normalized concept overlap; aliases require separate review."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def audit():
    manifest = json.loads((ROOT / 'data/training/fluent-noto-v1/manifest.json').read_text())
    normalize = lambda name: re.sub('[^a-z0-9]', '', name.lower())
    validation = {}
    for row in manifest['rows']:
        if row['included'] and row['split'] == 'validation' and 'codepoint' not in row:
            validation.setdefault(normalize(row['concept']), []).append(row['asset_id'])
    matches = []
    for row in manifest['rows']:
        if 'codepoint' not in row or not row['included'] or row['split'] != 'train':
            continue
        concept = row['caption'].split(', noto')[0]
        if normalize(concept) in validation:
            matches.append({'noto_asset_id': row['asset_id'], 'concept': concept,
                            'fluent_validation_asset_ids': validation[normalize(concept)]})
    return {'method': 'lowercase names, remove non-ASCII alphanumeric characters',
            'limitation': 'Exact-name lower bound; synonyms and visual equivalence are not covered.',
            'overlapping_noto_assets': len(matches), 'matches': matches}


if __name__ == '__main__':
    print(json.dumps(audit(), indent=2))
