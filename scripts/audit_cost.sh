#!/usr/bin/env bash
# Read-only inventory. No login, API enablement, deletion, or billing export setup.
set -euo pipefail
project=${LIFEMATE_PROJECT:-${GOOGLE_CLOUD_PROJECT:-}}
region=${LIFEMATE_REGION:-}
target=${LIFEMATE_TARGET:-}
refuse() { printf 'audit_cost: refusing: %s\n' "$*" >&2; exit 2; }
[[ -n "$project" ]] || refuse 'set LIFEMATE_PROJECT (or GOOGLE_CLOUD_PROJECT) explicitly'
[[ -n "$region" ]] || refuse 'set LIFEMATE_REGION explicitly'
[[ "$region" == asia-southeast1 ]] || refuse 'LIFEMATE_REGION must be asia-southeast1'
[[ -n "$target" ]] || refuse 'set LIFEMATE_TARGET explicitly'
[[ "$target" == lifemate ]] || refuse 'LIFEMATE_TARGET must be lifemate (the reviewed deployment)'
[[ "$project" =~ ^[a-z][a-z0-9-]{4,61}[a-z0-9]$ ]] || refuse 'invalid project ID'
command -v gcloud >/dev/null || refuse 'gcloud is required; authenticate separately'
command -v python3 >/dev/null || refuse 'python3 is required'
export LIFEMATE_PROJECT="$project"
python3 - <<'PY'
import datetime
import json
import os
import re
import subprocess
import sys

project = os.environ['LIFEMATE_PROJECT']
region = os.environ['LIFEMATE_REGION']
failed = False


