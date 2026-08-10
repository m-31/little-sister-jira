"""The Jira chip: what goes into the pre-filled URL, and where it appears (ADR-0001).

No Flask request context here on purpose — the provider and the URL builder must be
usable (and testable) without one, and `_node_url` answers "" outside one, which is
the "no link" case the description handles.

Nothing here is anybody's real Jira: the ids are placeholders and the host is a
documentation domain. The two tests that read a file read `examples/jira.yaml`, the
shape this package ships — which is also what keeps that example honest, since a key
it grew that the parser does not know would fail here.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml
from little_sister.checks import CheckError

from little_sister_jira import jira

#: The annotated example this package ships — the one YAML document in the
#: repository, and the only one the parser is checked against.
EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "jira.yaml"


def _example(*, edited: bool = True) -> dict:
    """The shipped example, optionally with its placeholder host replaced.

    `base_url` is the one key an operator *must* edit, and the example's value is a
    deliberate non-host so that copying it unedited is refused rather than rendered
    (see the test below). Every other assertion about the example wants the document
    an operator would actually end up with, so it substitutes a real one.
    """
    body = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    if edited:
        body["base_url"] = "https://tracker.example.org"
    return body


@dataclass(frozen=True)
class FakeCode:
    name: str


@dataclass(frozen=True)
class FakeNode:
    """The shape `StatusSnapshot` presents to the provider, and nothing more."""
    path: str = "/platform/ci/actions"
    name: str = "actions"
    code: FakeCode = FakeCode("ERROR")
    timestamp: str | None = "2026-08-01T09:15:00"
    children: tuple[object, ...] = ()
    reason: tuple[str, ...] = ("workflow `build` failed", "and `test` after it")
    members: bool = False


BOTH = jira.JiraConfig(
    base_url="https://tracker.example.org",
    project_id="10000",
    issue_type_id="10002",
    fields={"customfield_10101": "{name}: {reason}"},
    actions={
        "reason": jira.ActionConfig(label="Jira"),
        "node": jira.ActionConfig(label="Jira all",
                                  fields={"customfield_10101": "{name}: {reasons}"}),
    },
)


CONFIG = jira.JiraConfig(
    base_url="https://tracker.example.org",
    project_id="10000",
    issue_type_id="10002",
    fields={"customfield_10101": "{name}: {reason}"},
)


def _query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query)


@pytest.fixture(autouse=True)
def _forget_config():
    """The parsed configuration is a module global read once at startup; a test that
    installs one must not decide the next test's answer."""
    yield
    jira.use_config(None)


def test_the_url_is_jiras_prefilled_create_form():
    url = jira.issue_url(CONFIG, FakeNode(), "workflow `build` failed")
    assert url.startswith(
        "https://tracker.example.org/secure/CreateIssueDetails!init.jspa?")
    query = _query(url)
    assert query["pid"] == ["10000"]
    assert query["issuetype"] == ["10002"]


def test_the_summary_leads_with_the_node_path():
    # A board shows the head of a summary and cuts the tail, so *which* thing broke
    # has to survive the cut.
    query = _query(jira.issue_url(CONFIG, FakeNode(), "workflow failed"))
    assert query["summary"] == ["/platform/ci/actions: workflow failed"]


def test_the_summary_is_one_line_and_clamped():
    reason = "line one\n\n```\nlots\nof\noutput\n```"
    config = jira.JiraConfig(base_url="https://t.example.org", project_id="1",
                             issue_type_id="2", summary_limit=30)
    summary = _query(jira.issue_url(config, FakeNode(), reason))["summary"][0]
    assert "\n" not in summary and "`" not in summary
    assert len(summary) == 30
    assert summary.endswith("…")


def test_the_description_carries_the_reason_whole_and_says_where_it_came_from():
    reason = "workflow `build` failed\n\n```\nexit 1\n```"
    body = _query(jira.issue_url(CONFIG, FakeNode(), reason))["description"][0]
    assert reason in body                      # uncut, fences and all
    assert "node: /platform/ci/actions" in body
    assert "status: error" in body
    assert "observed: 2026-08-01T09:15:00" in body
    # No request context here, so there is no absolute dashboard link to add.
    assert "dashboard:" not in body


