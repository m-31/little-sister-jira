"""Raise a Jira issue from a node, or from one of its reason lines (ADR-0001).

The operator's move when a check goes red is usually the same one: open Jira, create
an issue, paste in what the dashboard already says. This fills little-sister's
**template slots** (little-sister ADR-0034) with a chip that is a plain link to Jira's
``CreateIssueDetails!init.jspa`` form, pre-filled from what the dashboard is showing.

**Two placements, because a ticket is about one of two things.** Where a check
declares its findings as *members* (little-sister ADR-0036), each line is separately
actionable and the chip belongs on the line: ``reason.actions``. Where the reasons are
*prose* — a failure message and its stack trace are one condition — there is one thing
to file and the chip belongs to the node, in its head on the wall and on its own page.
A per-line chip there would offer to raise a ticket about a stack trace.

**Where both placements are offered, each steps aside where the other is the right
subject** — and both rules are enforced here rather than left to the configuration,
because whether a node's reasons are members is a property of the *check*, and no
deployment can express "per line for these nodes, per node for those" in one file. So
a node with exactly one member declines the node chip (that member's own chip is the
same action), and a **prose** node declines the per-line chips (the node chip already
covers the condition, and a chip per line would offer to file a stack trace). A
deployment that offers only one placement keeps it in every case: stepping aside is
only ever in favor of a chip that is actually there.

**The node chip stands where the failure is.** A branch with a line of its own — a
check's coverage sentence, *12 functions in scope* — shows the color of whatever fails
beneath it, and a draft written from its lines would file that failure under the
branch's own reading. So the node chip is declined on a node whose **own** status is OK,
whatever its children's, and the node that failed keeps its chip.

**In a head's row the node chip may be a square** — the package's own glyph, a plus on
an issue card, with the label as its tooltip and its accessible name — where the
deployment writes ``icon: jira`` in its ``actions.node`` block and the library says the
chip stands in a head (the slot's ``place``, which little-sister hands over from 0.3.21
on). The square is little-sister's own, the one its actions are drawn in; without the
key, or on a library that does not say where, the chip wears its label as it always
has.

**A draft is bounded by its transport, not by the display.** Everything the chip
carries travels in a `GET` query string, where percent-encoding roughly triples a
traceback; past the server's request-line limit the operator gets a 414 from Jira
instead of a form, which is worse than no chip because the chip still looks like it
works. So the whole URL is clamped to :data:`DEFAULT_URL_LIMIT` characters
(``url_limit``), cutting the description and the configured fields — never the ids or
the summary — and a cut body keeps the link back to the node for as long as there is
room for it at all, which is what makes cutting safe. Below that there is no draft
worth protecting: a URL the server refuses is not one anybody reads.

Either way **Jira's own form is what opens** — nothing is created behind the operator's
back, no credentials are needed here, and the person editing the draft is whoever is
logged in to Jira in that browser. That is also why nothing here pins a ``reporter``:
a hard-coded account id would file everyone's tickets under one name. A deployment
that wants one anyway can set it as a field, and owns that choice.

The shape follows the seam: **this module computes values, the templates render HTML**
(``templates/reason_actions.html``, ``templates/node_actions.html``). Nothing here
builds markup, so the reason text — which a check assembled out of captured output —
is escaped by little-sister's own Jinja, exactly as it is everywhere else
(little-sister ADR-0018).

The ids live in ``config/jira.yaml`` in the installing deployment's configuration —
a configuration aspect **this package** registers (little-sister ADR-0035), so
changing a project, an issue type or which chips are offered is an edit and a restart
rather than a code change. Nothing in that file is a credential, which is why no
secret reference (little-sister ADR-0023) is involved.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import quote_plus, urlencode, urlsplit

import yaml
from flask import has_request_context, url_for
from little_sister import slots, values
from little_sister.checks import CheckError
from little_sister.config_dir import register_aspect, sole_aspect_file

#: This package's own logger. little-sister does not promise its ``logger`` object
#: to dependent packages — what it promises is that it never switches propagation
#: off, so an ordinary module logger's records land in the same place, under a name
#: that says which package wrote them (little-sister architecture.md §11).
logger = logging.getLogger(__name__)

#: The configuration aspect this package adds: ``config/jira.yaml``.
ASPECT = "jira"

#: Jira's pre-filled create-issue form. Everything else on the URL is a field.
CREATE_PATH = "/secure/CreateIssueDetails!init.jspa"

#: Jira refuses a summary over 255 characters, and a summary that long is unreadable
#: in a board anyway. The default leaves room for the node path in front of it.
DEFAULT_SUMMARY_LIMIT = 200

#: How long the whole chip URL may get. Everything a draft carries travels in a
#: ``GET`` query string, and a server refuses a request line past its own bound with
#: a 414 — Tomcat's ``maxHttpHeaderSize`` and nginx's ``large_client_header_buffers``
#: both default to **8 KB**, and Tomcat's covers the headers too. This default leaves
#: roughly two kilobytes of those, which a logged-in Jira session can easily use in
#: cookies alone. It is deliberately a knob: the real ceiling belongs to the Jira an
#: installation talks to, and nothing here can discover it.
DEFAULT_URL_LIMIT = 6000

#: What a cut description says before its trailer, so an operator reading a draft
#: knows the text continues. The trailer's ``dashboard:`` link is where it continues,
#: which is the whole reason cutting is safe.
TRUNCATED = "… truncated — the full text is on the dashboard below."

#: What may never appear in a ``base_url``'s host. A denylist rather than a pattern
#: for the host itself, on purpose: the point is not to validate somebody's DNS —
#: it is that ``<your-site>.atlassian.net``, copied unedited out of an example, is
#: not a host at all. A pattern tight enough to be satisfying refuses real
#: deployments — an IPv6 literal, an internationalized domain, a trailing-dot
#: FQDN — and each of those costs a working installation its chips at startup,
#: which is a worse failure than the one being prevented.
_NOT_IN_HOST = re.compile(r"[\s<>\"{}|\\^`]")

#: The keys ``config/jira.yaml`` may carry. Anything else is a typo worth naming:
#: a misspelled ``project_id`` would otherwise produce a button that quietly opens
#: the wrong project's form.
_KEYS = frozenset({"base_url", "project_id", "issue_type_id", "label",
                   "summary_limit", "url_limit", "fields", "actions"})

#: The placements an ``actions:`` block may name, and the slot each fills.
PLACEMENTS = {"reason": "reason.actions", "node": "node.actions"}

#: The keys each placement may carry — what differs between chips — and the node
#: chip's icon, which is its own: a line's chip keeps its label wherever it stands, as
#: the library's line actions do. The ids and the summary limit are properties of the
#: *project*, not of a placement.
_ACTION_KEYS = {"reason": frozenset({"label", "fields"}),
                "node": frozenset({"label", "fields", "icon"})}

#: The icons this package draws itself, by the name ``icon:`` gives: its own drawing,
#: a plus on an issue card, in ``templates/node_actions.html``. The name is the one
#: the library's own icon registry knows Jira by — its built-in glyph, or a
#: deployment's own mark under that name — so the file a deployment writes today is
#: the file it keeps; a name drawn from that registry waits for little-sister to
#: promise a slot filler the lookup its own actions use.
OWN_ICONS = frozenset({"jira"})

#: Where the slot says the node chip stands (``place``), the places that are a
#: head's row — a card's head, a nested box's, a node page's frame — which is where
#: little-sister draws an action with an icon as a square. A place this package
#: does not know is given the label chip.
HEAD_ROWS = frozenset({"card", "box", "frame"})


@dataclass(frozen=True)
class ActionConfig:
    """How one chip differs from the file's defaults: its label, its fields and — the
    node chip's alone — its icon."""
    label: str = "Jira"
    #: Extra Jira fields by id (``customfield_10101: "{name}: {reason}"``), each a
    #: template over the tokens in :func:`expand`. A custom field's *number* is a
    #: fact about one Jira project, so it belongs in config and not in this file.
    fields: Mapping[str, str] = field(default_factory=dict)
    #: The icon the node chip is drawn with in a head's row, by name — one of
    #: :data:`OWN_ICONS` — or ``""`` for the label chip.
    icon: str = ""


