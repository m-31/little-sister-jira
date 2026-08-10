"""The templates: that they ship, that they are the ones registered, and that the
markup is Jinja's to escape.

A surface extension carries something a check type does not — **package data**. The
two chips are Jinja files inside the import package, and a source checkout finds
them whether or not they would be in a wheel. So these tests read them the way an
installed package is read (:mod:`importlib.resources`, a
:class:`jinja2.PackageLoader`) rather than by walking up from ``__file__``.

That still does not prove the *wheel* carries them — only building one and
installing it into a clean environment does, which is the acceptance step. It does
prove the narrower thing that breaks silently: a template renamed in one place, or
left outside the package directory.
"""
from __future__ import annotations

from importlib import resources

import pytest
from jinja2 import Environment, PackageLoader, select_autoescape
from little_sister import slots

from little_sister_jira import jira

#: What ``jira.register()`` names, keyed by the slot it names it for. The pairing is
#: the thing under test: a renamed file that only got renamed on disk still ships,
#: and the registration then quietly draws nothing.
REGISTERED = {
    "reason.actions": "reason_actions.html",
    "node.actions": "node_actions.html",
}


@pytest.fixture
def environment() -> Environment:
    """Jinja reading this package the way an installed one is read.

    ``autoescape`` on for HTML, because that is little-sister's own setting and the
    escaping of a reason line is the property these templates rely on rather than
    implement.
    """
    return Environment(loader=PackageLoader("little_sister_jira", "templates"),
                       autoescape=select_autoescape(["html"]))


def test_both_templates_are_package_data():
    directory = resources.files("little_sister_jira") / "templates"
    shipped = {entry.name for entry in directory.iterdir()
               if entry.name.endswith(".html")}
    assert shipped == set(REGISTERED.values())


def test_the_package_declares_itself_typed():
    # Without `py.typed` a consumer running mypy over its own wiring gets
    # "module is installed, but missing library stubs or py.typed marker" for the
    # one import this package exists to be — and the marker only helps if it is
    # inside the import package, where the wheel picks it up.
    assert (resources.files("little_sister_jira") / "py.typed").is_file()


def test_the_registered_slots_are_slots_little_sister_declares():
    # The roster is closed (little-sister ADR-0034): a filler for a name that is not
    # in it is dropped with a warning, so a typo here costs the chip silently.
    assert set(REGISTERED) <= set(slots.SLOTS)
    assert set(jira.PLACEMENTS.values()) == set(REGISTERED)


@pytest.mark.parametrize("template", sorted(REGISTERED.values()))
def test_a_chip_renders_its_url_label_and_title(environment, template):
    html = environment.get_template(template).render(
        jira_url="https://tracker.example.org/secure/CreateIssueDetails!init.jspa?pid=1",
        jira_label="Jira all",
        jira_title="Create a Jira issue for /platform/ci/actions")
    assert 'href="https://tracker.example.org/secure/' in html
    assert ">Jira all</a>" in html
    assert 'target="_blank"' in html and 'rel="noopener noreferrer"' in html
    assert 'title="Create a Jira issue for /platform/ci/actions"' in html


@pytest.mark.parametrize("template", sorted(REGISTERED.values()))
def test_the_chip_classes_are_the_ones_the_frame_promises(environment, template):
    # `.reason-action` / `.node-action` are part of little-sister's slot contract
    # (its architecture.md §11), which is what lets the chip ink itself in
    # currentColor and read on every status tint without knowing which one it is on.
    html = environment.get_template(template).render(
        jira_url="https://tracker.example.org/x", jira_label="Jira", jira_title="t")
    expected = ("reason-action" if template.startswith("reason") else "node-action")
    assert f'class="{expected}"' in html


@pytest.mark.parametrize("template", sorted(REGISTERED.values()))
def test_a_reason_folded_into_the_draft_is_escaped_by_jinja(environment, template):
    # A reason is assembled from captured output (little-sister ADR-0018). Nothing in
    # this package builds markup, so the one thing that must hold is that the values
    # it hands over are escaped where they land.
    html = environment.get_template(template).render(
        jira_url='https://tracker.example.org/x?summary="><script>alert(1)</script>',
        jira_label='<b>Jira</b>',
        jira_title='say "hi" & <goodbye>')
    assert "<script>" not in html
    assert "<b>Jira</b>" not in html
    assert "&lt;script&gt;" in html
    assert "&#34;" in html or "&quot;" in html
    assert "&amp;" in html
