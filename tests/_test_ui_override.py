# -*- coding: utf-8 -*-
"""UI override suite: ui/override.css is injected before the dashboard </head>.

python tests/_test_ui_override.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _suite_head import *  # noqa: F401,F403

P, A = bootstrap()
declare_suite(__file__, ["qoder_proxy.py", "ui/override.css"])

BODY = b"<html><head><title>t</title></head><body>x</body></html>"
PREFIX = b'<style id="qd-override">'
SUFFIX = b"</style>"


def with_css(raw):
    """Run the hook with a temp css file holding raw bytes."""
    fd, path = tempfile.mkstemp(suffix=".css")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(raw)
        old = P.UI_OVERRIDE_CSS
        P.UI_OVERRIDE_CSS = path
        try:
            return P._inject_override_css(BODY)
        finally:
            P.UI_OVERRIDE_CSS = old
    finally:
        os.unlink(path)


def with_path(path):
    """Run the hook with UI_OVERRIDE_CSS pointed at path."""
    old = P.UI_OVERRIDE_CSS
    P.UI_OVERRIDE_CSS = path
    try:
        return P._inject_override_css(BODY)
    finally:
        P.UI_OVERRIDE_CSS = old


def test_injection_position():
    css = b"body{color:red}"
    out = with_css(css)
    block = PREFIX + css + SUFFIX
    idx = BODY.index(b"</head>")
    check(
        "override block sits immediately before the first </head>",
        out == BODY[:idx] + block + BODY[idx:],
        out,
    )


def test_missing_file_is_byte_identical():
    missing = os.path.join(tempfile.mkdtemp(), "no-such.css")
    check("missing css leaves the body byte-identical", with_path(missing) == BODY)


def test_empty_file_is_byte_identical():
    check("empty css leaves the body byte-identical", with_css(b"") == BODY)


def test_unreadable_path_is_byte_identical():
    check(
        "directory at the css path leaves the body unchanged",
        with_path(tempfile.mkdtemp()) == BODY,
    )


def test_non_utf8_css_is_passed_through():
    css = b"\xff\xfe\x00a{color:red}"
    out = with_css(css)
    check("non-utf8 css bytes are injected without decoding",
          out == BODY.replace(b"</head>", PREFIX + css + SUFFIX + b"</head>", 1),
          out)


def test_style_close_is_neutralized():
    css = b"a{}</style><script>alert(1)</script>"
    out = with_css(css)
    check(
        "css </style is escaped so it cannot break out",
        b"</style><script>" not in out,
        out,
    )
    check(
        "only the injected terminator closes the block", out.count(SUFFIX) == 1, out
    )  # the escaped copy carries a backslash
    check("escaped form keeps the css readable", b"<\\/style><script>" in out, out)


def test_style_close_is_neutralized_case_insensitively():
    css = b"a{}</STYLE><script>x</script>b{}</Style >"
    out = with_css(css)
    check("uppercase </STYLE> is escaped", b"</STYLE>" not in out, out)
    check("mixed-case </Style> is escaped", b"</Style" not in out, out)
    check("only the injected terminator closes the block", out.count(SUFFIX) == 1, out)


def test_no_head_is_unchanged():
    no_head = b"<html><body>x</body></html>"
    old = P.UI_OVERRIDE_CSS
    fd, path = tempfile.mkstemp(suffix=".css")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(b"body{color:red}")
        P.UI_OVERRIDE_CSS = path
        check(
            "body without </head> is served unchanged",
            P._inject_override_css(no_head) == no_head,
        )
    finally:
        P.UI_OVERRIDE_CSS = old
        os.unlink(path)


def test_handler_content_length_matches_body():
    html = b"<html><head></head><body>panel</body></html>"
    fd, html_path = tempfile.mkstemp(suffix=".html")
    fd2, css_path = tempfile.mkstemp(suffix=".css")
    old_html, old_css = P.DASHBOARD_HTML, P.UI_OVERRIDE_CSS
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(html)
        with os.fdopen(fd2, "wb") as fh:
            fh.write(b"body{margin:0}")
        P.DASHBOARD_HTML = html_path
        P.UI_OVERRIDE_CSS = css_path

        class FakeHandler(object):
            def __init__(self):
                self.wfile = io.BytesIO()
                self.headers = {}
                self.status = None

            def send_response(self, code):
                self.status = code

            def send_header(self, key, value):
                self.headers[key] = value

            def end_headers(self):
                pass

        handler = FakeHandler()
        P.Handler._dashboard(handler)
        served = handler.wfile.getvalue()
        check(
            "dashboard serves an injected body",
            PREFIX in served and served != html,
            served,
        )
        check(
            "Content-Length matches the injected bytes",
            handler.headers.get("Content-Length") == str(len(served)),
            handler.headers,
        )
    finally:
        P.DASHBOARD_HTML, P.UI_OVERRIDE_CSS = old_html, old_css
        os.unlink(html_path)
        os.unlink(css_path)


def test_css_is_reread_per_request():
    fd, path = tempfile.mkstemp(suffix=".css")
    old = P.UI_OVERRIDE_CSS
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(b"body{color:red}")
        P.UI_OVERRIDE_CSS = path
        first = P._inject_override_css(BODY)
        with open(path, "wb") as fh:
            fh.write(b"body{color:blue}")
        second = P._inject_override_css(BODY)
        check(
            "css edits apply without a restart",
            b"color:red" in first and b"color:blue" in second,
            (first, second),
        )
    finally:
        P.UI_OVERRIDE_CSS = old
        os.unlink(path)


def test_handler_serves_stock_html_without_css():
    html = b"<html><head><title>t</title></head><body>panel</body></html>"
    fd, html_path = tempfile.mkstemp(suffix=".html")
    empty_fd, empty_path = tempfile.mkstemp(suffix=".css")
    missing_path = os.path.join(tempfile.mkdtemp(), "no-such.css")
    old_html, old_css = P.DASHBOARD_HTML, P.UI_OVERRIDE_CSS
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(html)
        os.close(empty_fd)

        class FakeHandler(object):
            def __init__(self):
                self.wfile = io.BytesIO()
                self.headers = {}

            def send_response(self, code):
                pass

            def send_header(self, key, value):
                self.headers[key] = value

            def end_headers(self):
                pass

        P.DASHBOARD_HTML = html_path
        for label, css_path in (("missing", missing_path), ("empty", empty_path)):
            P.UI_OVERRIDE_CSS = css_path
            handler = FakeHandler()
            P.Handler._dashboard(handler)
            check("%s css serves dashboard.html byte-for-byte" % label,
                  handler.wfile.getvalue() == html, handler.wfile.getvalue())
            check("%s css keeps the stock Content-Length" % label,
                  handler.headers.get("Content-Length") == str(len(html)),
                  handler.headers)
    finally:
        P.DASHBOARD_HTML, P.UI_OVERRIDE_CSS = old_html, old_css
        os.unlink(html_path)
        os.unlink(empty_path)


test_injection_position()
test_missing_file_is_byte_identical()
test_empty_file_is_byte_identical()
test_unreadable_path_is_byte_identical()
test_non_utf8_css_is_passed_through()
test_style_close_is_neutralized()
test_style_close_is_neutralized_case_insensitively()
test_no_head_is_unchanged()
test_handler_content_length_matches_body()
test_handler_serves_stock_html_without_css()
test_css_is_reread_per_request()
def _css_section_two():
    raw = io.open(os.path.join(ROOT, "ui", "override.css"), encoding="utf-8").read()
    start = raw.index("/* 2. mobile layout */")
    end = raw.index("/* 3. visual polish */")
    return raw, raw[start:end]


def _css_top_level_headers(text):
    """Return (headers, ok); comments and quoted strings are skipped."""
    headers = []
    depth = 0
    buf = []
    i = 0
    quote = None
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch == "/" and nxt == "*":
            end = text.find("*/", i + 2)
            if end < 0:
                return headers, False
            i = end + 2
            continue
        elif ch in "\"'":
            quote = ch
        elif ch == "{":
            if depth == 0:
                headers.append("".join(buf).strip())
            depth += 1
            buf = []
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return headers, False
            buf = []
        else:
            if depth == 0:
                buf.append(ch)
        i += 1
    return headers, depth == 0 and quote is None


def test_css_is_ascii_balanced_and_marker_free():
    raw, _ = _css_section_two()
    _, ok = _css_top_level_headers(raw)
    check("override css is ASCII, brace-balanced and has no closing tag",
          all(ord(ch) < 128 for ch in raw) and ok and "</" not in raw,
          (len(raw), ok))


def test_css_rules_are_inside_max_width_media():
    _, section = _css_section_two()
    headers, ok = _css_top_level_headers(section)
    bad = [h for h in headers if not h.startswith("@media (max-width:")]
    check("every section 2 rule sits in a max-width media block",
          ok and bool(headers) and not bad, (bad, headers))


def test_important_rules_carry_reason_comment():
    _, section = _css_section_two()
    missing = [line.strip() for line in section.splitlines()
               if "!important" in line and "beats inline style" not in line]
    check("each !important has a beats inline style comment", not missing, missing)


test_css_is_ascii_balanced_and_marker_free()
test_css_rules_are_inside_max_width_media()
test_important_rules_carry_reason_comment()

def _css_section_three():
    raw = io.open(os.path.join(ROOT, "ui", "override.css"), encoding="utf-8").read()
    start = raw.index("/* 3. visual polish */")
    return raw[start:]


def _css_top_blocks(text):
    """Return [(selector, body)] for top-level blocks, comments stripped."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    blocks = []
    depth = 0
    sel = []
    body = []
    cur = None
    for ch in text:
        if ch == "{":
            if depth == 0:
                cur = " ".join("".join(sel).split())
                sel = []
                body = []
            else:
                body.append(ch)
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                blocks.append((cur, "".join(body)))
                cur = None
                body = []
            elif depth > 0:
                body.append(ch)
        elif depth == 0:
            sel.append(ch)
        else:
            body.append(ch)
    return blocks