def test_configured_fields_are_templated_not_formatted():
    # A reason routinely contains a brace; str.format would raise on it, and an
    # unknown token is left standing so a typo shows up in the draft.
    config = jira.JiraConfig(
        base_url="https://t.example.org", project_id="1", issue_type_id="2",
        fields={"customfield_10101": "{name} · {reason} · {nope}"})
    reason = 'json {"a": 1} rejected'
    value = _query(jira.issue_url(config, FakeNode(), reason))["customfield_10101"][0]
    assert value == f"actions · {reason} · {{nope}}"


def test_reserved_characters_are_encoded_once():
    reason = "500 on https://api.example.org/a?b=c&d=e — retry?"
    url = jira.issue_url(CONFIG, FakeNode(), reason)
    # One '?' in the whole URL: the query separator. Everything else is escaped.
    assert url.count("?") == 1
    assert reason in _query(url)["description"][0]


def test_the_provider_declines_a_container():
    # Placement policy is the filler's, not little-sister's: a container's reason is
    # a roll-up sentence, and the check that failed is what an issue should name.
    jira.use_config(CONFIG)
    node = FakeNode(children=(FakeNode(),))
    assert jira.reason_action(node=node, reason="something below is red",
                              index=0, surface="grid") is None


def test_the_provider_declines_a_healthy_leaf():
    jira.use_config(CONFIG)
    node = FakeNode(code=FakeCode("OK"))
    assert jira.reason_action(node=node, reason="all four replicas up",
                              index=0, surface="grid") is None


def test_the_provider_declines_when_there_is_no_configuration():
    jira.use_config(None)
    assert jira.reason_action(node=FakeNode(), reason="down", index=0,
                              surface="grid") is None


def test_the_provider_hands_the_template_a_url_a_label_and_a_title():
    jira.use_config(CONFIG)
    context = jira.reason_action(node=FakeNode(), reason="workflow failed",
                                 index=0, surface="grid")
    assert context is not None
    assert context["jira_label"] == "Jira"
    assert "/platform/ci/actions" in str(context["jira_title"])
    assert str(context["jira_url"]).startswith("https://tracker.example.org/secure/")


def test_every_surface_and_every_line_gets_the_same_chip():
    jira.use_config(CONFIG)
    first = jira.reason_action(node=FakeNode(), reason="x", index=0, surface="grid")
    second = jira.reason_action(node=FakeNode(), reason="x", index=3,
                                surface="check")
    assert first == second


def test_config_requires_the_three_ids():
    for body in ({"project_id": "1", "issue_type_id": "2"},
                 {"base_url": "https://t.example.org", "issue_type_id": "2"},
                 {"base_url": "https://t.example.org", "project_id": "1"}):
        with pytest.raises(CheckError):
            jira._parse(body, "config/jira.yaml")


def test_config_strips_a_trailing_slash_from_the_base_url():
    parsed = jira._parse({"base_url": "https://t.example.org/", "project_id": "1",
                          "issue_type_id": "2"}, "config/jira.yaml")
    assert parsed.base_url == "https://t.example.org"


def test_config_rejects_a_non_mapping_fields_block():
    with pytest.raises(CheckError):
        jira._parse({"base_url": "https://t.example.org", "project_id": "1",
                     "issue_type_id": "2", "fields": ["nope"]}, "config/jira.yaml")


def test_the_shipped_example_parses():
    # The example an operator copies, checked against the parser that reads it: a
    # key it grew that the parser does not know would be a documented typo.
    body = _example()
    parsed = jira._parse(body, str(EXAMPLE))
    assert parsed.project_id and parsed.issue_type_id
    assert not parsed.base_url.endswith("/")
    assert set(body) <= jira._KEYS


