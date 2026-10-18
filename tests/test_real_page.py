"""The chips on little-sister's own pages: the installed library, rendering them.

Every other test here stands something in for the library — `FakeNode` for the node a
provider reads, a direct call for the slot machinery that makes the call, and in
`test_dashboard_link.py` a Flask app of its own that registers the `status` route
itself. Each stands in for a name this package reads that little-sister's
`architecture.md` §11 does not promise: a node's attributes, the context a slot hands
over, the endpoint a draft links back to. So a rename on the library's side passed
every one of them, and in a deployment cost the chip or its link quietly, because the
slot machinery contains the error.

These render the **installed** library's grid and leaf pages with the chips
registered, the way a deployment serves them: a fresh process per configuration, this
package imported first and registering from a real `jira.yaml`, `little_sister.app`
after it. What reaches the page is what the library handed over. A renamed attribute
moves or drops chips, a renamed context key or endpoint drops every one of them, and a
status or an observation time the provider could not read shows in the draft.

Three names in the program below are not promised either, and are used on purpose:
`little_sister.tree.StatusTree`, its `upsert`, and the `status_tree` the pages read out
of `little_sister.app`. Nothing promised puts a node on a page, and a test whose
subject is the unpromised names may lean on a few more; when one of them moves, this
module fails loudly, which is the outcome the whole file is for. Who is looking goes
through the promised door instead — `little_sister.identity.use`, with a provider that
knows every request — so no user list and no login form are involved.

Like `test_the_import_is_the_registration.py`, the program runs in an environment
built from scratch, and so finds this package only where a deployment finds it:
installed. Run the suite through `uv run pytest`.

Nothing here is anybody's real Jira: the ids are placeholders and the host is a
documentation domain.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable
from html import unescape
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import parse_qs, urlsplit

import pytest

#: What every shape below starts from: a site, a project, an issue type, and one field
#: that carries the node's `name` into the draft.
HEAD = ('base_url: https://tracker.example.org\n'
        'project_id: "10000"\n'
        'issue_type_id: "10002"\n'
        'fields:\n'
        '  customfield_10101: "{name}: {reason}"\n')

#: The shapes of the `actions:` block that between them reach every attribute the
#: providers read. With both chips offered, each steps aside where the other is the
#: right subject, which is where `members` and `children` decide; with no `actions:`
#: block the per-line chip is the only one, and it keeps even prose. The third is the
#: first with the node chip naming its icon, which changes how that chip is drawn in
#: a head and never where it stands.
SHAPES = {
    "both": HEAD + ("actions:\n"
                    "  reason:\n    label: Jira\n"
                    "  node:\n    label: Jira all\n"),
    "reason only": HEAD,
    "square": HEAD + ("actions:\n"
                      "  reason:\n    label: Jira\n"
                      "  node:\n    label: Jira all\n    icon: jira\n"),
}

#: The grid, every leaf's own page, and the page of `/lambda`, a branch that is healthy
#: itself: where the library draws a branch's own head on its page, that head must
#: carry no chip either.
PAGES = ("/status", "/status/ci/reviews", "/status/ci/lint", "/status/svc/api",
         "/status/svc/ok", "/status/lambda/resize", "/status/lambda")

#: A deployment's `wsgi.py`, then the pages. It prints each page whole, with the status
#: it was served with, and leaves the reading to the tests, so that the program stays
#: what it stands for — and the context its library hands a node's actions, so that the
#: library asked what it hands over is the one that drew the pages.
PROGRAM = r"""
import json, sys

import little_sister_jira                      # the aspect and its slots, first
from little_sister import identity, slots
from little_sister.identity import Identity


class Everyone:
    def identify(self):
        return Identity("operator")

    def challenge(self):
        return "nobody", 401


identity.use("everyone", Everyone(), default=True)

import little_sister.app as dashboard          # the application, after them
from little_sister.status import StatusCode
from little_sister.tree import StatusTree

tree = StatusTree()
dashboard.status_tree = tree
tree.upsert("/ci/reviews", StatusCode.ERROR,
            {"pr-412": "review overdue", "pr-77": "review stale"}, members=True)
tree.upsert("/ci/lint", StatusCode.ERROR, {"e501": "line too long"}, members=True)
tree.upsert("/svc/api", StatusCode.ERROR,
            ["check error: boom", "Traceback (most recent call last):"])
tree.upsert("/svc/ok", StatusCode.OK, "all four replicas up")
tree.upsert("/svc", StatusCode.ERROR, "the group is degraded")
tree.upsert("/lambda/resize", StatusCode.ERROR, "3 errors in the last 1h")
tree.upsert("/lambda", StatusCode.OK, "1 function in scope (one region)")