FORBIDDEN_CSS = {
    "padding", "margin", "width", "height", "display", "gap", "position",
    "top", "left", "right", "bottom", "inset", "z-index", "overflow",
    "overflow-x", "overflow-y", "font-size", "line-height", "content",
    "border", "border-width", "border-top", "border-right", "border-bottom",
    "border-left", "vertical-align", "white-space", "float", "transform",
}


def _forbidden_prop(prop):
    return prop in FORBIDDEN_CSS or prop.startswith(("min-", "max-", "grid-", "flex"))


def _declared_props(body):
    props = []
    for raw in body.split(";"):
        raw = raw.strip()
        if ":" not in raw:
            continue
        props.append(raw.split(":", 1)[0].strip())
    return props


def test_section_three_has_no_layout_properties():
    blocks = [b for b in _css_top_blocks(_css_section_three())
              if not b[0].startswith("@media")]
    bad = []
    for sel, body in blocks:
        for prop in _declared_props(body):
            if _forbidden_prop(prop):
                bad.append("%s { %s }" % (sel, prop))
    check("section 3 top-level rules use decoration properties only", not bad, bad)


def test_section_one_only_has_variable_blocks():
    section = io.open(os.path.join(ROOT, "ui", "override.css"),
                      encoding="utf-8").read()
    start = section.index("/* 1. design tokens */")
    end = section.index("/* 2. mobile layout */")
    blocks = _css_top_blocks(section[start:end])
    selectors = [b[0] for b in blocks]
    bad = []
    for sel, body in blocks:
        for raw in body.split(";"):
            raw = raw.strip()
            if raw and not raw.startswith("--"):
                bad.append("%s { %s }" % (sel, raw))
    check("section 1 is only :root and dark-theme variable blocks",
          selectors == [":root", '[data-theme="dark"]'] and not bad,
          (selectors, bad))


test_section_three_has_no_layout_properties()
test_section_one_only_has_variable_blocks()

def test_dockerfile_ships_ui_and_i18n():
    dockerfile = io.open(os.path.join(ROOT, "Dockerfile"), encoding="utf-8").read()
    ignore_path = os.path.join(ROOT, ".dockerignore")
    ignored = io.open(ignore_path, encoding="utf-8").read() if os.path.exists(ignore_path) else ""
    patterns = [line.strip().rstrip("/") for line in ignored.splitlines()
                if line.strip() and not line.strip().startswith("#")]
    excluded = [name for name in ("ui", "i18n") if name in patterns]
    check("Dockerfile copies ui/ and i18n/ and .dockerignore keeps both",
          bool(re.search(r"^COPY ui ", dockerfile, re.M))
          and bool(re.search(r"^COPY i18n ", dockerfile, re.M))
          and not excluded, (excluded, patterns))


test_dockerfile_ships_ui_and_i18n()

finish()
