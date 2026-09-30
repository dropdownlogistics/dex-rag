"""Index-side exclusions for dex-ingest-everything.py.

What is in the corpus is the Operator's call (everything except credentials). What Dex
searches is a retrieval-quality decision: an excluded path stays in the corpus, in ddl-vault
and in git; only the index skips it. Tested by test_index_exclusions.py (Ellis Cooper,
DDL-4008; bookkeeping anchored to corpus/<root>/ per Silas Reeve, DDL-3004).
"""
from __future__ import annotations

import re

# Bookkeeping files the corpus writes ALONGSIDE each root's text. Matched
# only at corpus/<root>/<file> -- one segment below corpus/ -- because these
# names are ordinary and INDEX_EXCLUDE sees every private root.
_CORPUS_BOOKKEEPING = (
    r"manifest\.jsonl|SUMMARY\.md|MIRROR_GAPS\.md|REMOVED_BY_OPERATOR\.txt"
    r"|run\.json|source-inventory-[^\\/]*\.txt"
)

INDEX_EXCLUDE = [
    # vendored third-party code: a library is not the Operator's material,
    # and 65 files of auto-generated cmdlet definitions outrank his own
    # writing on any query that shares their vocabulary
    re.compile(r"[\\/]WindowsPowerShell[\\/]Modules[\\/]", re.I),
    re.compile(r"[\\/]node_modules[\\/]", re.I),
    re.compile(r"[\\/]site-packages[\\/]", re.I),
    re.compile(r"[\\/]vendor[\\/]", re.I),
    re.compile(r"[\\/](?:\.venv|venv)[\\/]", re.I),
    # app and game data
    re.compile(r"[\\/]Rockstar Games[\\/]", re.I),
    re.compile(r"[\\/]Social Club[\\/]", re.I),
    re.compile(r"[\\/]\.wdc[\\/]", re.I),
    # the corpus's own bookkeeping, anchored to corpus/<root>/<file>
    re.compile(r"[\\/]corpus[\\/][^\\/]+[\\/](?:" + _CORPUS_BOOKKEEPING + r")$",
               re.I),
    # the corpus's analysis outputs: paths and counts about the corpus,
    # not content from it (Wren's duplicate CSV lives here)
    re.compile(r"[\\/]corpus[\\/]_analysis[\\/]", re.I),
]


def is_index_excluded(path) -> bool:
    return any(rx.search(str(path)) for rx in INDEX_EXCLUDE)
