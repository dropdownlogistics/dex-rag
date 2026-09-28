"""dex-convert must not fail a finished conversion because its progress line can't be encoded.

Ellis Cooper (DDL-4008), iCloud corpus run, 2026-09-28: all 37 .vcf files failed. write_output wrote
each file correctly, then printed a line containing U+2192; with stdout redirected on Windows the
stream is cp1252, the print raised, and the caller recorded a failed conversion.
"""
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

SCRIPT = r"""
import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("dex_convert", r"{src}")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.write_output("hello", Path(r"{out}"), "card.vcf")
"""


def test_write_output_survives_cp1252_stdout(tmp_path):
    out = tmp_path / "card.vcf.md"
    code = SCRIPT.format(src=HERE / "dex-convert.py", out=out)
    env = dict(os.environ, PYTHONIOENCODING="cp1252", PYTHONUTF8="0")
    r = subprocess.run([sys.executable, "-c", code], cwd=HERE, env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    assert out.read_text(encoding="utf-8") == "hello"
    assert b"[OK] card.vcf" in r.stdout
