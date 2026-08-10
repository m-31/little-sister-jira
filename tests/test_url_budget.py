"""The transport budget: a draft that will not fit a request line is cut, not sent.

`summary_limit` bounds what a Jira board shows. Nothing bounded what the *browser*
sends, and everything a draft carries travels in a `GET` query string where
percent-encoding roughly triples a traceback:

    prose leaf, 1680-char traceback   → 4721 characters of URL
    node chip, 10 member lines        → 2727
    node chip, 25 member lines        → 5802
    node chip, 40 member lines        → 8877, past the common 8 KB request line

Forty findings under one critical band is not exotic — it is exactly the case the
node chip exists for. Past the server's limit the operator gets a 414 from Jira
instead of a form, which is worse than no chip: the chip still looks like it works.

What must survive a cut is asserted here as hard as the length itself — the ids, the
summary, and the `dashboard:` link that makes cutting safe in the first place.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

import pytest

from little_sister_jira import jira

TRACEBACK = ("deploy failed\n\n```\n"
             + "\n".join(f'  File "/srv/app/handler_{n}.py", line {n}, in handle'
                         for n in range(40))
             + "\n```")


@dataclass(frozen=True)
class Code:
    name: str = "ERROR"


@dataclass(frozen=True)
class Node:
    path: str = "/platform/ci/actions"
    name: str = "actions"
    code: Code = Code()
    timestamp: str | None = "2026-08-01T09:15:00"
    children: tuple[object, ...] = ()
    reason: tuple[str, ...] = ("deploy failed",)
    members: bool = False


def findings(count: int) -> Node:
    """A band of `count` addressable members, the shape the node chip is for."""
    return Node(reason=tuple(
        f"`finding-{n:04d}` policy violation on `resource-{n}` — investigate"
        for n in range(count)), members=True)


def config(**overrides) -> jira.JiraConfig:
    settings = {"base_url": "https://tracker.example.org", "project_id": "10000",
                "issue_type_id": "10002",
                "fields": {"customfield_10101": "{name}: {reasons}"}}
    settings.update(overrides)
    return jira.JiraConfig(**settings)


def _query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query, keep_blank_values=True)


@pytest.mark.parametrize("node", [Node(reason=(TRACEBACK,)), findings(10),
                                  findings(25), findings(40), findings(400)])
def test_no_draft_exceeds_the_limit(node):
    url = jira.issue_url(config(), node, node.reason[0],
                         body="\n".join(node.reason))
    assert len(url) <= jira.DEFAULT_URL_LIMIT


def test_the_ids_and_the_summary_are_never_what_gives():
    node = findings(400)
    query = _query(jira.issue_url(config(), node, node.reason[0],
                                  body="\n".join(node.reason)))
    assert query["pid"] == ["10000"]
    assert query["issuetype"] == ["10002"]
    # the summary is clamped by summary_limit and by nothing else
    # The whole summary, not a prefix of it: a tail cut would still start with the
    # node path and still be under summary_limit, so anything weaker than equality
    # passes while the board line is being eaten.
    assert query["summary"] == [jira._summary(config(), node, node.reason[0])]
    assert not query["summary"][0].endswith("…")


def test_a_cut_body_still_says_so_and_still_links_back(dashboard_context):
    node = findings(400)
    body = _query(jira.issue_url(config(), node, node.reason[0],
                                 body="\n".join(node.reason)))["description"][0]
    assert jira.TRUNCATED in body
    # The trailer is what survives — and its dashboard link is the whole reason
    # cutting the text above it is safe rather than lossy.
    assert "node: /platform/ci/actions" in body
    assert "status: error" in body
    assert "dashboard: https://monitor.example.org/status/platform/ci/actions" in body
    assert body.index(jira.TRUNCATED) < body.index("dashboard:")


def test_an_ordinary_draft_is_untouched():
    # The clamp must not become a tax on the common case: below the limit the URL is
    # what it always was, with no marker and nothing dropped.
    node = Node(reason=("workflow `build` failed", "and `test` after it"))
    url = jira.issue_url(config(), node, node.reason[0],
                         body="\n".join(node.reason))
    body = _query(url)["description"][0]
    assert jira.TRUNCATED not in body
    assert "workflow `build` failed\nand `test` after it" in body
    assert _query(url)["customfield_10101"][0].endswith("and `test` after it")


def test_a_short_field_is_not_cut_to_make_room_for_a_long_one():
    # Fair shares, smallest first: the traceback is going to be cut anyway, so there
    # is nothing to buy by also cutting a field that would have fitted.
    node = findings(200)
    url = jira.issue_url(config(fields={"customfield_10101": "{name}: {status}",
                                        "customfield_10102": "{reasons}"}),
                         node, node.reason[0], body="\n".join(node.reason))
    query = _query(url)
    assert query["customfield_10101"] == ["actions: ERROR"]      # whole
    assert query["customfield_10102"][0].endswith("…")           # cut
    assert len(url) <= jira.DEFAULT_URL_LIMIT


def test_two_long_fields_cut_each_other_evenly():
    node = findings(200)
    lines = "\n".join(node.reason)
    url = jira.issue_url(config(fields={"customfield_10101": "{reasons}",
                                        "customfield_10102": "{reasons}"}),
                         node, node.reason[0], body=lines)
    query = _query(url)
    first, second = (len(query[key][0]) for key in
                     ("customfield_10101", "customfield_10102"))
    assert first > 0 and second > 0      # `0 == 0` is not evenness
    assert abs(first - second) <= 2      # the same share, not first-come
    assert len(url) <= jira.DEFAULT_URL_LIMIT


def test_the_limit_is_a_knob_because_the_ceiling_is_the_deployment_s():
    node = findings(400)
    lines = "\n".join(node.reason)
    for limit in (900, 2000, 6000, 12000):
        url = jira.issue_url(config(url_limit=limit), node, node.reason[0],
                             body=lines)
        assert len(url) <= limit, f"{limit}: {len(url)}"


def test_a_budget_that_only_fits_the_trailer_keeps_the_link_back(dashboard_context):
    # The order things are given up in: the reason first, the marker and the link
    # back last, because the link is what makes losing the reason survivable.
    node = Node(reason=(TRACEBACK,))
    url = jira.issue_url(config(url_limit=1200), node, TRACEBACK, body=TRACEBACK)
    body = _query(url)["description"][0]
    assert len(url) <= 1200
    assert jira.TRUNCATED in body
    assert "dashboard: https://monitor.example.org/status/platform/ci/actions" in body


def test_below_the_floor_everything_that_can_give_has_given(dashboard_context):
    # The ids and the summary are never cut, so a limit under what *they* cost is a
    # limit that cannot be met — and the one thing that must not happen is a crash or
    # a draft that quietly keeps a body it was told it had no room for. Even the link
    # back goes here: a URL the server refuses is not a draft anybody reads.
    node = findings(400)
    url = jira.issue_url(config(url_limit=50), node, node.reason[0],
                         body="\n".join(node.reason))
    query = _query(url)
    assert query["pid"] == ["10000"] and query["issuetype"] == ["10002"]
    assert query["summary"][0].startswith("/platform/ci/actions: ")
    # Every value that could give has given, right down to empty. What is left over
    # the limit is the part no setting can shrink: the ids, the summary, and the
    # parameter names themselves.
    assert query["description"] == [""]
    assert query["customfield_10101"] == [""]
    assert url.endswith("&description=&customfield_10101=")


def test_the_shares_never_hand_out_more_room_than_there_is():
    assert sum(jira._shares({"a": 10, "b": 10, "c": 10}, 12).values()) <= 12
    assert sum(jira._shares({"a": 1, "b": 100}, 50).values()) <= 50
    assert jira._shares({"a": 1, "b": 100}, 50) == {"a": 1, "b": 49}
    assert jira._shares({"a": 5, "b": 5}, 100) == {"a": 5, "b": 5}      # no waste
    assert jira._shares({"a": 5}, -10) == {"a": 0}                      # no negatives


def test_fitting_measures_the_encoded_length_not_the_characters():
    # A newline costs three characters encoded, so a character-count budget would be
    # wrong by exactly the amount a traceback is made of.
    assert jira._fit("\n\n\n\n", 6) == "\n\n"
    assert jira._fit("abcd", 2) == "ab"
    assert jira._fit("abcd", 99) == "abcd"
    assert jira._fit("abcd", 0) == ""


@pytest.mark.parametrize("limit", [900, 1500, 3000, 6000, 20000])
@pytest.mark.parametrize("count", [0, 1, 2, 7, 40, 137, 400])
def test_the_limit_holds_across_every_shape_and_every_budget(limit, count,
                                                             dashboard_context):
    # The sweep that earns the arithmetic. The first version of this clamp was three
    # characters over at one budget out of four, because a newline costs three
    # characters once encoded and the separator before the marker was not counted.
    node = findings(count) if count else Node(reason=(TRACEBACK,))
    lines = "\n".join(node.reason)
    settings = config(url_limit=limit,
                      fields={"customfield_10101": "{reasons}",
                              "customfield_10102": "{name}: {status}"})
    for body in (None, lines):
        url = jira.issue_url(settings, node, node.reason[0], body=body)
        assert len(url) <= limit, f"{count} lines, limit {limit}: {len(url)}"


def test_a_configured_description_field_is_the_operators_body(dashboard_context):
    # `description` is a Jira field id like any other, so `fields:` may set it. The
    # clamp must cut *that* body rather than rebuild the stock one — a substitution
    # that would work in every test an operator ran and vanish on the long drafts
    # this budget exists for.
    node = findings(400)
    settings = config(fields={"description": "OURS: {reasons}"})
    for limit, cut in ((100_000, False), (jira.DEFAULT_URL_LIMIT, True)):
        body = _query(jira.issue_url(config(url_limit=limit,
                                            fields=settings.fields),
                                     node, node.reason[0],
                                     body="\n".join(node.reason)))["description"][0]
        assert body.startswith("OURS: "), f"limit {limit}"
        assert body.endswith("…") is cut
        assert "dashboard:" not in body      # their body, so our trailer is not in it


def test_a_budget_that_holds_only_the_trailer_keeps_the_link_over_the_marker(
        dashboard_context):
    # Cutting `marker + trailer` from the tail would delete the `dashboard:` line
    # and keep the sentence promising it — a body that is one broken reference.
    node = Node(reason=(TRACEBACK,))
    for limit in range(700, 1000, 10):
        body = _query(jira.issue_url(config(url_limit=limit), node, TRACEBACK,
                                     body=TRACEBACK))["description"][0]
        if not body:
            continue
        assert "dashboard: https://monitor.example.org" in body, f"limit {limit}"


def test_a_port_out_of_range_is_refused():
    from little_sister.checks import CheckError

    with pytest.raises(CheckError):
        jira._parse({"base_url": "https://jira.example.org:99999",
                     "project_id": "1", "issue_type_id": "2"}, "config/jira.yaml")
