"""Waypoint v0.2: credential masking in text and paths, failing closed, and the left-out-for-everyone rule.

The probe shapes are Amos Sayer's (DDL-3007), from his pre-install audit's probe file
(ddl-org surface-audit/work/WAYPOINT-AUDIT/waypoint_credential_probes.py), rebuilt here as the regression test
his fix list asks for (item e). Every value is FAKE and built at run time, so no secret-shaped literal sits in git.
'Survives' means any 10-character window of the secret appears in the output, his test.
Silas Reeve / DDL-3004 / 2026-10-16
"""
import pytest

import waypoint as wp

A = "abcdefghijklmnopqrstuvwxyz0123456789"
PROBES = [
    ("aws_access_key", "key id {} in a doc", "AKIA" + "ABCDEFGHIJKLMNOP"),
    ("github_pat", "token {} end", "ghp_" + A),
    ("openai_style", "key {} end", "sk-" + "ab12cd34ef56gh78ij90kl12mn34op56qr78st90uv12wx34"),
    ("slack_bot", "bot {} end", "xoxb-" + "123456789012-123456789012-abcdefABCDEF0123456789ab"),
    ("bearer_jwt", "Authorization: Bearer {}", "eyJ" + "hbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV"),
    ("pem_body", "-----BEGIN RSA " + "PRIVATE KEY-----\n{}\n-----END RSA " + "PRIVATE KEY-----", "MIIEowIBAAKCAQEA" + A * 3),
    ("password_assignment", "db password = {} for the server", "Tr0ub4dor&3xampleX9"),
    ("api_key_colon", "api_key: {}", "9f8e7d6c5b4a39281706f5e4d3c2b1a0"),
    ("env_style_token", "DEX_API_TOKEN={}", "q3Zk8vN1xP7mT4bW2cR6yH9jL5dF0sGa"),
    ("url_userinfo", "clone https://deploy:{}@git.example.test/repo.git", "S3cr3tPassw0rdX"),
    ("conn_string", "Server=db.example.test;User Id=sa;Password={};", "Xk29!vQm7LpTz4Rb"),
    ("google_key", "key {} end", "AIza" + "SyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6"),
    ("stripe_live", "key {} end", "sk_" + "live_" + "51H8aBcDeFgHiJkLmNoPqRsT"),
    ("base64_secret", "secret: {}", "VGhpcyBpcyBhIGZha2Ugc2VjcmV0IHZhbHVlIGZvciBwcm9iaW5n"),
    ("password_next_line", "password:\n  {}", "Hunter2Example#Value99"),
    ("quoted_json", '{"client_secret": "%s"}', "abcDEF123456ghiJKL789012mnoPQR34"),
    ("azure_sas", "?sv=2020&sig={}&se=2030", "Xy12AbCdEfGhIjKlMnOpQrStUvWxYz0123456789%3D"),
    ("aws_secret", "aws_secret_access_key = {}", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"),
]


# Part B: Amos Sayer's second-pass shapes (waypoint_credential_probes_v2.py, 2026-10-16), the new regression floor.
# They were written after reading the v0.2 rules, so they are the shapes a name list would miss. The 40-hex string in
# prose with no name beside it is left out on purpose: no name-based rule can know it, and he did not score it.
NEW = [
    ("camel_accessToken", '{"accessToken": "%s"}', "Zq81xKd02LmPw93TnVb7RcYe45HsUg"),
    ("camel_clientSecret", "clientSecret = {}", "Mn47PqRs91TuVw23XyZa65BcDe08Fg"),
    ("pgpassword_env", "export PGPASSWORD={}", "pgHunter2Fake9Value"),
    ("azure_accountkey", "DefaultEndpointsProtocol=https;AccountName=x;AccountKey={};EndpointSuffix=core.windows.net",
     "dGhpcyBpcyBhIGZha2UgYWNjb3VudCBrZXkgdmFsdWU9PQ"),
    ("passphrase_word", "passphrase: {}", "violet-anchor-lantern-42"),
    ("pass_word", "pass = {}", "Fake9Pass!Value77"),
    ("secretkey_nosep", "secretkey: {}", "Kd83Jf02Lq91Mn47Pz65"),
    ("camel_privateKey", "privateKey: {}", "Pk55Qr82St19Uv03Wx66"),
    ("camel_accessKey", "accessKey: {}", "Ak55Qr82St19Uv03Wx66"),
    ("passphrase_quoted_spaces", 'password: "%s"', "correct horse battery staple extra"),
    ("single_quoted_spaces", "password: '%s'", "correct horse battery staple extra"),
    ("escaped_quote_inside", 'password: "%s"', 'Ab12\\"CdEf34GhIj56KlMn'),
    ("unterminated_quote", 'password: "{}', "Un7erm1natedFakeValue99"),
    ("password_with_semicolon", "password={}", "Ab12;CdEf34;GhIj56"),
    ("password_with_comma", "password: {}", "Ab12,CdEf34,GhIj56"),
    ("password_with_apostrophe", "password: {}", "Ab12'CdEf34'GhIj56"),
    ("password_is_words", "the password is {} so keep it", "Tr0ubl3sFake77Word"),
    ("cli_flag_space", "mysql --password {} --host db", "Cl1Fl4gFakeValue88"),
    ("cli_flag_api_key", "tool --api-key {} --verbose", "Ap1K3yFlagFakeValue11"),
    ("curl_basic_flag", "curl -u deploy:{} https://example.test", "Cu7lBasicFakeValue22"),
    ("authorization_basic", "Authorization: Basic {}", "dXNlcm5hbWU6ZmFrZXBhc3N3b3JkMTIz"),
    ("authorization_token_scheme", "Authorization: Token {}", "Tk55SchemeFakeValue33"),
    ("password_arrow", "'password' => '{}'", "Ph9Arrow11FakeValue"),
    ("yaml_folded", "password: >-\n  {}", "Yaml88FoldedFakeValue"),
    ("npm_token", "//registry.example.test/:_authToken={}", "npm_" + "aB3dE6gH9jK2mN5pQ8sT1vW4yZ7cF0hJ3lN6"),
    ("huggingface", "token {} end", "hf_" + "aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789"),
    ("sendgrid", "key {} end", "SG." + "aBcDeFgHiJkLmNoPqRsTuV.wXyZ0123456789aBcDeFgHiJkLmNoPqRsTuV"),
    ("pypi", "token {} end", "pypi-AgEIcHlwaS5vcmc" + "aBcDeFgHiJkLmNoPqRsT0123456789"),
    ("shopify", "token {} end", "shpat_" + "aBcDeFgHiJkLmNoPqRsT0123456789ab"),
    ("google_oauth", "token {} end", "ya29." + "a0AfH6SMBaBcDeFgHiJkLmNoPqRsT0123456789"),
    ("stripe_webhook", "secret {} end", "whsec_" + "aBcDeFgHiJkLmNoPqRsT0123456789ab"),
    ("anthropic_style", "key {} end", "sk-ant-api03-" + "aBcDeFgHiJkLmNoPqRsT0123456789-aBcDeFgHiJkLm"),
    # third pass (Amos, waypoint_credential_probes_v3_fresh.py): shapes he wrote without showing them first
    ("pw_short_name", "pw: {}", "Mint-Ocelot-77-Fresh"),
    ("set_cookie_session", "Set-Cookie: sessionid={}; Path=/", "9fA8sD7fG6hJ5kL4zX3cV2bN1m"),
    ("cookie_header", "Cookie: {}", "k3Jf9Lm2Qp7Rt5Vw1Xz8Yb4"),
    ("pat_ado", "AZURE_DEVOPS_EXT_PAT={}", "abcdefghijklmnopqrstuvwxyz234567abcdefghijklmnopqrst"),
    ("mysql_glued_p", "mysql -u root -p{} appdb", "My5qlGluedFakeValue44"),
    ("mysqldump_glued_p", "mysqldump -h db.example.test -p{} --all-databases", "Dump5GluedFakeValue55"),
    ("tailscale_key", "key {} end", "tskey-" + "auth-kAbCdEfGhIjKlMnOpQrStUv-aBcDeFgHiJkLmNoPqRsT"),
]


def survives(secret, out):
    return any(secret[i:i + 10] in out for i in range(0, max(1, len(secret) - 9)))


def fill(tpl, secret):
    return tpl % secret if "%s" in tpl else tpl.replace("{}", secret)


@pytest.mark.parametrize("pid,tpl,secret", PROBES, ids=[p[0] for p in PROBES])
def test_every_probe_shape_is_masked_in_the_snippet(pid, tpl, secret):
    snip, m = wp.snippet_of("file: x\npath: y\n\nsome prose before. " + fill(tpl, secret) + " and some prose after.")
    assert not survives(secret, snip), pid
    assert m >= 1 and wp.MASK in snip


def test_all_eighteen_at_once_and_the_prose_around_them_stays():
    text = "\n".join("line %d: %s and plain words" % (i, fill(t, s)) for i, (_, t, s) in enumerate(PROBES))
    out, m = wp.mask(text)
    assert [p for p, t, s in PROBES if survives(s, out)] == [] and m >= len(PROBES)
    assert out.count("and plain words") == len(PROBES)


def test_ordinary_text_and_hashes_are_left_alone():
    for s in ("a risk-register line and commit c10e3d88df7c9032c8c287ad4e700de089b6a938",
              "the monkey sat on the keyboard; the design was signed off",
              "FND-0034 closed after seven nights; sha256 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"):
        assert wp.snippet_of(s) == (s, 0)


def test_a_credential_shaped_path_is_masked_too():
    secret = "ghp_" + A
    ask = lambda t, n: ([{"id": "1", "source_root": "vault", "rel_path": f"notes/{secret}.md", "text": "x", "score": 0.5,
                          "chunk_index": 0, "total_chunks": 1}], {"rows": 1})
    env = wp.search("anything", 3, ask)
    assert not survives(secret, env["hits"][0]["path"]) and env["hits"][0]["path"].startswith("notes/")
    assert env["credentials_masked"] == 1


def test_a_secret_is_masked_before_the_cut_so_it_cannot_straddle_it():
    secret = "q3Zk8vN1xP7mT4bW2cR6yH9jL5dF0sGa"
    snip, _ = wp.snippet_of("w " * (wp.SNIPPET_CHARS // 2 - 6) + "token=" + secret)
    assert not survives(secret, snip)


def test_masking_fails_closed(monkeypatch):
    def boom(_):
        raise RuntimeError("scanner broke")
    monkeypatch.setattr(wp, "credential_spans", boom)
    assert wp.snippet_of("anything at all") == (None, 0)
    ask = lambda t, n: ([{"id": "1", "source_root": "vault", "rel_path": "a.md", "text": "x", "score": 0.5,
                          "chunk_index": 0, "total_chunks": 1}], {"rows": 1})
    env = wp.search("anything", 3, ask)
    assert env["hits"] == [] and env["withheld_unchecked"] == 1 and any("withheld" in l for l in env["limits"])


def test_a_missing_scanner_withholds_every_snippet(monkeypatch):
    monkeypatch.setattr(wp, "secrets", None)
    assert wp.snippet_of("plain words") == (None, 0)


def test_photos_are_left_out_for_every_seat_and_no_filter_brings_them_back():
    cs = [{"id": "p", "source_root": "vault", "rel_path": "inbox/IMG_0001.HEIC", "text": "ocr", "score": 0.9, "chunk_index": 0, "total_chunks": 1},
          {"id": "q", "source_root": "photos", "rel_path": "2026/a.txt", "text": "caption", "score": 0.8, "chunk_index": 0, "total_chunks": 1},
          {"id": "n", "source_root": "vault", "rel_path": "notes/a.md", "text": "note", "score": 0.7, "chunk_index": 0, "total_chunks": 1}]
    ask = lambda t, n: (cs[:n], {"rows": 3})
    for q in ("thing", "thing root:photos", "thing ext:heic"):
        env = wp.search(q, 5, ask)
        assert all(h["id"] == "n" for h in env["hits"]) and env["removed"]["left_out_for_everyone"] == 2


@pytest.mark.parametrize("pid,tpl,secret", NEW, ids=[p[0] for p in NEW])
def test_second_pass_shapes_are_masked_in_the_snippet(pid, tpl, secret):
    snip, m = wp.snippet_of("file: x\npath: y\n\nsome prose before. " + fill(tpl, secret) + " and some prose after.")
    assert not survives(secret, snip), pid
    assert m >= 1 and wp.MASK in snip


def test_the_prose_around_a_second_pass_shape_stays():
    # an unterminated quote cannot say where the value ends, so it masks to the end of the line by design
    rows = [r for r in NEW if r[0] != "unterminated_quote"]
    text = "\n".join("line %d: %s and plain words" % (i, fill(t, s)) for i, (_, t, s) in enumerate(rows))
    out, m = wp.mask(text)
    assert [p for p, t, s in rows if survives(s, out)] == [] and m >= len(rows)
    assert out.count("and plain words") == len(rows)


def test_the_wider_name_rule_still_leaves_ordinary_words_alone():
    for s in ("the monkey: sat on the donkey; a turkey = dinner",
              "author: Silas Reeve and authority: the steward",
              "mkdir -p out/dir && ls -p out and pinned to the board",
              "tokenised the text: 4 parts; sigma = 3; a pinch of salt"):
        out, m = wp.mask(s)
        # the words after a colon may be masked where a credential WORD is in the name (tokenised: ...), and that is the
        # intended over-mask; what must hold is that the names that are not credential words are not touched.
        if "tokenised" not in s:
            assert (out, m) == (s, 0), s


@pytest.mark.parametrize("path,secret,tail", [
    ("notes/accessToken_Zq81xKd02LmPw93TnVb7.md", "Zq81xKd02LmPw93TnVb7", ".md"),
    ("backup/PGPASSWORD=pgHunter2Fake9Value/x.md", "pgHunter2Fake9Value", "/x.md"),
    ("notes/password=Hunter2FakeValue.md", "Hunter2FakeValue", ""),
])
def test_credential_shaped_path_segments_are_masked_and_the_rest_of_the_path_stays(path, secret, tail):
    out, n = wp.path_of(path)
    assert not survives(secret, out) and n >= 1 and out.startswith(path.split("/")[0] + "/")
    assert out.endswith(tail)                   # a value stops at its "/", it does not eat the folders after it


def test_an_ordinary_file_name_with_a_credential_word_in_it_is_not_hidden():
    for p in ("notes/token-economics-notes.md", "work/secret-santa.md", "notes/pinned-sigma.md"):
        assert wp.path_of(p) == (p, 0), p


@pytest.mark.parametrize("root,rel", [
    ("vault", "x/y.avif"), ("vault", "x/y.CR2"), ("vault", "x/y.NEF"), ("vault", "x/y.ARW"), ("vault", "x/y.jfif"),
    ("vault", "x/y.avi"), ("vault", "x/y.mkv"), ("vault", "x/y.m4v"), ("Camera Roll", "x/y.md"), ("DCIM", "x/y.md"),
    ("pictures", "x/y.md"), ("vault", "phone/DCIM/100APPLE/y.md"),
])
def test_more_photo_shapes_are_left_out(root, rel):
    assert wp.left_out({"source_root": root, "rel_path": rel})


def test_a_bare_p_flag_is_left_alone_and_only_the_glued_mysql_form_is_masked():
    for s in ("mkdir -p out/dir/sub", "docker run -p 8080:80 image", "mysql -p", "mysql -u root -p appdb",
              "mysql -h db -P3306 appdb", "ls -p /tmp and rsync -avp a b"):
        assert wp.mask(s) == (s, 0), s