client = dashboard.app.test_client()
print(json.dumps({"node.actions": slots.SLOTS["node.actions"].context,
                  "pages": {url: [(page := client.get(url)).status_code,
                                  page.get_data(as_text=True)]
                            for url in sys.argv[1:]}}))
"""

#: Where each chip belongs, as `(placement, summary)` — the summary opens with the
#: node's path, and a per-line chip's goes on with its line. Every case is decided by
#: one attribute the providers read off the library's node. `/svc` fails itself above
#: a failing leaf and keeps its node chip; `/lambda` is OK itself above one, and has
#: none — its failure is the leaf's, whose chip it is.
EXPECTED = {
    "both": {
        "/status": [
            ("node", "/ci/reviews: review overdue"),     # several members: a shortcut
            ("reason", "/ci/reviews: review overdue"),   # beside each member's own
            ("reason", "/ci/reviews: review stale"),
            ("reason", "/ci/lint: line too long"),       # one member: no node chip
            ("node", "/svc/api: check error: boom"),     # prose: the node files it
            ("node", "/svc: the group is degraded"),     # a container: its node chip
                                                         # only; the healthy leaf: none
            ("node", "/lambda/resize: 3 errors in the last 1h"),  # the failure's own;
        ],                                               # `/lambda`, OK itself: none
        "/status/ci/reviews": [
            ("node", "/ci/reviews: review overdue"),
            ("reason", "/ci/reviews: review overdue"),
            ("reason", "/ci/reviews: review stale"),
        ],
        "/status/ci/lint": [("reason", "/ci/lint: line too long")],
        "/status/svc/api": [("node", "/svc/api: check error: boom")],
        "/status/svc/ok": [],
        "/status/lambda/resize": [("node", "/lambda/resize: 3 errors in the last 1h")],
        "/status/lambda": [("node", "/lambda/resize: 3 errors in the last 1h")],
    },
    "reason only": {
        "/status": [
            ("reason", "/ci/reviews: review overdue"),
            ("reason", "/ci/reviews: review stale"),
            ("reason", "/ci/lint: line too long"),
            ("reason", "/svc/api: check error: boom"),   # prose keeps its lines when
            ("reason", "/svc/api: Traceback (most recent call last):"),  # no node chip
                                                         # stands in for them; the
                                                         # containers' lines: none
            ("reason", "/lambda/resize: 3 errors in the last 1h"),
        ],
        "/status/ci/reviews": [
            ("reason", "/ci/reviews: review overdue"),
            ("reason", "/ci/reviews: review stale"),
        ],
        "/status/ci/lint": [("reason", "/ci/lint: line too long")],
        "/status/svc/api": [
            ("reason", "/svc/api: check error: boom"),
            ("reason", "/svc/api: Traceback (most recent call last):"),
        ],
        "/status/svc/ok": [],
        "/status/lambda/resize": [
            ("reason", "/lambda/resize: 3 errors in the last 1h"),
        ],
        "/status/lambda": [("reason", "/lambda/resize: 3 errors in the last 1h")],
    },
}

EXPECTED["square"] = EXPECTED["both"]

#: One of this package's chips as its own templates write it: the class says which
#: placement and whether it is the head's square, the link is the draft, and the text
#: after the glyph is the label — or, a square showing none, its `aria-label`. The
#: library's own chips in the same rails link elsewhere, and are not matched.
CHIP = re.compile(
    r'<a class="(?P<placement>reason|node)-action(?P<square> is-icon)?" '
    r'href="(?P<href>https://tracker\.example\.org/[^"]*)"[^>]*?'
    r'aria-label="(?P<aria>[^"]*)"[^>]*>.*?</svg>(?P<label>[^<]*)</a>', re.DOTALL)


class Served(NamedTuple):
    """What one process served: each page's HTML, and the context the library that
    drew them hands `node.actions`."""

    pages: dict[str, str]
    context: tuple[str, ...]


def _render(root: Path, shape: str) -> Served:
    """Each page's HTML, served by a process that started the way a deployment does,
    and what that process's library hands a node's actions."""
    config = root / "config"
    config.mkdir()
    (config / "jira.yaml").write_text(SHAPES[shape], encoding="utf-8")
    done = subprocess.run([sys.executable, "-c", PROGRAM, *PAGES],
                          capture_output=True, text=True, cwd=root,
                          env={"PATH": "/usr/bin:/bin",
                               "LITTLE_SISTER_CONFIG_DIR": str(config),
                               "SECRET_KEY": "test-key"})
    assert done.returncode == 0, done.stderr
    served = json.loads(done.stdout.strip().splitlines()[-1])
    pages = served["pages"]
    refused = {url: status for url, (status, _page) in pages.items() if status != 200}
    assert not refused, f"the library did not serve every page: {refused}"
    return Served({url: page for url, (_status, page) in pages.items()},
                  tuple(served["node.actions"]))


@pytest.fixture(scope="module")
def served(tmp_path_factory) -> Callable[[str], Served]:
    """One shape, served — a process per shape, shared by every test here."""
    done: dict[str, Served] = {}

    def _served(shape: str) -> Served:
        if shape not in done:
            done[shape] = _render(tmp_path_factory.mktemp("pages"), shape)
        return done[shape]
    return _served


@pytest.fixture(scope="module")
def rendered(served) -> Callable[[str], dict[str, str]]:
    """The pages of one shape."""
    def _rendered(shape: str) -> dict[str, str]:
        return served(shape).pages
    return _rendered


def _chips(page: str) -> list[dict[str, Any]]:
    """Every Jira chip on a page as it is drawn: its placement, whether it is the
    head's square, the label it shows or names, and its draft's fields."""
    return [{"placement": chip["placement"], "square": bool(chip["square"]),
             "label": unescape(chip["aria"]) if chip["square"] else chip["label"],
             "draft": {key: values[0] for key, values
                       in parse_qs(urlsplit(unescape(chip["href"])).query).items()}}
            for chip in CHIP.finditer(page)]


def _drafts(page: str) -> list[tuple[str, str, dict[str, str]]]:
    """Every Jira chip on a page: its placement, its label, and its draft's fields."""
    return [(chip["placement"], chip["label"], chip["draft"]) for chip in _chips(page)]