@dataclass(frozen=True)
class JiraConfig:
    """What ``config/jira.yaml`` says. Only the first three are required.

    ``actions`` says which chips are offered, keyed by placement
    (:data:`PLACEMENTS`). An absent block means **the reason chip only**, which is
    what the deployment this extension grew up in had before the node chip existed
    — so an upgrade adds no button nobody asked for.
    """
    base_url: str
    project_id: str
    issue_type_id: str
    label: str = "Jira"
    summary_limit: int = DEFAULT_SUMMARY_LIMIT
    #: The transport bound of :data:`DEFAULT_URL_LIMIT` — a property of the server
    #: the browser will hand this URL to, which is why it sits beside the project's
    #: ids rather than on a placement.
    url_limit: int = DEFAULT_URL_LIMIT
    fields: Mapping[str, str] = field(default_factory=dict)
    actions: Mapping[str, ActionConfig] = field(default_factory=dict)

    def action(self, placement: str) -> ActionConfig | None:
        """The chip configured for ``placement``, or ``None`` when it is not offered
        — which is how a deployment chooses to have only per-reason tickets, or only
        whole-node ones.

        No ``actions`` at all means **the reason chip on the file's defaults**: the
        rule lives here rather than in the parser so a configuration built in code
        behaves exactly like a file that omits the block.
        """
        if not self.actions:
            return (ActionConfig(label=self.label, fields=self.fields)
                    if placement == "reason" else None)
        return self.actions.get(placement)


