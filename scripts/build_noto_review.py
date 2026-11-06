"""Build a private shuffled retrospective gallery from verified saved outputs."""
import argparse
import html
import json
import random
import shutil
from pathlib import Path

from audit_noto_comparison import audit, digest


def build(baseline, candidate, output):
    root = Path(__file__).resolve().parents[1]
    verified = audit(baseline, candidate, root)
    old = json.loads((baseline / 'report.json').read_text())
    new = json.loads((candidate / 'report.json').read_text())
    prompts = {p['id']: p for p in json.loads((root / 'benchmarks/collection-eval.json').read_text())['prompts']}
    rows = {(r['condition'], r['prompt'], r['seed']): r for r in old['images']}
    output.mkdir(parents=True, exist_ok=False)
    assets = output / 'assets'
    assets.mkdir()
    mapping, sections = {}, []
    rng = random.Random(verified['candidate_report_sha256'])
    for index, row in enumerate(new['images']):
        choices = [('step-656', candidate / row['file'])]
        choices += [(c, baseline / rows[c, row['prompt'], row['seed']]['image']) for c in ('base', 'pilot-25')]
        rng.shuffle(choices)
        pair = f"{row['prompt_id']}-seed-{row['seed']}"
        mapping[pair] = {}
        cards = []
        for label, (condition, source) in zip('ABC', choices):
            filename = f'{index:02d}-{label}.png'
            shutil.copyfile(source, assets / filename)
            mapping[pair][label] = {'condition': condition, 'sha256': digest(source)}
            cards.append(f'<article><h3>{label}</h3><img src="assets/{filename}" alt="Candidate {label}"><img class="thumb" src="assets/{filename}" alt="32 pixel thumbnail"></article>')
        criteria = ''.join(f'<li>{html.escape(c)}</li>' for c in prompts[row['prompt_id']]['criteria'])
        sections.append(f'<section><h2>{pair}</h2><p>{html.escape(row["prompt"])}</p><ul>{criteria}</ul><div class="grid">{"".join(cards)}</div></section>')
    page = '''<!doctype html><meta charset="utf-8"><title>Saved emoji comparison</title>
    <style>body{font:16px system-ui;max-width:1300px;margin:30px auto;padding:16px;background:#eee}section{background:white;padding:20px;margin:30px 0}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}img{width:100%}.thumb{display:block;width:32px;height:32px;margin:12px}h3{margin:0}</style>
    <h1>Retrospective emoji comparison</h1><p>24 prompt/seed groups; labels shuffled separately per group. Score each A/B/C before opening map.json: 0 = major failure, 1 = partial or uncertain, 2 = requested details met. Record uncertainty. This is a development diagnostic across separate runs; dependency equivalence is not established. Prior exposure to images prevents a claim of fully blinded AI review.</p>'''
    (output / 'index.html').write_text(page + ''.join(sections))
    (output / 'map.json').write_text(json.dumps(mapping, indent=2) + '\n')
    (output / 'audit.json').write_text(json.dumps(verified, indent=2) + '\n')
    (output / 'observations-template.json').write_text(json.dumps({
        'reviewer': None, 'method': None,
        'observations': {pair: {'scores_ABC': [None, None, None], 'notes': ''} for pair in mapping}
    }, indent=2) + '\n')
    return {'groups': len(mapping), 'images': sum(len(v) for v in mapping.values()),
            'gallery': str(output / 'index.html'), 'map_sha256': digest(output / 'map.json')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.baseline, args.candidate, args.output), indent=2))
