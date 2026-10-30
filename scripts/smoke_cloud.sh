#!/usr/bin/env bash
# Read-only probes by default. Submission/cancellation/reconciliation are opt-in.
set -euo pipefail
project=${LIFEMATE_PROJECT:-${GOOGLE_CLOUD_PROJECT:-}}
region=${LIFEMATE_REGION:-}
target=${LIFEMATE_TARGET:-}
refuse() { printf 'smoke_cloud: refusing: %s\n' "$*" >&2; exit 2; }
[[ -n "$project" ]] || refuse 'set LIFEMATE_PROJECT (or GOOGLE_CLOUD_PROJECT) explicitly'
[[ -n "$region" ]] || refuse 'set LIFEMATE_REGION explicitly'
[[ "$region" == asia-southeast1 ]] || refuse 'LIFEMATE_REGION must be asia-southeast1'
[[ -n "$target" ]] || refuse 'set LIFEMATE_TARGET explicitly'
[[ "$target" == lifemate ]] || refuse 'LIFEMATE_TARGET must be lifemate (the reviewed deployment)'
[[ "$project" =~ ^[a-z][a-z0-9-]{4,61}[a-z0-9]$ ]] || refuse 'invalid project ID'
for name in LIFEMATE_API_URL LIFEMATE_WEB_URL LIFEMATE_API_ID_TOKEN LIFEMATE_WEB_ID_TOKEN LIFEMATE_IAP_ASSERTION; do
    [[ -n "${!name:-}" ]] || refuse "set $name explicitly"
done
command -v python3 >/dev/null || refuse 'python3 is required'
command -v gcloud >/dev/null || refuse 'gcloud is required for read-only selected-service identity checks'
export LIFEMATE_PROJECT="$project"
python3 - <<'PY'
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


def refuse(message):
    print('smoke_cloud: refusing: ' + message, file=sys.stderr)
    sys.exit(2)


def required(name):
    value = os.environ.get(name, '')
    if not value:
        refuse('set ' + name + ' explicitly')
    return value


def base_url(name):
    value = required(name).rstrip('/')
    url = urllib.parse.urlsplit(value)
    if url.scheme != 'https' or not url.netloc or url.username or url.password or url.query or url.fragment or url.path:
        refuse(name + ' must be an explicit HTTPS service origin without credentials, path or query')
    return value


api = base_url('LIFEMATE_API_URL')
web = base_url('LIFEMATE_WEB_URL')
project = os.environ['LIFEMATE_PROJECT']
region = os.environ['LIFEMATE_REGION']
submit = os.environ.get('LIFEMATE_SMOKE_SUBMIT', '0')
cancel = os.environ.get('LIFEMATE_SMOKE_CANCEL', '0')
reconcile = os.environ.get('LIFEMATE_SMOKE_RECONCILE', '0')
if any(value not in ('0', '1') for value in (submit, cancel, reconcile)):
    refuse('LIFEMATE_SMOKE_SUBMIT/CANCEL/RECONCILE must be 0 or 1')
if submit != '1' and (cancel == '1' or reconcile == '1'):
    refuse('cancellation/reconciliation require LIFEMATE_SMOKE_SUBMIT=1')
if submit == '1':
    required('LIFEMATE_SMOKE_APPROVAL')
    if os.environ.get('LIFEMATE_SMOKE_SYNTHETIC') != '1':
        refuse('set LIFEMATE_SMOKE_SYNTHETIC=1 only for the approved synthetic catalog entries')
    experiment = required('LIFEMATE_SMOKE_EXPERIMENT_ID')
    dataset = required('LIFEMATE_SMOKE_DATASET_ID')
    model = required('LIFEMATE_SMOKE_MODEL_ID')
    key = required('LIFEMATE_SMOKE_IDEMPOTENCY_KEY')
    bucket = required('LIFEMATE_SMOKE_RESULTS_BUCKET')
    prefix_template = required('LIFEMATE_SMOKE_RESULT_PREFIX')
    worker_image = required('LIFEMATE_SMOKE_WORKER_IMAGE')
    if not re.fullmatch(re.escape(region) + r'-docker\.pkg\.dev/' + re.escape(project) + r'/lifemate-images/[A-Za-z0-9_./-]+@sha256:[0-9a-f]{64}', worker_image):
        refuse('worker image must be a same-project immutable digest in the reviewed regional lifemate-images repository')
    if not re.fullmatch(r'[a-z0-9][a-z0-9._-]+[a-z0-9]', bucket):
        refuse('invalid results bucket name')
    if prefix_template.count('{run_id}') > 1 or not prefix_template.endswith('/') or prefix_template.startswith('/'):
        refuse('result prefix must be the reviewed RESULT_PREFIX, end with /, and optionally contain one {run_id}')
    if not re.fullmatch(r'[A-Za-z0-9_./{}-]+', prefix_template) or '..' in prefix_template.split('/') or '{' in prefix_template.replace('{run_id}', '') or '}' in prefix_template.replace('{run_id}', ''):
        refuse('unsafe result object prefix')
    expected = json.loads(required('LIFEMATE_SMOKE_EXPECTED_NAMES_JSON'))
    if (not isinstance(expected, list) or not expected or
            any(not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./-]*', name) or '..' in name.split('/') for name in expected) or
            len(set(expected)) != len(expected)):
        refuse('expected names must be the nonempty unique server-approved artifact-name JSON array')
    timeout = int(os.environ.get('LIFEMATE_SMOKE_TIMEOUT_SECONDS', '900'))
    if not 1 <= timeout <= 7200:
        refuse('smoke timeout must be 1..7200 seconds; this is not a job cancellation or cost cap')
    if reconcile == '1':
        machine = base_url('LIFEMATE_DISPATCHER_URL')
        required('LIFEMATE_MACHINE_ID_TOKEN')
    # Fail before submission if the read-only Batch/GCS client is unavailable.
    import shutil
    if shutil.which('gcloud') is None:
        refuse('gcloud is required for actual Batch and generation-pinned result reads')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    # Never forward bearer credentials to a login page or another origin.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