#: The parsed configuration, or ``None`` when there is none or it is unusable. Read
#: once at registration: a monitor's configuration does not change while it runs, and
#: an operator who edits the file wants the restart to tell them whether it parsed.
_config: JiraConfig | None = None


def register() -> None:
    """Declare the ``jira`` aspect, read it, and fill the slots it asks for.

    Called from this package's ``__init__``, so a deployment's ``wsgi.py`` registers
    the whole extension with one import — placed **before** ``little_sister.app``,
    because the aspect has to be declared before anything reads it — the next line
    included — and the slot filled before the first render.

    A missing or broken ``config/jira.yaml`` costs the deployment its button and
    nothing else: the failure is logged, the provider then declines every line, and
    the dashboard is untouched. A monitor that will not start because an issue
    tracker is misconfigured would have the priorities backwards.
    """
    global _config
    register_aspect(ASPECT)
    _config = _load()
    package = __package__ or "little_sister_jira"
    if _config is None or _config.action("reason") is not None:
        slots.register("reason.actions", package,
                       "reason_actions.html", reason_action)
    if _config is not None and _config.action("node") is not None:
        slots.register("node.actions", package,
                       "node_actions.html", node_action)


def reason_action(*, node: object, reason: str, index: int,
                  surface: str) -> Mapping[str, object] | None:
    """The ``reason.actions`` context provider: what the chip needs, or ``None``.

    Placement policy lives here rather than in little-sister's template, which is the
    point of the seam. Three rules:

    * **Leaves only.** A container's reason is a roll-up sentence; the check that
      actually failed is the one an issue should name.
    * **Not on a healthy node.** An ``OK`` leaf may still carry a reason ("all four
      replicas up"), and offering to raise a ticket for it is noise.
    * **Not on prose, when the node chip is offered.** Reasons that are not
      *members* are one condition written across several lines — a failure message
      and its stack trace — so there is one thing to file and the node chip is what
      files it. A chip per line there is the same ticket offered three times, one of
      them about a traceback. This is the mirror of :func:`node_action`'s
      single-member rule, and like it, it only ever steps aside in favor of a chip
      that is actually configured: a deployment offering *only* per-line chips keeps
      them on prose too.
    """
    action = _offered("reason", node)
    if action is None or _config is None:
        return None
    if getattr(node, "children", ()):
        return None
    if not getattr(node, "members", False) and _config.action("node") is not None:
        return None
    del index, surface  # the chip is the same on both surfaces, for every line
    return _chip(action, node, reason)


