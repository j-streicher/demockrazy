"""Fallen in den Templates, die kein View-Test bemerkt."""

import pathlib
import re

TEMPLATE_ROOT = pathlib.Path(__file__).resolve().parents[1] / "templates"


def test_no_multiline_brace_hash_comments():
    """`{# … #}` über mehrere Zeilen ist in Django **kein** Kommentar.

    Gemessen, weil es beim Umbau von results.html (4.2) genau einmal zugeschlagen hat: Djangos
    `tag_re` ist ohne `re.DOTALL` kompiliert, ein `{#` findet sein `#}` also nur in derselben Zeile.
    Ein mehrzeiliger Block bleibt Text -- inklusive der `{{ … }}` darin, die dann ausgewertet
    werden. Im konkreten Fall stand das Wort „script" in spitzen Klammern in der Prosa; der Parser
    öffnete daran ein script-Element und verschluckte das Datenelement dahinter. Die Seite lieferte
    einen fehlerfreien 200 und zeigte kein Diagramm.

    Warum es so lange keiner merkte: in einem Kind-Template verwirft Django alles außerhalb der
    `{% block %}`s, und dort standen die beiden älteren Fälle. Verschiebt sie jemand nach innen,
    leaken sie. Für mehrzeilige Kommentare gibt es `{% comment %}`.
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

    assert not offenders, "mehrzeilige {# #}-Blöcke -- {% comment %} verwenden: " + ", ".join(
        offenders
    )