def test_the_shipped_examples_placeholder_host_is_refused():
    # The example's `base_url` is `https://<your-site>.atlassian.net`. Copied
    # unedited it must cost the button — a chip pointing at a host that cannot
    # resolve looks exactly like a working one until somebody presses it.
    with pytest.raises(CheckError):
        jira._parse(_example(edited=False), str(EXAMPLE))


# --- the node chip (ADR-0001 amendment) ----------------------------------------

def test_no_actions_block_means_the_reason_chip_only():
    # Installing the node chip is a decision: a deployment that says nothing keeps
    # the per-line chip alone, and gets no button it never asked for.
    parsed = jira._parse({"base_url": "https://t.example.org", "project_id": "1",
                          "issue_type_id": "2"}, "config/jira.yaml")
    assert parsed.action("reason") is not None
    assert parsed.action("node") is None


def test_a_placement_inherits_the_defaults_and_overrides_one_key():
    parsed = jira._parse({
        "base_url": "https://t.example.org", "project_id": "1", "issue_type_id": "2",
        "label": "Jira", "fields": {"customfield_1": "{name}"},
        "actions": {"reason": {}, "node": {"label": "File all"}},
    }, "config/jira.yaml")
    assert parsed.action("reason").label == "Jira"
    assert parsed.action("node").label == "File all"
    # fields were not overridden, so both inherit the file's default
    assert parsed.action("node").fields == {"customfield_1": "{name}"}


def test_a_placement_may_override_its_fields():
    parsed = jira._parse({
        "base_url": "https://t.example.org", "project_id": "1", "issue_type_id": "2",
        "fields": {"customfield_1": "{reason}"},
        "actions": {"node": {"fields": {"customfield_1": "{reasons}"}}},
    }, "config/jira.yaml")
    assert parsed.action("node").fields == {"customfield_1": "{reasons}"}
    assert parsed.action("reason") is None      # named nowhere, so not offered


def test_an_unknown_placement_warns_and_is_skipped(caplog):
    parsed = jira._parse({
        "base_url": "https://t.example.org", "project_id": "1", "issue_type_id": "2",
        "actions": {"card": {}, "node": {}},
    }, "config/jira.yaml")
    assert parsed.action("node") is not None
    assert "card" in caplog.text and "node, reason" in caplog.text


def test_a_non_mapping_actions_block_is_refused():
    with pytest.raises(CheckError):
        jira._parse({"base_url": "https://t.example.org", "project_id": "1",
                     "issue_type_id": "2", "actions": ["node"]}, "config/jira.yaml")


def test_the_node_draft_summarises_the_first_line_and_carries_them_all():
    jira.use_config(BOTH)
    context = jira.node_action(node=FakeNode(), surface="grid")
    assert context is not None
    assert context["jira_label"] == "Jira all"
    query = _query(str(context["jira_url"]))
    # summary: the node path and its *first* line, flattened
    assert query["summary"] == ["/platform/ci/actions: workflow build failed"]
    # description: every line, uncut, fences and all
    body = query["description"][0]
    assert "workflow `build` failed" in body
    assert "and `test` after it" in body


def test_the_reasons_token_expands_to_every_line():
    jira.use_config(BOTH)
    context = jira.node_action(node=FakeNode(), surface="check")
    value = _query(str(context["jira_url"]))["customfield_10101"][0]
    assert value == "actions: workflow `build` failed\nand `test` after it"


def test_the_node_chip_keeps_containers():
    # The difference from the per-line chip: node.actions renders in the card head,
    # and a card at depth 1 IS a container — declining them would mean the chip never
    # appeared on the dashboard at all.
    jira.use_config(BOTH)
    node = FakeNode(children=(FakeNode(),), reason=("something below is red",))
    assert jira.node_action(node=node, surface="grid") is not None
    assert jira.reason_action(node=node, reason="x", index=0,
                              surface="grid") is None


def test_the_node_chip_declines_a_node_with_no_reasons():
    jira.use_config(BOTH)
    node = FakeNode(children=(FakeNode(),), reason=())
    assert jira.node_action(node=node, surface="grid") is None


