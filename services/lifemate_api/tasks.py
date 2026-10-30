"""Cloud Tasks enqueue adapter for the persisted dispatch intent.

Thin and injected: the real client is built lazily, so tests inject a fake and
the module imports without credentials. The queue name and target route are
deployment configuration, not request input.
"""
import json


class CloudTasksEnqueuer:
    """Enqueues one HTTP task per dispatch intent onto the dispatch queue."""

    def __init__(self, client=None, project=None, location=None, queue=None, dispatch_url=None,
                 service_account=None, audience=None):
        self._client = client
        self._project = project
        self._location = location
        self._queue = queue
        self._dispatch_url = dispatch_url
        self._service_account = service_account
        self._audience = audience

    def _queue_path(self):
        return f"projects/{self._project}/locations/{self._location}/queues/{self._queue}"

    def enqueue(self, intent):
        """Create a Cloud Task that POSTs the run's dispatch intent."""
        client = self._client
        if client is None:
            from google.cloud import tasks_v2  # imported lazily; not a test dependency

            client = tasks_v2.CloudTasksClient()
        payload = {"run_id": intent.run_id, "attempt": intent.attempt, "job_id": intent.job_id}
        task = {
            "http_request": {
                "http_method": "POST",
                "url": self._dispatch_url,
                "headers": {"content-type": "application/json"},
                "body": json.dumps(payload).encode(),
                "oidc_token": {
                    "service_account_email": self._service_account,
                    "audience": self._audience,
                },
            }
        }
        return client.create_task(parent=self._queue_path(), task=task)


class RecordingEnqueuer:
    """Test double: records intents and can be told to fail."""

    def __init__(self, fail=False):
        self.enqueued = []
        self.fail = fail

    def enqueue(self, intent):
        if self.fail:
            raise RuntimeError("queue unavailable")
        self.enqueued.append(intent)
        return intent
