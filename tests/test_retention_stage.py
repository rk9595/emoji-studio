import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/retention_stage.py'
spec = importlib.util.spec_from_file_location('retention_stage', SCRIPT)
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)
IDENTITY = {'GITHUB_RUN_ID': '123', 'GITHUB_SHA': 'a'*40}
SECRET = 'private-token-DO-NOT-EMIT'


class StageTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.receipts = []

    def run_code(self, code, **kwargs):
        return stage.run_stage('registry_copy', [sys.executable, '-c', code], directory=str(self.root),
                               environment=IDENTITY, emit_receipt=self.receipts.append, **kwargs)

    def test_success_hides_stdout_stderr_and_argv(self):
        code = f'import sys; print({SECRET!r}); print("https://blob.invalid/?sig="+{SECRET!r},file=sys.stderr)'
        self.assertEqual(self.run_code(code), 0)
        serialized = json.dumps(self.receipts)
        self.assertNotIn(SECRET, serialized)
        self.assertNotIn('blob.invalid', serialized)
        self.assertNotIn(code, serialized)
        self.assertEqual([r['phase'] for r in self.receipts], ['started', 'finished'])
        self.assertEqual(self.receipts[-1]['classification'], 'success')
        self.assertEqual(self.receipts[-1]['exit_code'], 0)
        self.assertGreaterEqual(self.receipts[-1]['elapsed_ms'], 0)
        logs = list(self.root.glob('*.log'))
        self.assertEqual(len(logs), 1)
        self.assertEqual(stat.S_IMODE(logs[0].stat().st_mode), 0o600)
        self.assertIn(SECRET, logs[0].read_text())

    def test_failure_preserves_exit_and_fixed_hint_without_retry(self):
        marker = self.root/'calls'
        code = ('from pathlib import Path; import sys; '
                f'p=Path({str(marker)!r}); p.write_text(p.read_text()+"x" if p.exists() else "x"); '
                f'print("unauthorized https://registry.invalid/?sig={SECRET}"); sys.exit(7)')
        self.assertEqual(self.run_code(code), 7)
        self.assertEqual(marker.read_text(), 'x')
        self.assertEqual(self.receipts[-1]['classification'], 'authentication_or_access')
        self.assertNotIn(SECRET, json.dumps(self.receipts))

    def test_verifier_codes_are_allowlisted_never_reflected(self):
        for code in stage.VERIFIER_CODES:
            raw = json.dumps({'status':'failed','code':code}).encode()
            self.assertEqual(stage.classify(raw, 1), code)
        for code in (SECRET, ['unauthorized'], None, {'x':SECRET}):
            result = stage.classify(json.dumps({'status':'failed','code':code}).encode(), 1)
            self.assertNotIn(SECRET, result)
        self.assertEqual(stage.classify(b'{bad-json '+SECRET.encode(), 1), 'unclassified_failure')

    def test_hint_matching_and_tail_are_bounded(self):
        for expected, patterns in stage.HINTS:
            for pattern in patterns:
                with self.subTest(expected=expected, pattern=pattern):
                    self.assertEqual(stage.classify(pattern+b' '+SECRET.encode(), 1), expected)
        raw = b'unauthorized' + b'x'*(stage.TAIL_LIMIT+1)
        self.assertEqual(stage.classify(raw, 1), 'unclassified_failure')
        self.assertEqual(stage.classify(b'unauthorized', 0), 'success')

    def test_only_actual_wrapper_timeout_is_labelled_deadline_exceeded(self):
        self.assertEqual(stage.classify(b'', 124), 'unclassified_failure')
        self.assertEqual(stage.classify(b'unauthorized', 124, timed_out=True), 'stage_deadline_exceeded')
        with patch.dict(stage.STAGES, registry_copy=0.1):
            self.assertEqual(self.run_code('import time; time.sleep(60)'), 124)
        self.assertTrue(self.receipts[-1]['timed_out'])
        self.assertEqual(self.receipts[-1]['classification'], 'stage_deadline_exceeded')

    def test_timeout_kills_descendant_before_delayed_side_effect(self):
        marker = self.root/'unexpected'
        child = f'import time; from pathlib import Path; time.sleep(0.8); Path({str(marker)!r}).write_text("bad")'
        parent = f'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",{child!r}]); time.sleep(60)'
        with patch.dict(stage.STAGES, registry_copy=0.15):
            self.assertEqual(self.run_code(parent), 124)
        # An independent local clock process waits for the would-be child action.
        subprocess.run([sys.executable, '-c', 'import time; time.sleep(1)'], check=True)
        self.assertFalse(marker.exists())

    def test_spawn_error_and_signals_are_sanitized(self):
        result = stage.run_stage('registry_login', ['/nonexistent/'+SECRET], directory=str(self.root),
                                 environment=IDENTITY, emit_receipt=self.receipts.append)
        self.assertEqual(result, 127)
        self.assertEqual(self.receipts[-1]['classification'], 'process_start_failed')
        self.assertNotIn(SECRET, json.dumps(self.receipts))
        self.assertEqual(self.run_code('import os,signal; os.kill(os.getpid(),signal.SIGTERM)'), 143)
        self.assertEqual(self.receipts[-1]['classification'], 'process_signalled')

    def test_named_output_retains_json_privately_and_refuses_overwrite(self):
        self.assertEqual(self.run_code('print("{\\"tag\\":\\"safe\\"}")', output_name='preflight.json'), 0)
        self.assertEqual(json.loads((self.root/'preflight.json').read_text()), {'tag':'safe'})
        with patch.object(stage.subprocess, 'Popen') as spawn, self.assertRaises(FileExistsError):
            self.run_code('raise Exception()', output_name='preflight.json')
        spawn.assert_not_called()

    def test_unsafe_identity_stage_and_paths_never_execute(self):
        for environment in ({}, {**IDENTITY,'GITHUB_SHA':SECRET}, {**IDENTITY,'GITHUB_RUN_ID':'../x'}):
            with self.subTest(environment=environment), patch.object(stage.subprocess, 'Popen') as spawn:
                with self.assertRaises(ValueError):
                    stage.run_stage('registry_copy', ['unused'], directory=str(self.root), environment=environment)
                spawn.assert_not_called()
        for name in ('../outside.json', 'x.log', '/tmp/x.json', SECRET):
            with self.subTest(name=name), patch.object(stage.subprocess, 'Popen') as spawn:
                with self.assertRaises(ValueError):
                    self.run_code('pass', output_name=name)
                spawn.assert_not_called()
        with patch.object(stage.subprocess, 'Popen') as spawn, self.assertRaises(ValueError):
            stage.run_stage(SECRET, ['unused'], directory=str(self.root), environment=IDENTITY)
        spawn.assert_not_called()

    def test_symlink_output_and_directory_are_not_followed(self):
        target = self.root/'target'
        target.write_text('keep')
        (self.root/'linked.json').symlink_to(target)
        with patch.object(stage.subprocess, 'Popen') as spawn, self.assertRaises(FileExistsError):
            self.run_code('pass', output_name='linked.json')
        spawn.assert_not_called()
        alias = self.root/'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        with patch.object(stage.subprocess, 'Popen') as spawn, self.assertRaises(ValueError):
            stage.run_stage('registry_copy', ['unused'], directory=str(alias), environment=IDENTITY)
        spawn.assert_not_called()
        self.assertEqual(target.read_text(), 'keep')

    def test_cli_stdin_reaches_child_without_appearing_in_receipts(self):
        result = subprocess.run([sys.executable, str(SCRIPT), '--stage', 'registry_login', '--',
                                 sys.executable, '-c', 'import sys; value=sys.stdin.read(); print(value); '
                                 'sys.exit(0 if value.startswith("private-token") else 4)'],
                                env={**os.environ, **IDENTITY, 'RUNNER_TEMP':str(self.root)},
                                input=SECRET, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, '')
        self.assertNotIn(SECRET, result.stdout)
        self.assertEqual(len(result.stdout.splitlines()), 2)

    def test_cli_invalid_arguments_never_echo_values(self):
        result = subprocess.run([sys.executable, str(SCRIPT), '--stage', SECRET],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 125)
        self.assertEqual(result.stderr, '')
        self.assertNotIn(SECRET, result.stdout)
        self.assertIn('diagnostics_wrapper_failed', result.stdout)

    def test_closed_preflight_reaches_no_registry_client(self):
        code = ('import sys; '
                f'sys.path.insert(0,{str(ROOT / "scripts")!r}); '
                'import verify_ghcr_retention as v; value=v.proposal(); '
                'v.proposal=lambda: {**value,"publication_authorized":False}; '
                'sys.argv=["verify","preflight"]; v.main()')
        result = subprocess.run([sys.executable, str(SCRIPT), '--stage', 'preflight', '--',
                                 sys.executable, '-c', code],
                                env={**os.environ, **IDENTITY, 'RUNNER_TEMP':str(self.root)},
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        receipt = json.loads(result.stdout.splitlines()[-1].split('=',1)[1])
        self.assertEqual(receipt['classification'], 'publication_not_authorized')

    def test_large_diagnostic_reports_truncation_without_raw_bytes(self):
        self.assertEqual(self.run_code(f'import sys; print("x"*70000+{SECRET!r}); sys.exit(1)'), 1)
        self.assertTrue(self.receipts[-1]['diagnostic_tail_truncated'])
        self.assertEqual(self.receipts[-1]['classification'], 'unclassified_failure')
        self.assertNotIn(SECRET, json.dumps(self.receipts))

    def test_workflow_uses_all_stage_wrappers_without_broadening_bounds(self):
        workflow = (ROOT/'.github/workflows/amd-runtime-retain.yml').read_text()
        self.assertEqual(workflow, (ROOT/'ops/workflows/amd-runtime-retain.yml').read_text())
        for name in stage.STAGES:
            self.assertIn('--stage '+name+' ', workflow)
        self.assertEqual(stage.STAGES['registry_copy'], 600)
        self.assertEqual(stage.STAGES['fresh_pull'], 1200)
        self.assertIn('timeout-minutes: 45', workflow)
        self.assertIn('timeout-minutes: 30', workflow)
        self.assertEqual(workflow.count('skopeo copy --retry-times 0'), 1)
        self.assertIn('packages: read', workflow)
        self.assertNotIn('upload-artifact', workflow)
        self.assertNotIn('cat "$RUNNER_TEMP/registry-', workflow)


if __name__ == '__main__':
    unittest.main()