def query(title, args):
    global failed
    print('\n## ' + title, flush=True)
    formatting = ['--json'] if args[:2] == ['storage', 'ls'] else ['--format=json']
    result = subprocess.run(['gcloud', *args, '--project', project, *formatting, '--quiet'],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode:
        failed = True
        print('UNVERIFIED: command failed; no empty-inventory or cleanup claim', flush=True)
        # CLI errors may include private resource details. Keep them in the approved terminal only.
        print(result.stderr.strip(), file=sys.stderr)
        return None
    try:
        value = json.loads(result.stdout)
    except ValueError:
        failed = True
        print('UNVERIFIED: command returned invalid JSON')
        return None
    print(json.dumps(value, indent=2, sort_keys=True), flush=True)
    return value


print('READ ONLY; selected project=%s region=%s target=lifemate observed_at=%s' %
      (project, region, datetime.datetime.now(datetime.timezone.utc).isoformat()))
print('Inventories include the whole project to expose unlabelled/orphaned spend; no cleanup is performed.')
query('Selected-region Batch jobs (terminal records are not proof of VM cleanup)',
      ['batch', 'jobs', 'list', '--location', region])
query('All project VMs (including other regions)', ['compute', 'instances', 'list'])
query('All persistent disks (users=[] means detached, not approved to delete)', ['compute', 'disks', 'list'])
query('All snapshots', ['compute', 'snapshots', 'list'])
query('Custom Compute images', ['compute', 'images', 'list', '--no-standard-images'])
query('Cloud Run services', ['run', 'services', 'list', '--region', region])
query('Dispatch queue retry/concurrency and backlog configuration',
      ['tasks', 'queues', 'describe', 'lifemate-dispatch', '--location', region])
query('Reconciliation schedule/status (does not execute it)',
      ['scheduler', 'jobs', 'describe', 'lifemate-reconcile', '--location', region])
repositories = query('Artifact Registry repositories', ['artifacts', 'repositories', 'list', '--location=all'])
for repository in repositories or []:
    name = repository.get('name', '')
    match = re.fullmatch(r'projects/([^/]+)/locations/([^/]+)/repositories/([^/]+)', name)
    if not match or match[1] != project:
        failed = True
        print('UNVERIFIED: unexpected repository identity')
        continue
    _, location, repo = match.groups()
    query('Registry retention/cleanup policy: ' + name,
          ['artifacts', 'repositories', 'describe', repo, '--location', location])
    if repository.get('format') == 'DOCKER':
        query('Docker image versions/tags: ' + name,
              ['artifacts', 'docker', 'images', 'list',
               '%s-docker.pkg.dev/%s/%s' % (location, project, repo), '--include-tags'])
buckets = query('All project buckets', ['storage', 'buckets', 'list'])
for bucket in buckets or []:
    name = bucket.get('name', '')
    if name.startswith('gs://'):
        name = name[5:].rstrip('/')
    if not re.fullmatch(r'[a-z0-9][a-z0-9._-]+[a-z0-9]', name):
        failed = True
        print('UNVERIFIED: unexpected bucket identity')
        continue
    uri = 'gs://' + name
    query('Bucket lifecycle/retention/soft-delete/versioning: ' + uri,
          ['storage', 'buckets', 'describe', uri])
    # Metadata only. No object content is read or downloaded, including organizer trees.
    query('Object generations, sizes, and storage classes: ' + uri,
          ['storage', 'ls', uri + '/**', '--all-versions'])
    query('Soft-deleted objects still retained: ' + uri,
          ['storage', 'objects', 'list', uri + '/**', '--soft-deleted', '--exhaustive'])
query('Billing linkage (not credit balance or a current invoice)', ['billing', 'projects', 'describe', project])
print('\n## Billing/report lag')
print('No BigQuery export is created or enabled. Linkage does not prove remaining credit, expiry, price, or zero spend.')
print('Cloud Billing usage reports/exports are delayed; new exports do not backfill all prior usage. Compare observed_at, usage_end_time, export_time, credits and adjustments before approving spend.')
table = os.environ.get('LIFEMATE_BILLING_EXPORT_TABLE', '')
if table:
    if not re.fullmatch(r'[a-z][a-z0-9-]*\.[A-Za-z0-9_]+\.gcp_billing_export_(?:resource_v1_|v1_)[A-Za-z0-9_]+', table):
        print('UNVERIFIED: invalid LIFEMATE_BILLING_EXPORT_TABLE', file=sys.stderr)
        failed = True
    elif not os.environ.get('LIFEMATE_BILLING_QUERY_APPROVED') == '1':
        print('UNVERIFIED: querying billing export can incur query charges; set LIFEMATE_BILLING_QUERY_APPROVED=1 after approval', file=sys.stderr)
        failed = True
    elif not os.environ.get('LIFEMATE_BILLING_LOCATION'):
        print('UNVERIFIED: set LIFEMATE_BILLING_LOCATION for the existing export dataset', file=sys.stderr)
        failed = True
    else:
        sql = '''SELECT CURRENT_TIMESTAMP() AS observed_at, MAX(usage_end_time) AS latest_usage_end,
MAX(export_time) AS latest_export_time,
TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), MAX(usage_end_time), HOUR) AS usage_lag_hours,
TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), MAX(export_time), HOUR) AS export_lag_hours,
SUM(cost) AS cost_before_credits,
SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS credits,
ANY_VALUE(currency) AS currency FROM `%s`
WHERE project.id = '%s' AND usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)''' % (table, project)
        print('\n## Existing billing export (last 30 days; maximum 1 GB query billed)')
        try:
            result = subprocess.run(['bq', '--project_id=' + project,
                                     '--location=' + os.environ['LIFEMATE_BILLING_LOCATION'],
                                     'query', '--use_legacy_sql=false', '--format=json',
                                     '--maximum_bytes_billed=1000000000', sql],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode:
                print(result.stderr.strip(), file=sys.stderr)
                failed = True
            else:
                report = json.loads(result.stdout)
                print(json.dumps(report, indent=2, sort_keys=True))
                if not report or not report[0].get('latest_usage_end') or not report[0].get('latest_export_time'):
                    print('UNVERIFIED: selected export contains no recent usage/export timestamp', file=sys.stderr)
                    failed = True
        except FileNotFoundError:
            print('UNVERIFIED: bq is not installed', file=sys.stderr)
            failed = True
else:
    print('Export lag UNVERIFIED: no existing LIFEMATE_BILLING_EXPORT_TABLE selected. Owner must check Billing Reports, credits/expiry and the report freshness manually.')
    failed = True
print('\n## Cleanup reconciliation')
print('Compare terminal Batch jobs against live VMs, disk users, snapshots, image versions, object generations and retained/soft-deleted bytes above. Empty inventories do not prove a zero invoice.')
print('Deletion/retention changes require a separate reviewed owner-approved action. This script never cancels, deletes, applies, enables APIs, or changes billing.')
if failed:
    print('audit_cost: incomplete inventory; at least one read was unverified', file=sys.stderr)
    sys.exit(1)
PY
