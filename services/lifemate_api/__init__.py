"""Private API surface: IAP assertion verification, role mapping, run views.

The domain (request identity, lifecycle, roles) lives in ``lifemate_cloud``; this
package only turns HTTP requests into domain calls. Real Firestore and Cloud Tasks
adapters live beside it and import their Google clients lazily, never at import.
"""
