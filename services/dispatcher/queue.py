"""Cloud Tasks enqueue for dispatch creation and repair.

Split from ``google_adapters`` so the pure queue translation can be imported
without the Batch/Storage client libraries. The queue is the dispatch route's
own ingress: a task carries an OIDC token for the caller identity, which is what
lets an IAM-private Cloud Run dispatcher accept it without being publicly
invokable. No metadata call happens at import.
"""


class CloudTasksQueue:
    """One Cloud Tasks HTTP task per enqueue request.

    Retries are Cloud Tasks' job: the dispatch route is idempotent by identity,
    so a replayed task repairs rather than duplicates. The task's ``run_id``
    body is exactly the dispatch payload the route expects.
    """

    def __init__(self, url, service_account, client=None, project=None, location=None,
                 queue=None, audience=None):
        self.url = url
        self.service_account = service_account
        self.audience = audience or url
        self._client = client
        self._project = project
        self._location = location
        self._queue = queue

    def _queue_path(self):
        return f"projects/{self._project}/locations/{self._location}/queues/{self._queue}"

    def enqueue_dispatch(self, run_id):
        return self.enqueue({"run_id": run_id})

    def enqueue(self, payload):
        """Create the task; the OIDC token is minted by Cloud Tasks itself."""
        if self._client is None:
            from google.cloud import tasks_v2  # imported lazily on purpose

            self._client = tasks_v2.CloudTasksClient()
        task = {
            "http_request": {
                "http_method": "POST",
                "url": self.url,
                "headers": {"content-type": "application/json"},
                "body": _json_bytes(payload),
                "oidc_token": {
                    "service_account_email": self.service_account,
                    "audience": self.audience,
                },
            }
        }
        return self._client.create_task(parent=self._queue_path(), task=task)


def _json_bytes(payload):
    import json

    return json.dumps(payload).encode()