opener = urllib.request.build_opener(NoRedirect())


def selected_service(name, selected_url):
    result = subprocess.run(['gcloud', 'run', 'services', 'describe', name,
                             '--region', region, '--project', project, '--format=json', '--quiet'],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        refuse('cannot read the explicitly selected Cloud Run service ' + name)
    service = json.loads(result.stdout)
    actual = service.get('status', {}).get('url') or service.get('uri')
    if actual != selected_url:
        refuse('selected URL does not match Cloud Run ' + name + ' in the selected project/region')


selected_service('lifemate-api', api)
selected_service('lifemate-web', web)
if reconcile == '1':
    selected_service('lifemate-dispatcher', machine)


def request(base, path, method='GET', body=None, machine_call=False, web_call=False, idempotency=None):
    token = os.environ['LIFEMATE_MACHINE_ID_TOKEN'] if machine_call else os.environ['LIFEMATE_WEB_ID_TOKEN' if web_call else 'LIFEMATE_API_ID_TOKEN']
    headers = {'Authorization': 'Bearer ' + token}
    if not machine_call and not web_call:
        headers['x-goog-iap-jwt-assertion'] = os.environ['LIFEMATE_IAP_ASSERTION']
    if idempotency:
        headers['idempotency-key'] = idempotency
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with opener.open(req, timeout=45) as response:
            content = response.read()
            if web_call:
                if response.status != 200 or 'text/html' not in response.headers.get('Content-Type', ''):
                    raise RuntimeError('web route did not return HTML 200')
                return None
            return response.status, json.loads(content)
    except urllib.error.HTTPError as exc:
        # Do not print response bodies, tokens, assertions, or arbitrary application errors.
        raise RuntimeError('%s %s returned HTTP %s; no success claimed' % (method, path, exc.code)) from None


print('Selected project=%s region=%s target=lifemate; mode=%s' % (project, region, 'approved synthetic mutation' if submit == '1' else 'read-only'), flush=True)
request(web, '/', web_call=True)
code, health = request(api, '/healthz')
if health != {'status': 'ok'}:
    raise RuntimeError('unexpected actual /healthz response')
_, identity = request(api, '/api/me')
if identity.get('role') not in ('owner', 'maintainer', 'researcher', 'viewer'):
    raise RuntimeError('actual /api/me did not return an approved role')
_, catalog = request(api, '/api/models')
_, run_list = request(api, '/api/runs')
if not isinstance(run_list.get('runs'), list) or not isinstance(catalog.get('models'), list) or not isinstance(catalog.get('datasets'), list):
    raise RuntimeError('unexpected actual catalog/run-list response')
print('Actual web / and API /healthz, /api/me, /api/models, /api/runs responded; role=' + identity['role'], flush=True)
if submit != '1':
    print('READ ONLY: no experiment/run/task/job created, cancellation requested, or reconciliation invoked. This does not prove GPU execution, denied-user behavior, or results.')
    sys.exit(0)
if identity['role'] == 'viewer':
    refuse('viewer cannot submit a run')
if dataset not in {item['id'] for item in catalog['datasets']} or model not in {item['id'] for item in catalog['models']}:
    refuse('selected synthetic dataset/model are not in the actual approved catalog')
body = {'dataset_id': dataset, 'model_id': model, 'decoding': {}}
route = '/api/experiments/' + urllib.parse.quote(experiment, safe='') + '/runs'
status, run = request(api, route, method='POST', body=body, idempotency=key)
run_id = run.get('run_id')
if status != 202 or not isinstance(run_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', run_id):
    raise RuntimeError('submission was not durable HTTP 202 with a safe run_id')
print('Durably accepted run_id=' + run_id + '; no automatic cleanup or resubmission on failure', flush=True)
status, duplicate = request(api, route, method='POST', body=body, idempotency=key)
if status != 202 or duplicate.get('run_id') != run_id:
    raise RuntimeError('duplicate same-key submission did not preserve the run identity')


def gcloud(*args, binary=False):
    result = subprocess.run(['gcloud', *args, '--project', project, '--quiet'],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError('actual gcloud read failed; inspect authorized CLI logs separately, no success claimed')
    return result.stdout if binary else json.loads(result.stdout)


def object_bytes(uri):
    metadata = gcloud('storage', 'objects', 'describe', uri, '--format=json')
    generation = str(metadata.get('generation', ''))
    if not generation.isdigit() or int(generation) < 1:
        raise RuntimeError('result manifest has no pinned object generation')
    return gcloud('storage', 'cat', uri + '#' + generation, binary=True), generation


def verify_results():
    prefix = prefix_template.replace('{run_id}', run_id)
    raw, generation = object_bytes('gs://' + bucket + '/manifests/' + run_id + '.json')
    manifest = json.loads(raw)
    if manifest.get('run_id') != run_id or len(manifest.get('required', [])) != len(expected) or set(manifest.get('required', [])) != set(expected):
        raise RuntimeError('actual final manifest does not match run identity and server-approved coverage')
    entries = manifest.get('entries', [])
    if len(entries) != len(expected) or {entry.get('name') for entry in entries} != set(expected):
        raise RuntimeError('actual final manifest contains missing, duplicate or extra artifact entries')
    for entry in entries:
        generation_pin = entry.get('generation')
        digest = entry.get('checksum')
        if (isinstance(generation_pin, bool) or not isinstance(generation_pin, int) or generation_pin < 1 or
                not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest)):
            raise RuntimeError('invalid generation/checksum pin in actual result manifest')
        content = gcloud('storage', 'cat', 'gs://' + bucket + '/' + prefix + entry['name'] + '#' + str(generation_pin), binary=True)
        if hashlib.sha256(content).hexdigest() != digest or (entry.get('size') is not None and entry['size'] != len(content)):
            raise RuntimeError('actual generation-pinned artifact checksum/size mismatch')
    print('Verified actual final manifest generation=%s sha256=%s and %d pinned result objects (synthetic bytes not printed).' %
          (generation, hashlib.sha256(raw).hexdigest(), len(entries)), flush=True)


deadline = time.monotonic() + timeout
seen_job = None
last_state = None
cancel_sent = False
while time.monotonic() < deadline:
    if reconcile == '1':
        request(machine, '/internal/reconcile', method='POST', body={'run_id': run_id}, machine_call=True)
    _, detail = request(api, '/api/runs/' + run_id)
    _, failures = request(api, '/api/runs/' + run_id + '/failures')
    jobs = gcloud('batch', 'jobs', 'list', '--location', region, '--filter=labels.run-id=' + run_id, '--format=json')
    if len(jobs) > 1:
        raise RuntimeError('more than one actual Batch job for the run; stop admission and investigate')
    batch_state = None
    if jobs:
        job = gcloud('batch', 'jobs', 'describe', jobs[0]['name'].rsplit('/', 1)[-1], '--location', region, '--format=json')
        uid = job.get('uid')
        if not uid or (seen_job is not None and seen_job != (job['name'], uid)):
            raise RuntimeError('actual Batch identity missing or changed while polling')
        seen_job = (job['name'], uid)
        batch_state = job.get('status', {}).get('state')
        images = [runnable.get('container', {}).get('imageUri')
                  for group in job.get('taskGroups', []) for runnable in group.get('taskSpec', {}).get('runnables', [])]
        if worker_image not in images:
            raise RuntimeError('actual Batch job does not run the exact approved worker image digest')
        if cancel == '1' and not cancel_sent:
            request(api, '/api/runs/' + run_id + '/cancel', method='POST', body={})
            cancel_sent = True
            print('Cancellation intent requested against the observed job; terminal cancellation is not yet proven.', flush=True)
    state = detail.get('state')
    observation = (state, batch_state)
    if observation != last_state:
        print('Observed run=%s api=%s actual_batch=%s' % (run_id, state, batch_state or 'not observed'), flush=True)
        last_state = observation
    if state == 'SUCCEEDED':
        if seen_job is None or batch_state != 'SUCCEEDED':
            raise RuntimeError('API success is not backed by actual Batch success')
        verify_results()
        print('Synthetic API acceptance, web route probe, duplicate identity, actual Batch completion and pinned results verified. This does not prove browser submission, real SDK inference, recovery, A30 limits or denied-user behavior.')
        sys.exit(0)
    if state == 'CANCELED' and cancel == '1':
        if seen_job is None or batch_state not in ('CANCELLED', 'CANCELED', 'FAILED', 'DELETED'):
            raise RuntimeError('API cancellation is not backed by an observed terminal Batch outcome; pre-create cancellation needs separate ledger/slot inspection')
        print('Cancellation terminal outcome observed; no result-success claim. Run audit_cost.sh to reconcile VM/disk cleanup.')
        sys.exit(0)
    if state in ('FAILED', 'CANCELED'):
        raise RuntimeError('actual run terminated ' + str(state) + '; inspect redacted /failures and approved logs')
    time.sleep(10)
raise RuntimeError('poll timeout for run ' + run_id + '; the run may still incur charges. No hidden cancellation was performed; use the authorized cancel route, reconcile Batch identity, then audit_cost.sh')
PY
