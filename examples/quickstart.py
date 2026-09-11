"""Runnable quickstart. Set TOPOLAB_API_KEY (org-scoped) to run it.

Prints the catalog, then walks everything the organization licences and pulls
the newest archive of the first entry. Add-on gaps are reported, not fatal.
"""
from topolab import AddonRequiredError, Client, NotFoundError

tl = Client()  # reads TOPOLAB_API_KEY
print("Datasets:", [d.table for d in tl.datasets.list(limit=5).data])

try:
    page = tl.datasets.owned(limit=5)
    print(f"Owned: {page.total} licensed datasets")
    for d in page.items:
        print(" -", d.table, d.recordCount, "records, latest archive", d.latestArchiveMonth)

    for d in tl.datasets.iter_owned(total_limit=1):
        ds = tl.dataset(d.table)
        print("Archives:", [a.month for a in ds.archives()])
        print("Saved", ds.archive(f"{d.table}.zip", month="latest", format="geojson"))
        print("Rows:", ds.coordinates(limit=5).total)
except AddonRequiredError as e:
    print("Need addon:", e.addon)
except NotFoundError as e:
    print("No archive available:", e.message)
