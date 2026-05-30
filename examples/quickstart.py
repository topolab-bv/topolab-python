"""Runnable quickstart. Set TOPOLAB_API_KEY (org-scoped) to run against staging.

Falls back to printing the catalog if the key lacks the API_ACCESS addon.
"""
from topolab import Client, AddonRequiredError

tl = Client()  # reads TOPOLAB_API_KEY
print("Datasets:", [d.table for d in tl.datasets.list(limit=5).data])
try:
    path = tl.dataset("nl-domino-poi").download("dominos-nl.geojson")
    print("Saved", path)
except AddonRequiredError as e:
    print("Need addon:", e.addon)