def test_a_single_member_keeps_only_its_reason_chip():
    jira.use_config(BOTH)
    node = FakeNode(reason=("one finding",), members=True)
    assert jira.node_action(node=node, surface="grid") is None
    assert jira.reason_action(node=node, reason="one finding", index=0,
                              surface="grid") is not None


def test_several_members_also_offer_the_all_members_chip():
    jira.use_config(BOTH)
    node = FakeNode(reason=("first finding", "second finding"), members=True)
    context = jira.node_action(node=node, surface="grid")
    assert context is not None
    assert context["jira_label"] == "Jira all"


def test_a_single_member_keeps_a_node_only_action():
    jira.use_config(jira.JiraConfig(
        base_url="https://t.example.org", project_id="1", issue_type_id="2",
        actions={"node": jira.ActionConfig(label="Jira all")}))
    node = FakeNode(reason=("one finding",), members=True)
    assert jira.node_action(node=node, surface="grid") is not None


def test_the_node_chip_declines_a_healthy_node():
    jira.use_config(BOTH)
    assert jira.node_action(node=FakeNode(code=FakeCode("OK")),
                            surface="grid") is None


def test_neither_chip_appears_without_a_configuration():
    jira.use_config(None)
    assert jira.node_action(node=FakeNode(), surface="grid") is None
    assert jira.reason_action(node=FakeNode(), reason="x", index=0,
                              surface="grid") is None


def test_a_placement_that_is_not_offered_draws_nothing():
    jira.use_config(jira.JiraConfig(
        base_url="https://t.example.org", project_id="1", issue_type_id="2",
        actions={"reason": jira.ActionConfig()}))
    assert jira.node_action(node=FakeNode(), surface="grid") is None
    assert jira.reason_action(node=FakeNode(), reason="x", index=0,
                              surface="grid") is not None


def test_the_shipped_example_offers_both_chips():
    parsed = jira._parse(_example(), str(EXAMPLE))
    assert parsed.action("reason") is not None
    assert parsed.action("node") is not None
    assert parsed.action("node").label == "Jira all"


# --- the placements step aside for each other -----------------------------------

def test_prose_with_both_placements_offered_keeps_only_the_node_chip():
    # A failure message and its stack trace are one condition. With both chips
    # configured, a chip per line is the same ticket offered three times — one of
    # them about a traceback, which is the case the node chip exists for.
    jira.use_config(BOTH)
    node = FakeNode(reason=("deploy failed", "```", "Traceback…"), members=False)
    assert jira.node_action(node=node, surface="grid") is not None
    for index, line in enumerate(node.reason):
        assert jira.reason_action(node=node, reason=line, index=index,
                                  surface="grid") is None


def test_prose_keeps_its_line_chips_when_that_is_the_only_placement_offered():
    # Stepping aside is only ever in favor of a chip that is actually there: a
    # deployment offering only `reason` must not lose its sole action on prose.
    jira.use_config(CONFIG)                       # no actions: block ⇒ reason only
    node = FakeNode(reason=("deploy failed", "Traceback…"), members=False)
    assert jira.reason_action(node=node, reason="deploy failed", index=0,
                              surface="grid") is not None


def test_members_are_untouched_by_the_prose_rule():
    # Where a check declares its findings, each line is separately actionable and
    # keeps its own chip — with the node chip beside it as the file-them-all.
    jira.use_config(BOTH)
    node = FakeNode(reason=("first finding", "second finding"), members=True)
    assert jira.reason_action(node=node, reason="first finding", index=0,
                              surface="grid") is not None
    assert jira.node_action(node=node, surface="grid") is not None


# --- base_url is where the browser goes, so it is checked ------------------------

@pytest.mark.parametrize("value", [
    "https://<your-site>.atlassian.net",       # the example, copied unedited
    "tracker.example.org",                     # no scheme
    "ftp://tracker.example.org",               # not a browser scheme
    "https://",                                # no host
    "https:///jira",                           # no host, with a path
    "https://tracker example.org",             # a space is not a host
    "https://tracker.example.org?a=b",         # would put two '?' on the URL
    "https://tracker.example.org#frag",
])
def test_a_base_url_that_is_not_a_jira_is_refused(value):
    with pytest.raises(CheckError):
        jira._parse({"base_url": value, "project_id": "1", "issue_type_id": "2"},
                    "config/jira.yaml")


