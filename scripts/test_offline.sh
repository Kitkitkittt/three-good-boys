#!/usr/bin/env bash
# Operator-selected launcher rehearsal, not an assertion of the official launcher contract.
set -euo pipefail
project=${LIFEMATE_PROJECT:-${GOOGLE_CLOUD_PROJECT:-}}
region=${LIFEMATE_REGION:-}
target=${LIFEMATE_TARGET:-}
refuse() { printf 'test_offline: refusing: %s\n' "$*" >&2; exit 2; }
[[ -n "$project" ]] || refuse 'set LIFEMATE_PROJECT (or GOOGLE_CLOUD_PROJECT) explicitly'
[[ -n "$region" ]] || refuse 'set LIFEMATE_REGION explicitly'
[[ "$region" == asia-southeast1 ]] || refuse 'LIFEMATE_REGION must be asia-southeast1'
[[ -n "$target" ]] || refuse 'set LIFEMATE_TARGET explicitly'
[[ "$target" == lifemate ]] || refuse 'LIFEMATE_TARGET must be lifemate (the reviewed deployment)'
[[ "$project" =~ ^[a-z][a-z0-9-]{4,61}[a-z0-9]$ ]] || refuse 'invalid project ID'
for name in LIFEMATE_OFFLINE_IMAGE LIFEMATE_OFFLINE_DATA LIFEMATE_OFFLINE_OUTPUT LIFEMATE_OFFLINE_OUTPUT_MOUNT LIFEMATE_OFFLINE_EXPECTED_IDS LIFEMATE_OFFLINE_APPROVAL; do
    [[ -n "${!name:-}" ]] || refuse "set $name explicitly"
done
[[ ${LIFEMATE_OFFLINE_RUN:-} == 1 ]] || refuse 'set LIFEMATE_OFFLINE_RUN=1 only after fixture, launcher and GPU execution approval'
[[ ${1:-} == -- ]] || refuse 'supply -- followed by the approved private launcher arguments (zero arguments allowed)'
shift
command -v docker >/dev/null || refuse 'docker is required'
command -v python3 >/dev/null || refuse 'python3 is required'
export LIFEMATE_PROJECT="$project"
python3 - "$@" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys


def refuse(message):
    print('test_offline: refusing: ' + message, file=sys.stderr)
    sys.exit(2)


image = os.environ['LIFEMATE_OFFLINE_IMAGE']
if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9./_:-]*@sha256:[0-9a-f]{64}', image):
    refuse('LIFEMATE_OFFLINE_IMAGE must be a full image reference pinned by sha256 digest, not a tag')
data = Path(os.environ['LIFEMATE_OFFLINE_DATA']).resolve(strict=True)
output = Path(os.environ['LIFEMATE_OFFLINE_OUTPUT']).resolve(strict=True)
expected_file = Path(os.environ['LIFEMATE_OFFLINE_EXPECTED_IDS']).resolve(strict=True)
if not data.is_dir() or not output.is_dir():
    refuse('data and output must be existing directories')
if data == output or data in output.parents or output in data.parents:
    refuse('data and output directories must not overlap')
if any(output.iterdir()):
    refuse('output must be empty; existing results must never be mistaken for this execution')
if ',' in str(data) or ',' in str(output):
    refuse('Docker bind paths cannot contain commas')
mount = os.environ['LIFEMATE_OFFLINE_OUTPUT_MOUNT']
if not re.fullmatch(r'/[A-Za-z0-9_./-]+', mount) or '..' in mount.split('/'):
    refuse('output mount must be an explicit safe absolute container directory')
mount_path = Path(mount)
if mount_path == Path('/data') or Path('/data') in mount_path.parents or mount_path == Path('/') or mount_path == Path('/tmp') or Path('/tmp') in mount_path.parents:
    refuse('output mount cannot shadow /data, /tmp, or the container root')
expected = json.loads(expected_file.read_text(encoding='utf-8'))
if (not isinstance(expected, list) or not expected or
        any(not isinstance(value, str) or not value for value in expected) or len(set(expected)) != len(expected)):
    refuse('expected IDs must be a nonempty JSON array of unique strings from permitted inputs, never environment files')
# No pull: registry login, downloads and image publication are separate approved actions.
info = json.loads(subprocess.check_output(['docker', 'image', 'inspect', image], text=True))[0]
if image not in info.get('RepoDigests', []):
    refuse('the local image does not attest the exact selected repository digest')
if info.get('Config', {}).get('Volumes'):
    refuse('image declares extra volumes; only the approved data/output host mounts are allowed')
if info.get('Config', {}).get('Entrypoint') != ['/opt/submission/launcher']:
    refuse('image entrypoint must match the reviewed private packaging contract /opt/submission/launcher')
command = ['docker', 'run', '--rm', '--pull=never', '--network', 'none', '--gpus', 'all',
           '--read-only', '--tmpfs', '/tmp:rw,nosuid,nodev,size=1g',
           '--mount', 'type=bind,src=%s,dst=/data,readonly' % data,
           '--mount', 'type=bind,src=%s,dst=%s' % (output, mount),
           '--env', 'HF_HUB_OFFLINE=1', '--env', 'TRANSFORMERS_OFFLINE=1',
           '--env', 'HF_DATASETS_OFFLINE=1', '--env', 'DO_NOT_TRACK=1', image, *sys.argv[1:]]
print('UNCONFIRMED official launcher/output mapping. Running only the explicitly approved private launcher contract.', flush=True)
print('Selected project=%s region=%s target=lifemate' % (os.environ['LIFEMATE_PROJECT'], os.environ['LIFEMATE_REGION']), flush=True)
print('No credential, home, or host model-cache mount; no cloud credentials passed.', flush=True)
print(shlex.join(command), flush=True)
subprocess.run(command, check=True)
# The operator mounts the directory expected to contain submission.jsonl. This does
# not claim that the absolute container path is organizer-confirmed.
submission = output / 'submission.jsonl'
if not submission.is_file() or submission.is_symlink():
    refuse('launcher did not write a regular submission.jsonl in the selected output mount')
rows = []
for number, line in enumerate(submission.read_text(encoding='utf-8').splitlines(), 1):
    try:
        row = json.loads(line)
    except ValueError:
        refuse('submission contains invalid JSON at line %d' % number)
    if not isinstance(row, dict) or set(row) != {'id', 'tool_calls', 'state_hash'}:
        refuse('submission row %d has missing or extra fields' % number)
    if (not isinstance(row['id'], str) or not isinstance(row['tool_calls'], list) or
            not isinstance(row['state_hash'], str) or not re.fullmatch(r'[0-9a-f]{64}', row['state_hash'])):
        refuse('submission row %d has invalid field types or hash shape' % number)
    rows.append(row)
ids = [row['id'] for row in rows]
if len(ids) != len(expected) or len(set(ids)) != len(ids) or set(ids) != set(expected):
    refuse('submission does not cover exactly the approved unique input IDs')
print(json.dumps({'image': image, 'records': len(rows),
                  'submission_sha256': hashlib.sha256(submission.read_bytes()).hexdigest(),
                  'network': 'none', 'gpus': 'all', 'launcher_status': 'operator-selected; official details unconfirmed'}))
print('Structural coverage only: same-session ToolEnv/hash integrity, official schema/scoring, A30 timing and deterministic replays still need separate exercised evidence.')
PY
