"""Reading `config/jira.yaml`, and what registration does with what it found.

ADR-0001 decision 8 is the property under test: **a broken configuration costs the
button and nothing else**. Every failure below has to end in "no chip", a log line
that names the file, and an application that still starts.

The aspect lookup itself belongs to little-sister — resolving the configuration
roots is its job, and a tree that will not resolve is *its* refusal to start, not
a chip we quietly drop — so the lookup is replaced here rather than reproduced.
What is ours is everything after the path comes back.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from little_sister_jira import jira

MINIMAL = """
base_url: https://tracker.example.org/
project_id: "10000"
issue_type_id: "10002"
"""


@pytest.fixture(autouse=True)
def _forget_config():
    yield
    jira.use_config(None)


#: Everything `register()` asks of little-sister, in order — written by the two
#: fixtures below so an ordering assertion has something to assert against. A
#: lookup that recorded nothing would make "declared before it is read" true by
#: construction, which is a test that cannot fail.
CALLS: list[tuple[str, str]] = []


@pytest.fixture(autouse=True)
def _forget_calls():
    CALLS.clear()
    yield


@pytest.fixture
def aspect(monkeypatch, tmp_path):
    """Point the aspect lookup at a file this test writes, or at nothing."""
    def _install(body: str | None, *, name: str = "jira.yaml") -> Path | None:
        path = tmp_path / name
        if body is not None:
            path.write_text(body, encoding="utf-8")

        def _lookup(aspect: str) -> Path | None:
            CALLS.append(("read", aspect))
            return path if body is not None else None

        monkeypatch.setattr(jira, "sole_aspect_file", _lookup)
        return path if body is not None else None
    return _install


def test_no_configuration_file_means_no_chip(aspect, caplog):
    aspect(None)
    with caplog.at_level(logging.INFO):
        assert jira._load() is None
    assert "no jira.yaml in the configuration" in caplog.text


def test_a_readable_file_is_parsed(aspect):
    aspect(MINIMAL)
    config = jira._load()
    assert config is not None
    assert config.base_url == "https://tracker.example.org"    # trailing slash gone
    assert config.action("reason") is not None                 # no actions: block
    assert config.action("node") is None


def test_unreadable_yaml_costs_the_button_and_nothing_else(aspect, caplog):
    aspect("base_url: [unclosed\n")
    assert jira._load() is None
    assert "could not be read" in caplog.text


def test_a_document_that_is_not_a_mapping_costs_the_button(aspect, caplog):
    aspect("- not\n- a mapping\n")
    assert jira._load() is None
    assert "must be a mapping" in caplog.text


def test_a_file_the_parser_refuses_costs_the_button(aspect, caplog):
    aspect('project_id: "10000"\nissue_type_id: "10002"\n')   # no base_url
    assert jira._load() is None
    assert "no issue button" in caplog.text


def test_an_unknown_key_is_named_but_the_rest_still_loads(aspect, caplog):
    # A misspelled `project_id` would otherwise produce a button that quietly opens
    # the wrong project's form, so the key is named rather than shrugged off.
    aspect(MINIMAL + 'projekt_id: "10001"\n')
    config = jira._load()
    assert config is not None
    assert "projekt_id" in caplog.text


# --- registration ---------------------------------------------------------------

@pytest.fixture
def registered(monkeypatch):
    """Record what `register()` asks little-sister for, instead of asking it."""
    monkeypatch.setattr(jira.slots, "register",
                        lambda slot, package, template, context=None,
                        builtin=False: CALLS.append((slot, template)))
    monkeypatch.setattr(jira, "register_aspect",
                        lambda name: CALLS.append(("aspect", name)))
    return CALLS


def test_registration_declares_the_aspect_before_it_reads_it(aspect, registered):
    aspect(MINIMAL)
    jira.register()
    # Declaring before reading is a requirement rather than a courtesy: little-sister
    # resolves an aspect by looking its name up in `ASPECTS`, so `_load()` on an
    # undeclared `jira` raises `KeyError` instead of reporting no configuration — and
    # `_load` deliberately does not catch it (a failure of the configuration *tree* is
    # not ours to answer), so the import itself would fail and take the deployment's
    # boot with it, which is the opposite of decision 8. Both calls are recorded, so
    # swapping them fails here.
    assert registered.index(("aspect", "jira")) < registered.index(("read", "jira"))


def test_only_the_configured_chips_are_filled(aspect, registered):
    aspect(MINIMAL + "actions:\n  node:\n    label: Jira all\n")
    jira.register()
    assert ("node.actions", "node_actions.html") in registered
    assert ("reason.actions", "reason_actions.html") not in registered


def test_a_broken_configuration_still_fills_the_reason_slot(aspect, registered):
    # Nothing is drawn — the provider declines every line — but the filler is there,
    # so fixing the file and restarting is all it takes.
    aspect("- not a mapping\n")
    jira.register()
    assert ("reason.actions", "reason_actions.html") in registered


def test_a_placement_written_as_yaml_null_takes_the_defaults(aspect):
    # `node:` with nothing under it is null, not an empty mapping — and it is the
    # form an operator is likelier to write than `node: {}`.
    aspect(MINIMAL + "label: File it\nactions:\n  reason:\n  node:\n")
    config = jira._load()
    assert config is not None
    assert config.action("reason").label == "File it"
    assert config.action("node").label == "File it"
