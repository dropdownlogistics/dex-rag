"""Proposed for dex-rag: index-side exclusions. Test first.

Applied to dex-rag by Silas Reeve (DDL-3004), 2026-09-29. The patterns live in
`index_exclusions.py`; this file tests them and `dex-ingest-everything.py` calls them.

WHAT IT IS FOR. `ddl-vault` became a private ingest root when the corpus
landed there, so the everything-run of 2026-09-29T09:56Z indexed 246,898
chunks from it -- including material that belongs in the corpus but not in a
retrieval index:

  * vendored third-party library code (the Microsoft Graph PowerShell SDK):
    12,777 chunks already in ddl_private_v1 across 65 files;
  * app and game data (Rockstar, Social Club, .wdc): 1,846 chunks, 91 files;
  * the corpus's own bookkeeping: 32 chunks.

THE RULE. What is *in the corpus* is the Operator's call -- everything except
credentials. What Dex *searches* is a retrieval-quality decision. An excluded
document stays in the corpus, in ddl-vault and in git; only the index skips it.

THE AMENDMENT THAT MATTERS (Silas, 2026-09-29). The first draft anchored
bookkeeping on the filename alone: `[\\/]SUMMARY\.md$`. But `INDEX_EXCLUDE`
applies to **every** private root -- `sessions`, `D:\DDL_Intake`, `archive` --
not only the corpus. A `SUMMARY.md` or `run.json` in any project the Operator
keeps there would have gone unsearchable **with nothing saying so**, which is
the expensive direction this file warns about in its own comments.

So bookkeeping is anchored to the layout it actually has: exactly one segment
below `corpus/`. `corpus/icloud/SUMMARY.md` is bookkeeping;
`archive/projectX/SUMMARY.md` is somebody's document, and
`corpus/icloud/text/.../SUMMARY.md` is a real document that happens to carry
that name.

Ellis Cooper / DDL-4008 / reborn-cowork
"""
from __future__ import annotations

import re
import unittest

from index_exclusions import is_index_excluded  # noqa: E402


V = r"C:\Users\dexjr\ddl-vault"


class Exclusions(unittest.TestCase):

    EXCLUDE = [
        # vendored
        V + r"\corpus\onedrive\text\Documents\WindowsPowerShell\Modules\Microsoft.Graph.Sites\2.38.1\exports\Cmdlets.ps1.md",
        r"C:\proj\node_modules\left-pad\index.js",
        r"C:\proj\.venv\Lib\site-packages\requests\api.py",
        r"C:\app\vendor\lib\x.php",
        # app/game data
        r"C:\Users\x\OneDrive\Documents\Rockstar Games\Social Club\log.txt",
        # corpus bookkeeping, one segment below corpus/
        V + r"\corpus\icloud\manifest.jsonl",
        V + r"\corpus\my-drive\SUMMARY.md",
        V + r"\corpus\onedrive\MIRROR_GAPS.md",
        V + r"\corpus\icloud\REMOVED_BY_OPERATOR.txt",
        V + r"\corpus\03_Work\run.json",
        V + r"\corpus\icloud\source-inventory-icloud-before.txt",
        # corpus analysis outputs
        V + r"\corpus\_analysis\duplicates.csv",
    ]

    # The cost of a false positive is a document the Operator wrote becoming
    # unsearchable with nothing saying so. All of these must pass through.
    KEEP = [
        # his own material inside the corpus
        V + r"\corpus\icloud\text\Documents\09_DDLProduction\09_Legal\exhibits\Exhibit_P2.pdf.md",
        V + r"\corpus\dex-universe\text\00_Archive\Google_SearchHistory.html.md",
        V + r"\corpus\my-drive\text\05_DirectIngest\notes.txt",
        # THE AMENDMENT: the same filenames in other private roots
        V + r"\archive\projectX\SUMMARY.md",
        r"D:\DDL_Private\sessions\2026-09-29\run.json",
        r"D:\DDL_Intake\share\2026-09-20\manifest.jsonl",
        # ...and a real document inside the corpus that happens to be named
        # like bookkeeping: it is under text/, not one segment below corpus/
        V + r"\corpus\icloud\text\Documents\projects\SUMMARY.md",
        V + r"\corpus\onedrive\text\notes\run.json",
        # documents ABOUT the excluded things
        r"C:\notes\how-we-vendor-dependencies.md",
        r"C:\notes\node_modules-cleanup-plan.md",
        r"C:\projects\vendormanagement\contracts\acme.md",
    ]

    def test_the_classes_we_mean_are_excluded(self):
        for p in self.EXCLUDE:
            self.assertTrue(is_index_excluded(p), f"should exclude: {p}")

    def test_nothing_of_the_operators_own_is_excluded(self):
        for p in self.KEEP:
            self.assertFalse(is_index_excluded(p), f"must NOT exclude: {p}")

    def test_bookkeeping_names_are_safe_in_other_private_roots(self):
        """Silas's amendment, stated as its own test because it is the whole
        reason the pattern is shaped this way.

        INDEX_EXCLUDE sees every PRIVATE_ROOT, not just the corpus, and
        SUMMARY.md / run.json / manifest.jsonl are ordinary filenames."""
        for p in (V + r"\archive\projectX\SUMMARY.md",
                  V + r"\archive\projectX\run.json",
                  r"D:\DDL_Private\sessions\2026-09-29\run.json",
                  r"D:\DDL_Intake\share\2026-09-20\manifest.jsonl",
                  r"C:\anything\SUMMARY.md"):
            self.assertFalse(is_index_excluded(p),
                             f"outside corpus/<root>/ this is somebody's "
                             f"document: {p}")

    def test_bookkeeping_matches_only_one_segment_below_corpus(self):
        """`corpus/icloud/SUMMARY.md` is bookkeeping. `corpus/icloud/text/
        .../SUMMARY.md` is a document that happens to share the name, and it
        lives where the Operator's material lives."""
        self.assertTrue(is_index_excluded(V + r"\corpus\icloud\SUMMARY.md"))
        self.assertFalse(is_index_excluded(
            V + r"\corpus\icloud\text\Documents\SUMMARY.md"))
        self.assertFalse(is_index_excluded(
            V + r"\corpus\icloud\text\SUMMARY.md"))

    def test_google_searchhistory_is_explicitly_kept(self):
        """Silas's ruling, 2026-09-29: large, and the Operator's own
        material. A test so nobody tidies it into a big-file exclusion later
        on sight of its size alone."""
        self.assertFalse(is_index_excluded(
            V + r"\corpus\dex-universe\text\00_Archive\DDL-Standards-Canon\Google_SearchHistory.html.md"))

    def test_a_segment_match_needs_separators_on_both_sides(self):
        """`vendor` as a path segment is a dependency tree; `vendormanagement`
        is a business folder."""
        self.assertTrue(is_index_excluded(r"C:\app\vendor\lib\x.php"))
        self.assertFalse(is_index_excluded(r"C:\app\vendormanagement\x.md"))
        self.assertFalse(is_index_excluded(r"C:\app\my-vendors.md"))

    def test_forward_and_back_slashes_both_match(self):
        self.assertTrue(is_index_excluded("/home/x/node_modules/pkg/a.js"))
        self.assertTrue(is_index_excluded(r"C:\x\node_modules\pkg\a.js"))
        self.assertTrue(is_index_excluded(
            "/mnt/c/Users/dexjr/ddl-vault/corpus/icloud/SUMMARY.md"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
