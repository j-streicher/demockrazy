"""Traps in the templates that no view test notices."""

import pathlib
import re

TEMPLATE_ROOT = pathlib.Path(__file__).resolve().parents[1] / "templates"


def test_no_multiline_brace_hash_comments():
    """`{# … #}` across several lines is **not** a comment in Django.

    Measured, because it struck exactly once while rebuilding results.html (4.2): Django's `tag_re`
    is compiled without `re.DOTALL`, so a `{#` finds its `#}` only on the same line. A multi-line
    block stays text -- including the `{{ … }}` inside it, which are then evaluated. In that
    concrete case the word "script" stood in angle brackets in the prose; the parser opened a script
    element there and swallowed the data element behind it. The page returned a faultless 200 and
    showed no chart.

    Why nobody noticed for so long: in a child template Django discards everything outside the
    `{% block %}`s, and that is where the two older cases sat. If someone moves them inside, they
    leak. For multi-line comments there is `{% comment %}`.
    """
    offenders = []
    for path in sorted(TEMPLATE_ROOT.rglob("*.html")):
        text = path.read_text()
        for match in re.finditer(r"\{#", text):
            rest = text[match.start() :]
            end = rest.find("#}")
            if end == -1 or "\n" in rest[: end + 2]:
                offenders.append(
                    f"{path.relative_to(TEMPLATE_ROOT)}:{text[: match.start()].count(chr(10)) + 1}"
                )

    assert not offenders, "multi-line {# #} blocks -- use {% comment %}: " + ", ".join(offenders)
