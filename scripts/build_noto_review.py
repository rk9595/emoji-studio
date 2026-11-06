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
        cards = [card.replace('<h3>', '<h3>') for card in cards]
        sections.append(f'<section data-pair="{html.escape(pair)}"><h2>{pair}</h2><p>{html.escape(row["prompt"])}</p><ul>{criteria}</ul><div class="grid">{"".join(cards)}</div><fieldset><legend>Score each image</legend>' + ''.join(f'<label>{label}: <select data-score="{label}"><option value="">Choose</option><option value="0">0 — major failure</option><option value="1">1 — partial / unsure</option><option value="2">2 — meets criteria</option></select></label>' for label in 'ABC') + '<label>Notes <input data-notes type="text" placeholder="Optional"></label></fieldset></section>')
    page = '''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Saved emoji comparison</title>
    <style>body{font:16px system-ui;max-width:1300px;margin:30px auto;padding:16px;background:#eee}section{background:white;padding:20px;margin:30px 0;border-radius:10px}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}img{width:100%;border-radius:6px}.thumb{display:block;width:32px;height:32px;margin:12px}h3{margin:0}fieldset{display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin-top:18px;padding:14px}select,input,button{font:inherit;padding:8px}header{position:sticky;top:0;background:#fff;padding:12px;z-index:2;border-radius:10px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}</style>
    <h1>Retrospective emoji comparison</h1><p>For each prompt, compare A/B/C with the criteria. Choose a score for each: 0 = major failure, 1 = partial or unsure, 2 = meets the requested details. Labels are shuffled for every prompt. This development review compares separate runs; prior exposure means it is not a fully blinded AI review.</p>
    <header><button id="export">Download scores</button><button id="clear">Clear scores</button><span id="progress"></span><span>Scores save automatically in this browser.</span></header>'''
    page += ''.join(sections) + '''<script>
    const key='noto-review-v1'; let saved={}; try{saved=JSON.parse(localStorage.getItem(key)||'{}')}catch{}
    const sections=[...document.querySelectorAll('section[data-pair]')];
    function render(){let done=0; for(const s of sections){const x=saved[s.dataset.pair]||{}; for(const q of s.querySelectorAll('[data-score]'))q.value=x[q.dataset.score]??''; s.querySelector('[data-notes]').value=x.notes||''; if('A'in x&&'B'in x&&'C'in x)done++} document.querySelector('#progress').textContent=`${done}/${sections.length} groups scored`}
    function collect(){for(const s of sections){const x=saved[s.dataset.pair]||{}; for(const q of s.querySelectorAll('[data-score]')){if(q.value)x[q.dataset.score]=Number(q.value);else delete x[q.dataset.score]} x.notes=s.querySelector('[data-notes]').value; saved[s.dataset.pair]=x} localStorage.setItem(key,JSON.stringify(saved));render()}
    document.addEventListener('change',collect); document.addEventListener('input',e=>{if(e.target.matches('[data-notes]'))collect()}); render();
    document.querySelector('#export').onclick=()=>{collect(); const blob=new Blob([JSON.stringify({reviewer:'human',method:'manual criterion scoring; retrospective shuffled comparison',observations:saved},null,2)],{type:'application/json'}); const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='noto-review-scores.json';a.click();URL.revokeObjectURL(a.href)};
    document.querySelector('#clear').onclick=()=>{if(confirm('Clear all saved scores?')){saved={};localStorage.removeItem(key);render()}};
    </script>'''
    (output / 'index.html').write_text(page)
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