def node_action(*, node: object, surface: str,
                place: str | None = None) -> Mapping[str, object] | None:
    """The ``node.actions`` context provider: one ticket for the whole node.

    Its rules differ from the per-line chip's in two ways. **Containers are not
    declined**: this slot renders in a node's head, and a card at depth 1 *is* a
    container. It also acts as an **all-members shortcut** when several addressable
    members exist, but declines a single member when that member already has the
    reason action — the mirror of the prose rule in :func:`reason_action`, and for
    the same reason: two chips, one ticket. "Already has" is literal, and the
    ``children`` test is what makes it so: a **container** declaring one member gets
    no per-line chip either (that rule is above), so standing down for it would
    leave the node with no chip at all — two rules deferring to each other into
    silence. A node with **no reasons** is declined as
    well; it has nothing to put in a ticket, and a draft summarized as
    ``/platform/ci:`` with nothing after it is worse than no chip.

    **Not on a node that is healthy itself** (:func:`_healthy_itself`), whatever
    beneath it fails. Such a node is red only by roll-up, and its reason lines are
    its own reading — a coverage sentence, *12 functions in scope* — so a draft
    from them would file the failure under a line that says nothing about it. The
    chip stands where the failure is: on the node beneath that counts it.

    **Its icon, where it stands in a head.** With ``icon:`` in the block the chip
    is a square in the head's row (``jira_icon``), its label the tooltip; ``place``
    is how the library says the chip stands in one, and a library that hands over
    no ``place`` — one older than 0.3.21, which draws no square — gets the label
    chip, as does a place this package does not know.
    """
    action = _offered("node", node)
    if action is None or _config is None or _healthy_itself(node):
        return None
    lines = _reason_lines(node)
    if not lines:
        return None
    if (getattr(node, "members", False) and len(lines) == 1
            and not getattr(node, "children", ())
            and _config.action("reason") is not None):
        return None
    del surface  # the chip is the same on the wall and on a node's own page
    square = action.icon if action.icon and place in HEAD_ROWS else ""
    return {**_chip(action, node, lines[0], body="\n".join(lines)),
            "jira_icon": square}


def _offered(placement: str, node: object) -> ActionConfig | None:
    """The chip configured for ``placement``, unless this node should not carry one.

    The one rule both placements share: **not on a healthy node**. Everything else is
    the provider's own.
    """
    if _config is None:
        return None
    code = getattr(node, "code", None)
    if code is not None and getattr(code, "name", "") == "OK":
        return None
    return _config.action(placement)


def _healthy_itself(node: object) -> bool:
    """Whether the node's **own** status is OK, whatever beneath it fails.

    Read from ``own_counted`` — what the node counts for itself in what it rolls up
    to: its own status, or its own reading degraded where that reading went stale —
    rather than from ``code``, which on a branch is the worst of the node and of
    everything beneath it. A node that does not carry the attribute, a library older
    than 0.3.20's, is not known to be healthy, so its chip stays where it was.
    """
    own = getattr(node, "own_counted", None)
    return own is not None and str(getattr(own, "name", "")) == "OK"


def _chip(action: ActionConfig, node: object, reason: str,
          body: str | None = None) -> dict[str, object]:
    """What a template needs for one chip."""
    assert _config is not None                      # guarded by :func:`_offered`
    return {
        "jira_url": issue_url(_config, node, reason, action=action, body=body),
        "jira_label": action.label,
        "jira_title": f"Create a Jira issue for {getattr(node, 'path', '')}",
    }


def _reason_lines(node: object) -> list[str]:
    """The node's reason lines as plain text.

    Read from ``reason`` — the tuple of texts every surface already shows — rather
    than from ``reasons``, whose entries carry slugs this module has no use for
    (little-sister ADR-0036 decision 11).
    """
    return [str(line) for line in getattr(node, "reason", ()) if str(line).strip()]


