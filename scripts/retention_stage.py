"""Run one retention stage; print only fixed-schema diagnostics, never raw output.

This helper grants no execution authority. The workflow must pass its publication
preflight before any write stage. It has no retry loop and preserves failures.
"""

import argparse
import json
import os
import re
import signal
import stat
import subprocess
import tempfile
import time
from pathlib import Path

# Keep the reviewed command deadlines; do not turn diagnostics into extra time.
STAGES = {
    'preflight': 120,
    'publish_preflight': 120,
    'registry_login': 60,
    'registry_copy': 600,
    'metadata_verify': 180,
    'fresh_metadata_verify': 180,
    'fresh_registry_login': 60,
    'fresh_pull': 1200,
    'final_verify': 180,
}
TAIL_LIMIT = 65536
VERIFIER_CODES = frozenset({
    'publication_not_authorized', 'pricing_recheck_required', 'unapproved_run_identity',
    'retention_scope_changed', 'retention_limits_changed', 'credentials_missing',
    'package_lookup_failed', 'private_package_identity_mismatch', 'unexpected_package_versions',
    'token_request_failed', 'manifest_digest_mismatch', 'config_identity_mismatch',
    'config_digest_mismatch', 'wrong_platform', 'anonymous_access_not_denied',
    'registry_transport_failed', 'redirect_denied', 'redirect_limit', 'read_deadline',
    'response_too_large', 'invalid_expected_digest', 'image_size_exceeded',
    'retention_check_failed',
})
HINTS = (
    ('disk_capacity', (b'no space left on device', b'disk quota exceeded')),
    ('authentication_or_access', (b'unauthorized', b'authentication required', b'denied:', b'forbidden')),
    ('rate_limited', (b'too many requests', b'toomanyrequests')),
    ('transport_timeout', (b'context deadline exceeded', b'i/o timeout', b'tls handshake timeout')),
    ('transport_connection', (b'connection reset', b'connection refused', b'no such host')),
    ('digest_or_size', (b'digest mismatch', b'size mismatch')),
)


def classify(raw, returncode, *, timed_out=False, spawn_failed=False):
    """Untrusted diagnostics yield enum hints only; text matches are not proof."""
    if timed_out:
        return 'stage_deadline_exceeded'
    if spawn_failed:
        return 'process_start_failed'
    if returncode == 0:
        return 'success'
    if returncode < 0:
        return 'process_signalled'
    tail = raw[-TAIL_LIMIT:]
    try:
        value = json.loads(tail)
        if (type(value) is dict and value.get('status') == 'failed'
                and type(value.get('code')) is str and value['code'] in VERIFIER_CODES):
            return value['code']
    except (ValueError, UnicodeError):
        pass
    lower = tail.lower()
    for category, needles in HINTS:
        if any(needle in lower for needle in needles):
            return category
    return 'unclassified_failure'


def identity(environment):
    run_id, head = environment.get('GITHUB_RUN_ID', ''), environment.get('GITHUB_SHA', '')
    if (not re.fullmatch(r'[1-9][0-9]{0,19}', run_id)
            or not re.fullmatch(r'[0-9a-f]{40}', head)):
        raise ValueError('invalid_identity')
    return {'run_id': run_id, 'source_commit': head}


def emit(value):
    print('RETENTION_STAGE_RECEIPT=' + json.dumps(value, sort_keys=True), flush=True)


def private_output(directory, output_name):
    root = Path(directory)
    if not root.is_absolute() or any(p.is_symlink() for p in (root, *root.parents)) or not root.is_dir():
        raise ValueError('invalid_private_directory')
    if output_name is not None:
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,63}\.json', output_name):
            raise ValueError('invalid_output_name')
        return os.open(root / output_name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    fd, _ = tempfile.mkstemp(prefix='retention-stage-', suffix='.log', dir=root)
    return fd


def _stop_group(process):
    # Kill the group, including children that survive after their leader exits.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=5)


def run_stage(stage, command, *, directory, environment, output_name=None, emit_receipt=emit):
    if stage not in STAGES or not command or not all(type(part) is str for part in command):
        raise ValueError('invalid_stage_command')
    base = {'schema_version': 1, 'stage': stage, 'timeout_seconds': STAGES[stage], **identity(environment)}
    # Refuse pre-existing/symlink output paths before executing anything. Raw logs
    # remain private in disposable runner storage and are never emitted/uploaded.
    fd = private_output(directory, output_name)
    try:
        require_mode = stat.S_IMODE(os.fstat(fd).st_mode)
        if require_mode != 0o600:
            raise ValueError('invalid_log_mode')
        with os.fdopen(fd, 'w+b') as log:
            fd = None
            emit_receipt({**base, 'phase': 'started'})
            started = time.monotonic()
            timed_out = spawn_failed = False
            process = None
            try:
                process = subprocess.Popen(command, stdin=None, stdout=log, stderr=log,
                                           start_new_session=True)
                try:
                    returncode = process.wait(timeout=STAGES[stage])
                except subprocess.TimeoutExpired:
                    timed_out = True
                    _stop_group(process)
                    returncode = 124
            except OSError:
                if process is not None:
                    _stop_group(process)
                    raise
                spawn_failed = True
                returncode = 127
            except BaseException:
                if process is not None:
                    _stop_group(process)
                raise
            elapsed_ms = max(0, min(round((time.monotonic() - started) * 1000), 86400000))
            log.seek(0, os.SEEK_END)
            size = log.tell()
            log.seek(max(0, size - TAIL_LIMIT))
            raw = log.read(TAIL_LIMIT)
            emit_receipt({**base, 'phase': 'finished', 'elapsed_ms': elapsed_ms,
                          'exit_code': returncode, 'timed_out': timed_out,
                          'classification': classify(raw, returncode, timed_out=timed_out,
                                                     spawn_failed=spawn_failed),
                          'classification_is_hint': True, 'diagnostic_tail_truncated': size > TAIL_LIMIT})
            return returncode if returncode >= 0 else 128 + min(-returncode, 127)
    finally:
        if fd is not None:
            os.close(fd)


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally echoes invalid input, which could contain secrets.
        raise ValueError('invalid_arguments')


def main():
    parser = SafeParser(description=__doc__)
    parser.add_argument('--stage', choices=STAGES, required=True)
    parser.add_argument('--output-name')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    try:
        args = parser.parse_args()
        command = args.command[1:] if args.command[:1] == ['--'] else args.command
        result = run_stage(args.stage, command, directory=os.environ.get('RUNNER_TEMP', ''),
                           environment=os.environ, output_name=args.output_name)
    except Exception:
        # No traceback, argv, paths, environment, process exception or raw logs.
        emit({'schema_version': 1, 'phase': 'wrapper_failed', 'classification': 'diagnostics_wrapper_failed'})
        result = 125
    raise SystemExit(result)


if __name__ == '__main__':
    main()