def _trailer(draft: dict[str, str]) -> list[str]:
    """The lines under the draft's `---`: where the reason came from."""
    return draft["description"].split("\n---\n", 1)[1].splitlines()


@pytest.mark.parametrize(("shape", "url"),
                         [(shape, url) for shape in SHAPES for url in PAGES])
def test_each_chip_lands_where_its_rule_puts_it(rendered, shape, url):
    """`members` decides which of the two chips a leaf gets, `children` keeps the
    per-line chip off a container's line, `code` keeps both off a healthy node,
    `own_counted` keeps the node chip off one that is healthy itself above a failure,
    and `reason` is what there is to file — each read off the library's own node, on
    the page the library drew, through the context its slots hand over."""
    placed = sorted((placement, draft["summary"])
                    for placement, _label, draft in _drafts(rendered(shape)[url]))
    assert placed == sorted(EXPECTED[shape][url])


def test_a_draft_says_what_the_node_on_the_page_says(rendered):
    """Name, path, status and the time it was observed, as the library's node carries
    them. A renamed timestamp would read *not yet observed* in every draft and a
    renamed status *undefined* — and neither would move a chip."""
    [draft] = [draft for placement, _label, draft
               in _drafts(rendered("both")["/status/ci/reviews"])
               if placement == "node"]
    assert draft["summary"] == "/ci/reviews: review overdue"
    assert draft["customfield_10101"] == "reviews: review overdue"
    node, status, observed = _trailer(draft)[:3]
    assert (node, status) == ("node: /ci/reviews", "status: error")
    assert observed.startswith("observed: ")
    assert observed != "observed: not yet observed"


def test_every_draft_links_back_to_its_node_s_own_page(rendered):
    """The link is `url_for("status", …)` against the real application — the one
    endpoint name this package assumes. Where a chip is drawn its link has to be its
    own node's page; where the endpoint is gone every provider raises, the slot
    machinery contains it and no chip is drawn at all — so an empty page set fails
    here too, rather than passing with nothing checked."""
    seen = 0
    for shape in SHAPES:
        for url, page in rendered(shape).items():
            for _placement, _label, draft in _drafts(page):
                trailer = _trailer(draft)
                path = trailer[0].removeprefix("node: ")
                assert trailer[-1] == f"dashboard: http://localhost/status{path}", url
                seen += 1
    assert seen, "no draft on any page, so no link to follow"


def test_the_node_chip_is_the_heads_square_where_the_library_says_it_stands_in_one(
        served):
    """With `icon: jira` every node chip is little-sister's own square, named by its
    label, where the library hands the slot a `place` — the context key the slot
    gained when a node's actions moved into its head's row — and the label chip where
    it hands over none. A line's chip is never a square, and without the key no chip
    is: what the library that drew the page hands over decides which, not this test —
    asked of the process that served the page, since a path of this one's own may
    name another library."""
    square = served("square")
    heads = "place" in square.context
    seen = 0
    for url, page in square.pages.items():
        for chip in _chips(page):
            if chip["placement"] == "node":
                assert (chip["square"], chip["label"]) == (heads, "Jira all"), url
                seen += 1
            else:
                assert not chip["square"], url
    assert seen, "no node chip on any page, so nothing drawn to look at"
    assert not any(chip["square"] for page in served("both").pages.values()
                   for chip in _chips(page))