def issue_url(config: JiraConfig, node: object, reason: str, *,
              action: ActionConfig | None = None,
              body: str | None = None) -> str:
    """The pre-filled ``CreateIssueDetails`` URL for one node, within its budget.

    ``reason`` is what the summary is built from — the line for a per-line chip, the
    node's first line for a node chip. ``body`` overrides the description, which is
    how a node chip carries **every** line where a per-line chip carries one.

    The ids and the summary are never cut: an issue in the wrong project, or one
    whose board line is half a sentence, is worse than a truncated body. What gives
    is the description and the configured fields — and only when the whole URL would
    otherwise exceed ``url_limit``, so an ordinary draft is byte-for-byte what it
    always was.
    """
    chip = action if action is not None else ActionConfig(config.label, config.fields)
    summary = _summary(config, node, reason)
    fixed: dict[str, str] = {
        "pid": config.project_id,
        "issuetype": config.issue_type_id,
        "summary": summary,
    }
    trailer = _trailer(node)
    text = body if body is not None else reason
    variable: dict[str, str] = {"description": _join(text, trailer)}
    for key, template in chip.fields.items():
        variable[key] = expand(template, node, reason, summary)

    head = f"{config.base_url}{CREATE_PATH}?"
    room = (max(1, config.url_limit) - len(head) - len(urlencode(fixed))
            - sum(len(f"&{quote_plus(key)}=") for key in variable))
    for key, share in _shares({k: len(quote_plus(v)) for k, v in variable.items()},
                              room).items():
        if len(quote_plus(variable[key])) <= share:
            continue
        # `description` is a Jira field id like any other, so a deployment may set
        # it in `fields:` — and then the body is *theirs*, template and all.
        # Rebuilding it from the node here would discard that template, and only on
        # the long drafts this clamp exists for: it would work in every test an
        # operator ran and vanish exactly when it mattered.
        ours = key == "description" and "description" not in chip.fields
        variable[key] = (_clamp(text, trailer, share) if ours
                         else _cut(variable[key], share))
    return f"{head}{urlencode({**fixed, **variable})}"


def _shares(wanted: Mapping[str, int], room: int) -> dict[str, int]:
    """Divide ``room`` among the parts, giving the small ones all they asked for.

    Smallest first, each capped at an equal share of what is still unspent, and what
    a part does not take is redistributed to the ones behind it. So a short custom
    field is never cut to make space for a traceback that is going to be cut anyway,
    and two long fields cut each other equally rather than by whichever came first
    out of a mapping.
    """
    shares: dict[str, int] = {}
    left = room
    for index, key in enumerate(sorted(wanted, key=lambda name: wanted[name])):
        fair = left // (len(wanted) - index)
        shares[key] = max(0, min(wanted[key], fair))
        left -= shares[key]
    return shares


def _cut(text: str, budget: int) -> str:
    """``text`` cut to ``budget`` with a trailing ellipsis — or nothing.

    The marker costs nine characters once encoded, so a share too small to pay for
    it buys an empty value rather than a URL nine characters over the limit it was
    built to respect. An empty parameter is honest: Jira renders the field blank.
    """
    marker = "…"
    room = budget - len(quote_plus(marker))
    return f"{_fit(text, room)}{marker}" if room > 0 else ""


def _fit(text: str, budget: int) -> str:
    """The longest prefix of ``text`` that survives encoding within ``budget``.

    By bisection over the *characters*, measuring the *encoded* length: the two are
    not proportional — a newline costs three, an ellipsis nine — so a character
    budget derived by division would be wrong in whichever direction hurts.
    """
    if budget <= 0:
        return ""
    if len(quote_plus(text)) <= budget:
        return text
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if len(quote_plus(text[:middle])) <= budget:
            low = middle
        else:
            high = middle - 1
    return text[:low]


