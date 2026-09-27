"""The link back into the dashboard — and the one name here that little-sister
does not promise.

Every other test runs outside a Flask request context, where `_node_url` answers
`""` and the description simply carries no link. That leaves the branch that
matters untested: inside a request the draft gains an **absolute** URL, because it
is read inside Jira where a relative path means nothing.

It is also one of the module's two couplings outside little-sister's promised
surface (its `architecture.md` §11, which names neither `app` nor its routes; the
node's attributes are the other): the URL is built with `url_for("status", …)`, so
the **endpoint name** `status` is a string this package assumes. A rename in the
library is permitted without a version bump and would not move the API epoch; what
would happen is a `BuildError` per chip per render, contained by the slot machinery
and therefore silent apart from a log. These tests cannot see that happen: the
stand-in below registers the name itself, so it agrees with this package by
construction. `test_real_page.py` renders the installed library's own pages and is
what fails if the route moves; what is left here is the branch — an absolute link
inside a request, none outside one.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

import pytest
from flask import Flask

from little_sister_jira import jira

CONFIG = jira.JiraConfig(base_url="https://tracker.example.org",
                         project_id="10000", issue_type_id="10002",
                         fields={"customfield_10101": "{url}"})


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
    reason: tuple[str, ...] = ("workflow failed",)
    members: bool = False


@pytest.fixture
def dashboard():
    """A stand-in for little-sister's dashboard: one route, named `status`.

    The name is the contract this module writes against — not the app, not the URL
    shape — so that is what the stand-in reproduces.
    """
    app = Flask(__name__)
    app.add_url_rule("/status/<path:branch>", "status", lambda branch: "")
    with app.test_request_context("/", base_url="https://monitor.example.org"):
        yield


def _query(url: str) -> dict[str, list[str]]:
    # `keep_blank_values`, because one case below is a field that expands to
    # nothing: the parameter is still on the URL, and dropping it here would make
    # "no link" indistinguishable from "no such field".
    return parse_qs(urlsplit(url).query, keep_blank_values=True)


def test_the_description_links_back_absolutely(dashboard):
    body = _query(jira.issue_url(CONFIG, Node(), "workflow failed"))["description"][0]
    assert "dashboard: https://monitor.example.org/status/platform/ci/actions" in body


def test_the_url_token_is_the_same_absolute_link(dashboard):
    value = _query(jira.issue_url(CONFIG, Node(),
                                  "workflow failed"))["customfield_10101"][0]
    assert value == "https://monitor.example.org/status/platform/ci/actions"


def test_outside_a_request_there_is_simply_no_link():
    body = _query(jira.issue_url(CONFIG, Node(), "workflow failed"))["description"][0]
    assert "dashboard:" not in body
    assert _query(jira.issue_url(CONFIG, Node(),
                                 "workflow failed"))["customfield_10101"] == [""]
