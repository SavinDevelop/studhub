from xml.etree import ElementTree as ET

import pytest

from .templatetags.ui import ICON_NAMES, icon


@pytest.mark.parametrize("name", sorted(ICON_NAMES))
def test_bundled_lucide_icons_render_with_inherited_color(name):
    markup = str(icon(name))
    root = ET.fromstring(markup)
    assert root.attrib["aria-hidden"] == "true"
    svg = root[0]
    assert svg.attrib["data-lucide"] == ICON_NAMES[name]
    assert svg.attrib["stroke"] == "currentColor"
    assert svg.attrib["viewBox"] == "0 0 24 24"
    assert "<img" not in markup
    assert icon(name, active=True) == markup


def test_unknown_icons_cannot_load_arbitrary_files():
    assert icon("../../core/settings") == ""
    assert icon("<script>alert(1)</script>") == ""