def expand(template: str, node: object, reason: str, summary: str) -> str:
    """Substitute the node/reason tokens in a configured field template.

    Plain replacement, deliberately not :meth:`str.format`: a reason is captured
    output and routinely contains a brace, which ``format`` would read as a field
    name and raise on. An unknown token is left standing rather than erased, so a
    typo shows up in the draft instead of vanishing from it.
    """
    for token, value in _tokens(node, reason, summary).items():
        template = template.replace("{" + token + "}", value)
    return template


def _tokens(node: object, reason: str, summary: str) -> dict[str, str]:
    """What a field template may refer to.

    ``reasons`` is every line, newline-separated — the node chip's body, and the same
    name little-sister's own ``config/actions.yaml`` uses for it, so an operator who
    knows one file knows this one. (That file spells the status ``{code}`` where this
    one says ``{status}``; the two are separate vocabularies and neither is worth
    breaking to align.)
    """
    return {
        "path": str(getattr(node, "path", "")),
        "name": str(getattr(node, "name", "")),
        "status": _status_name(node),
        "observed": str(getattr(node, "timestamp", "") or "not yet observed"),
        "reason": reason,
        "reasons": "\n".join(_reason_lines(node)),
        "summary": summary,
        "url": _node_url(node),
    }


def _summary(config: JiraConfig, node: object, reason: str) -> str:
    """``<node path>: <the reason, on one line>``, clamped to the summary limit.

    The path goes first because a Jira board shows the head of a summary and cuts the
    tail: *which* thing broke is what has to survive the cut.
    """
    head = f"{getattr(node, 'path', '')}: {_one_line(reason)}".strip()
    limit = max(1, config.summary_limit)
    return head if len(head) <= limit else head[:limit - 1] + "…"


def _one_line(reason: str) -> str:
    """A Markdown reason flattened to one line: no fences, no newlines, no runs."""
    return " ".join(reason.replace("`", "").split())


def _trailer(node: object) -> str:
    """Where the reason came from: the node, its status, when, and a link back.

    Assembled apart from the reason because it is what survives a cut. It is short,
    bounded, and it carries the ``dashboard:`` line — which is precisely what makes
    truncating the text above it safe rather than lossy: the full reason is one
    click away, and cutting the tail off the *whole* body would have thrown away the
    link that says so.
    """
    lines = ["---",
             f"node: {getattr(node, 'path', '')}",
             f"status: {_status_name(node).lower()}",
             f"observed: {getattr(node, 'timestamp', None) or 'not yet observed'}"]
    url = _node_url(node)
    if url:
        lines.append(f"dashboard: {url}")
    return "\n".join(lines)


def _join(reason: str, trailer: str) -> str:
    """The body as it reads: the reason, a blank line, then where it came from."""
    return f"{reason}\n\n{trailer}"


def _clamp(reason: str, trailer: str, budget: int) -> str:
    """The body, with the *reason* cut so the whole thing encodes within ``budget``.

    The trailer is kept whole and the marker is paid for before the text is measured,
    so a clamped body always still says that it was clamped and where the rest is.

    When the budget cannot hold even that — a limit small enough to be a
    configuration mistake — **the limit still wins** and the trailer is cut like
    anything else. Keeping a link back inside a URL the server will refuse would be
    keeping the one useful part of a draft nobody can open.
    """
    # What the body costs before a single character of the reason: the marker, the
    # newline that separates it from the text above, and the trailer. Counted on the
    # *encoded* string, and counted here rather than approximated — the newline alone
    # is three characters once encoded, which is exactly the kind of rounding that
    # puts a URL three characters over a limit it was built to respect.
    overhead = len(quote_plus(_join(f"\n{TRUNCATED}", trailer)))
    if overhead >= budget:
        # Nothing of the reason fits. Give up the marker before the trailer, never
        # the other way round: cutting `_join(TRUNCATED, trailer)` from the tail
        # would delete the ``dashboard:`` line while keeping the sentence that
        # promises it — a body that is one broken reference and nothing else.
        for candidate in (_join(TRUNCATED, trailer), trailer):
            if len(quote_plus(candidate)) <= budget:
                return candidate
        return _fit(trailer, budget)
    kept = _fit(reason, budget - overhead).rstrip()
    return _join(f"{kept}\n{TRUNCATED}" if kept else TRUNCATED, trailer)


