"""dex-convert's output must be a function of its input, not of the run (FND-0022, Ellis Cooper / DDL-4008).

The header used to carry three properties of the RUN: `CONVERTED: <today>`, `SOURCE: <absolute path>` and
`CONVERTED_BY: dex-convert.py v1.0`. So the same file converted on two days, or from two folders, or by an
upgraded converter, gave different text, and every hash taken over that text drifted: the corpus's dedupe key
(text_sha256) changed on all 9 dex-convert rows between two runs of google-takeout a day apart, and on nothing
else in 18,272 shared rows. Operator approval for the change: 2026-10-01.

Behaviour is tested on real converter calls, not on the header string alone. Red-first.

Silas Reeve / DDL-3004 / 2026-10-01
"""
from __future__ import annotations

import importlib.util
import re
from datetime import datetime
from pathlib import Path

import pytest

HERE = Path(__file__).parent
_spec = importlib.util.spec_from_file_location("dex_convert_under_test", HERE / "dex-convert.py")
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)

VCF = ("BEGIN:VCARD\nVERSION:3.0\nFN:Test Person\nTEL:555-0100\nEMAIL:test@example.com\nEND:VCARD\n"
       "BEGIN:VCARD\nVERSION:3.0\nFN:Other Person\nTEL:555-0101\nEND:VCARD\n")
MBOX = ("From a@example.com Mon Jan  1 00:00:00 2024\nFrom: a@example.com\nTo: b@example.com\n"
        "Subject: first\nDate: Mon, 1 Jan 2024 00:00:00 +0000\n\nbody one\n\n"
        "From b@example.com Tue Jan  2 00:00:00 2024\nFrom: b@example.com\nTo: a@example.com\n"
        "Subject: second\nDate: Tue, 2 Jan 2024 00:00:00 +0000\n\nbody two\n\n")


def _convert(tmp_path: Path, folder: str, name: str, text: str, fn) -> bytes:
    """Convert `name` placed under a differently named folder; return all output bytes, in order."""
    src_dir = tmp_path / folder / "nested" / "deeper"
    src_dir.mkdir(parents=True)
    src = src_dir / name
    src.write_text(text, encoding="utf-8")
    out = tmp_path / (folder + "-out")
    produced = fn(src, out) or []
    assert produced, "the converter produced nothing: the test would compare two empty results"
    return b"\n".join(Path(p).read_bytes() for p in sorted(Path(x) for x in produced))


@pytest.mark.parametrize("name,text,fn_name", [("contacts.vcf", VCF, "convert_vcf"),
                                              ("mail.mbox", MBOX, "convert_mbox")])
def test_same_file_from_two_folders_converts_to_the_same_bytes(tmp_path, name, text, fn_name):
    a = _convert(tmp_path, "run-A-on-C-drive", name, text, getattr(C, fn_name))
    b = _convert(tmp_path, "run-B-somewhere-else", name, text, getattr(C, fn_name))
    assert a == b, "identical input gave different text: the output depends on where the file sat"


@pytest.mark.parametrize("name,text,fn_name", [("contacts.vcf", VCF, "convert_vcf"),
                                              ("mail.mbox", MBOX, "convert_mbox")])
def test_output_carries_no_property_of_the_run(tmp_path, name, text, fn_name):
    out = _convert(tmp_path, "some-folder", name, text, getattr(C, fn_name)).decode("utf-8")
    assert datetime.now().strftime("%Y-%m-%d") not in out, "today's date is in the converted text"
    assert "CONVERTED" not in out, "a conversion stamp or tool version is in the converted text"
    assert str(tmp_path) not in out and "some-folder" not in out, "the source's folder is in the converted text"
    assert not re.search(r"dex-convert\.py v\d", out), "the converter's version is in the converted text"


def test_header_still_says_what_the_document_is(tmp_path):
    out = _convert(tmp_path, "f", "contacts.vcf", VCF, C.convert_vcf).decode("utf-8")
    head = out.split("=" * 60)[0]
    assert "SOURCE: contacts.vcf" in head, "the file's name is the provenance a reader of the chunk needs"
    assert "TYPE: vcf-contacts" in head


def test_two_different_files_still_differ(tmp_path):
    # the control: determinism must not come from ignoring the input
    a = _convert(tmp_path, "x", "contacts.vcf", VCF, C.convert_vcf)
    b = _convert(tmp_path, "y", "contacts.vcf", VCF.replace("Test Person", "Someone Else"), C.convert_vcf)
    assert a != b