@pytest.mark.parametrize("value", [
    "https://tracker.example.org",
    "http://tracker.example.org",
    "https://tracker.example.org:8443",
    "https://tracker.example.org/jira",        # a context path is normal
    "https://jira-1.example.org/",
])
def test_a_real_base_url_is_accepted(value):
    parsed = jira._parse({"base_url": value, "project_id": "1",
                          "issue_type_id": "2"}, "config/jira.yaml")
    assert parsed.base_url == value.rstrip("/")


def test_a_refused_base_url_costs_the_button_and_nothing_else(caplog):
    # Same category as every other bad value: logged, no chip, application intact.
    # Before this check it was the exception — a rendered, clickable dead link.
    with pytest.raises(CheckError) as refusal:
        jira._parse({"base_url": "https://<your-site>.atlassian.net",
                     "project_id": "1", "issue_type_id": "2"}, "config/jira.yaml")
    assert "<your-site>" in str(refusal.value)      # names what it got


def test_a_container_declaring_one_member_still_gets_a_chip():
    # The hole two mirror rules can leave: `reason_action` declines every container,
    # so the node chip standing down "because the member has its own" would leave
    # this node with nothing at all — and it renders on a card head, where nothing
    # else fills in.
    jira.use_config(BOTH)
    node = FakeNode(children=(FakeNode(),), reason=("one finding",), members=True)
    assert jira.reason_action(node=node, reason="one finding", index=0,
                              surface="grid") is None
    assert jira.node_action(node=node, surface="grid") is not None


def test_no_node_shape_loses_every_chip():
    # The property behind the rule above, over the shapes a snapshot can present.
    jira.use_config(BOTH)
    for children in ((), (FakeNode(),)):
        for members in (False, True):
            for reasons in (("only line",), ("first", "second")):
                node = FakeNode(children=children, members=members,
                                reason=reasons)
                drawn = [jira.node_action(node=node, surface="grid")] + [
                    jira.reason_action(node=node, reason=line, index=i,
                                       surface="grid")
                    for i, line in enumerate(reasons)]
                assert any(drawn), (
                    f"no chip anywhere: children={bool(children)} "
                    f"members={members} reasons={len(reasons)}")


@pytest.mark.parametrize("value", ["https://jira.example.org#",
                                   "https://jira.example.org?"])
def test_a_bare_trailing_query_or_fragment_is_refused(value):
    # Both parse to an *empty* query and fragment — falsy, so a check on the parsed
    # parts misses them. `…org#` makes the entire chip URL a fragment: the browser
    # opens the Jira home page and nothing says why.
    with pytest.raises(CheckError):
        jira._parse({"base_url": value, "project_id": "1", "issue_type_id": "2"},
                    "config/jira.yaml")


@pytest.mark.parametrize("value", [
    "https://[::1]:8080",                  # an IPv6 literal
    "http://[2001:db8::1]/jira",
    "https://jira.köln.de",                # an internationalized domain
    "https://jira.example.org.",           # a trailing-dot FQDN
    "https://10.0.0.7:8080/jira",
])
def test_a_real_but_unusual_host_is_not_refused(value):
    # A false refusal costs a working deployment its chips at startup, which is a
    # worse failure than the placeholder this check exists to catch.
    assert jira._parse({"base_url": value, "project_id": "1",
                        "issue_type_id": "2"}, "config/jira.yaml").base_url


def test_a_base_url_is_normalized_not_echoed():
    # urlsplit strips ASCII tabs and newlines, so a value carrying one would
    # validate clean and then land in an href.
    parsed = jira._parse({"base_url": "https://jira.example\norg/",
                          "project_id": "1", "issue_type_id": "2"},
                         "config/jira.yaml")
    assert "\n" not in parsed.base_url