def _node_url(node: object) -> str:
    """The absolute dashboard URL of this node, so the issue links back.

    Absolute deliberately: the link is read in Jira, where a relative path means
    nothing. Empty outside a request context (a unit test), which the callers treat
    as "no link" rather than as an error.
    """
    if not has_request_context():
        return ""
    branch = str(getattr(node, "path", "")).lstrip("/")
    return url_for("status", branch=branch, _external=True)


def _status_name(node: object) -> str:
    code = getattr(node, "code", None)
    return str(getattr(code, "name", "") or "UNDEFINED")


def _load() -> JiraConfig | None:
    """Parse ``config/jira.yaml`` from the first root that declares it.

    Every failure *of this file* is logged and answered with ``None`` — no chip,
    everything else untouched. A failure of the **configuration tree** is not ours
    to answer: little-sister raises for a root that does not resolve, and for the
    aspect stored in a shape it does not have (a `jira/` directory, or two files
    claiming the name), and those are fatal by design. Swallowing them here would
    turn a refusal to start into a dashboard that runs with the buttons quietly
    missing — and for the shape errors nothing else reports them at all.
    """
    path = sole_aspect_file(ASPECT)
    if path is None:
        logger.info("jira: no %s.yaml in the configuration — no issue button",
                    ASPECT)
        return None
    try:
        body = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        logger.warning("jira: %s could not be read: %s — no issue button",
                       path, error)
        return None
    if not isinstance(body, Mapping):
        logger.warning("jira: %s must be a mapping, got %s — no issue button",
                       path, type(body).__name__)
        return None
    unknown = sorted(set(body) - _KEYS)
    if unknown:
        logger.warning("jira: %s has unknown key(s): %s (known: %s)",
                       path, ", ".join(unknown), ", ".join(sorted(_KEYS)))
    try:
        return _parse(body, str(path))
    except CheckError as error:
        logger.warning("jira: %s — no issue button", error)
        return None


def _parse(body: Mapping[str, object], where: str) -> JiraConfig:
    """One document as a :class:`JiraConfig`; raises on anything unusable."""
    label = values.text(body, "label", default="Jira", where=where)
    fields = _parse_fields(body, where)
    return JiraConfig(
        base_url=_base_url(values.text(body, "base_url", required=True,
                                       where=where), where),
        project_id=values.text(body, "project_id", required=True, where=where),
        issue_type_id=values.text(body, "issue_type_id", required=True,
                                  where=where),
        label=label,
        summary_limit=values.number(body, "summary_limit",
                                    default=DEFAULT_SUMMARY_LIMIT, where=where),
        url_limit=values.number(body, "url_limit", default=DEFAULT_URL_LIMIT,
                                where=where),
        fields=fields,
        actions=_parse_actions(body, where, label, fields),
    )


def _base_url(raw: str, where: str) -> str:
    """``base_url`` as an http(s) URL with a host, or a refusal naming what it got.

    Everything else in this module answers a bad configuration with "log it, decline
    the chip, touch nothing else". Without this check the one value that decides
    *where the browser goes* was the exception: an unedited placeholder out of the
    example produced a rendered, clickable chip pointing at a host that cannot
    resolve — a dead button that looks exactly like a working one.

    A query or a fragment is refused too, and not only on principle: the form's own
    parameters are appended after a ``?``, so a ``base_url`` carrying one would build
    a URL with two. That is checked against the **raw string**, because a bare
    trailing ``?`` or ``#`` parses to an empty query and an empty fragment — falsy,
    invisible to a check on the parsed parts, and enough to turn the whole chip URL
    into a fragment the browser never sends.

    What comes back is the **parsed** URL rather than the string that was read:
    :func:`~urllib.parse.urlsplit` strips ASCII tabs and newlines, so a value
    carrying one would otherwise validate clean and then land in an ``href``.
    """
    if "?" in raw or "#" in raw:
        raise CheckError(
            f"{where}: 'base_url' may not carry a query or a fragment — got "
            f"{raw!r}. The create-issue form's own parameters go after the '?', "
            f"and a URL with two of them reaches nothing.")
    parts = urlsplit(raw)
    if (parts.scheme not in ("http", "https") or not parts.netloc
            or "@" in parts.netloc or _NOT_IN_HOST.search(parts.netloc)):
        raise CheckError(
            f"{where}: 'base_url' must be an http(s) URL naming your Jira host — "
            f"got {raw!r}. A placeholder copied out of an example is not a host; "
            f"put your own site there.")
    try:
        parts.port                       # noqa: B018  raises on a port out of range
    except ValueError as error:
        raise CheckError(f"{where}: 'base_url' has an unusable port — {error}"
                         ) from error
    return parts.geturl().rstrip("/")


def _parse_fields(body: Mapping[str, object], where: str) -> dict[str, str]:
    """A ``fields:`` mapping of Jira field id -> template, or an empty one."""
    raw = body.get("fields")
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise CheckError(f"{where}: 'fields' must be a mapping, got "
                         f"{type(raw).__name__}")
    return {str(key): values.text(raw, str(key), required=True,
                                  where=f"{where}.fields")
            for key in raw}


def _parse_actions(body: Mapping[str, object], where: str, label: str,
                   fields: Mapping[str, str]) -> dict[str, ActionConfig]:
    """The ``actions:`` block — which chips a deployment offers.

    **Absent means the reason chip only**, on the file's defaults: that is what the
    deployment this grew up in had before the node chip existed, so an upgrade adds
    no button nobody asked for. A placement named with an empty mapping takes the
    defaults too; one that names ``label`` or ``fields`` overrides that key alone.

    An unknown placement name warns and is skipped rather than raising — a typo there
    costs one chip, and a monitor that will not start because of it would have the
    priorities backwards.

    ``icon`` is the node placement's alone, and inherits nothing: an icon this
    package does not draw (:data:`OWN_ICONS`) is warned about and leaves the label
    chip, for the same reason — the button still works, wearing its label.
    """
    raw = body.get("actions")
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise CheckError(f"{where}: 'actions' must be a mapping of placement name "
                         f"to settings, got {type(raw).__name__}")
    parsed: dict[str, ActionConfig] = {}
    for key in raw:
        name = str(key)
        if name not in PLACEMENTS:
            logger.warning("jira: %s names the unknown placement %r — known: %s",
                           where, name, ", ".join(sorted(PLACEMENTS)))
            continue
        settings = raw[key]
        if settings is None:
            settings = {}
        if not isinstance(settings, Mapping):
            raise CheckError(f"{where}.actions.{name}: must be a mapping, got "
                             f"{type(settings).__name__}")
        known = _ACTION_KEYS[name]
        unknown = sorted(set(map(str, settings)) - known)
        if unknown:
            logger.warning("jira: %s.actions.%s has unknown key(s): %s (known: %s)",
                           where, name, ", ".join(unknown), ", ".join(sorted(known)))
        icon = (values.text(settings, "icon", where=f"{where}.actions.{name}").strip()
                if "icon" in known else "")
        if icon and icon not in OWN_ICONS:
            logger.warning("jira: %s.actions.%s names the icon %r, which this package "
                           "does not draw (it draws: %s) — the chip keeps its label",
                           where, name, icon, ", ".join(sorted(OWN_ICONS)))
            icon = ""
        parsed[name] = ActionConfig(
            label=values.text(settings, "label", default=label,
                              where=f"{where}.actions.{name}"),
            fields=(_parse_fields(settings, f"{where}.actions.{name}")
                    if "fields" in settings else fields),
            icon=icon,
        )
    return parsed


def use_config(config: JiraConfig | None) -> None:
    """Install a configuration directly, bypassing the file — for tests."""
    global _config
    _config = config
