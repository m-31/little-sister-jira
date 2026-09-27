# ADR-0001 — Raise a Jira issue from a reason line

- **Status:** Accepted
- **Date:** 2026-08-01 (adopted into this repository 2026-08-08)
- **Related:** little-sister **ADR-0034** (template slots — the seam this fills),
  little-sister **ADR-0035** (registered configuration aspects — where
  `config/jira.yaml` gets to live), little-sister **ADR-0036** (addressable
  members — what decides which placement a ticket belongs to), little-sister
  **ADR-0018** (why this package builds no HTML), little-sister **ADR-0023**
  (secret references — deliberately unused here, see §4)

> This record was written in the private deployment the chip grew up in and moved
> here with the code. Its numbering is this repository's; every reference to one of
> little-sister's is written out as **little-sister ADR-00NN**, because the two
> numbering spaces overlap.

## Context

When a check goes red the operator's next move is nearly always the same: open Jira,
start an issue, and retype what the dashboard is already showing — which node, what it
said, when. The manual version of that was a shell script: it URL-encoded a summary, a
description and a custom field into Jira's `CreateIssueDetails!init.jspa` form and
handed it to `open`. It proved the mechanism and nothing else — the values were
hard-coded, so using it meant editing the script.

What was missing was not the URL. It was a place on the page to put a button. That gap
is closed on the library side by little-sister's **template slots** (its ADR-0034):
the library declares named places and the context it hands over there, and a dependent
package fills one with a template of its own plus a context provider. This ADR records
what this package does with them.

## Decision

Fill little-sister's `reason.actions` slot with a **Jira chip**: a link, per reason
line of a failing leaf, to Jira's own create-issue form, pre-filled from that node and
that reason.

1. **A link, not an API call.** The chip is an `<a href>` to
   `<base_url>/secure/CreateIssueDetails!init.jspa?…`, opened in a new tab. Nothing is
   created until a human presses Create in Jira's own form; the deployment stores no
   Jira credential, holds no token, and the browser's existing Jira session decides who
   is filing. The monitoring page also never navigates away from what it is watching.
2. **No `reporter` is pinned.** The script this replaced pinned one account id.
   Carried over, that would have filed everyone's tickets under one name; left out,
   Jira defaults to whoever is signed in, which is the right answer and needs no
   configuration. A deployment that wants one anyway can set it as a `fields:` entry,
   and owns that choice — including what it means on a shared dashboard.
3. **This module computes values; the template renders HTML.** `jira.py` returns a URL,
   a label and a title; `templates/reason_actions.html` is the only markup, and it is
   rendered by little-sister's Jinja with autoescaping on. The reason text is check-
   authored and often assembled from captured output (little-sister ADR-0018) — folding
   it into an issue draft must not be the one path where that escaping is ours to
   remember.
4. **The ids live in `config/jira.yaml`**, a configuration aspect this package
   registers (little-sister ADR-0035): `base_url`, `project_id`, `issue_type_id`, the
   chip `label`, a `summary_limit`, and a `fields` map of extra Jira field ids to
   templates over `{path}` `{name}` `{status}` `{observed}` `{reason}` `{summary}`
   `{url}`, and a `{reasons}` token that expands to every line of the node,
   newline-separated. The names are this package's own: little-sister's
   `config/actions.yaml` spells the status `{code}` where this file says `{status}`,
   and `examples/jira.yaml` says so beside the token, since the two files are separate
   vocabularies an operator meets one at a time. A custom field *number* is a fact
   about one Jira project, so it is an operator edit and a restart, never a code
   change. Nothing in the file is a secret, so no secret reference (little-sister
   ADR-0023) is involved; deleting the file simply removes the chip.

   The file also names **which placements this deployment offers**, in an `actions:`
   block (`reason`, `node`), each inheriting the file's `label` and `fields` and free
   to override either; the ids, the summary limit and `url_limit` stay at the top
   level, because they are properties of the *project* rather than of a placement.
   **An absent block means the reason chip only**, so installing the node chip stays a
   decision rather than a button that arrives with an upgrade.
5. **Placement policy is ours.** The library offers the slot on every reason of every
   node; the provider declines a **container** (its reason is a roll-up sentence — the
   check that actually failed is what an issue should name) and declines an **OK**
   node (a healthy leaf may still carry a reason, and offering to file a ticket for it
   is noise). Everything else — every non-OK leaf, on the dashboard and on the leaf
   detail page, for every logged-in viewer — gets the chip. The kiosk gets none, which
   the library already decides.

   **The chip has a second placement.** little-sister's `node.actions` slot (its
   ADR-0034, second slot) takes an action whose subject is the whole node, and that is
   the right one where a check's reasons are **prose** — a failure message and its
   stack trace are one condition and want one ticket, not two buttons. Where a check
   declares its findings as **members** (little-sister ADR-0036) the per-line chip
   stays right.

   Its decline rules differ in one deliberate way: the node chip **does not decline
   containers**, because the slot renders in the card head and a card at depth 1 *is* a
   container. It declines a node with **no reasons** instead — a container with no
   reading of its own has nothing to put in a ticket, and a draft summarized as
   `/platform/ci:` with nothing after it is worse than no chip. Both chips still
   decline a healthy node.

   **Each placement steps aside where the other is the right subject.** When both are
   enabled, the node chip is also the aggregate **Jira all** shortcut for several
   addressable members. It declines a node with exactly one member because that
   member's Jira chip already represents the same action; showing both is duplication,
   not another useful choice. The counterpart holds for prose: a leaf with a stack
   trace and both placements configured would otherwise draw a chip on every line *and*
   one on the node — the very thing this decision's reasoning argues against. Both
   rules only ever stand down in favor of a chip that is actually offered, and both sit
   in this package's provider rather than in little-sister's slot core: a package that
   offers only `node.actions` must not lose its sole action merely because the node has
   one member. They belong in the code and not in the configuration, because whether a
   node's reasons are members is a property of the **check**, and no deployment can say
   "per line for these nodes, per node for those" in one file. Prose and node-only
   configurations retain their node action, and the no-reasons, healthy-node and
   container rules remain.
6. **Summary is `<node path>: <reason on one line>`, path first**, clamped to
   `summary_limit` with an ellipsis: a Jira board shows the head of a summary and cuts
   the tail, so *which* thing broke has to survive the cut. The **description** carries
   the reason **whole** — a fenced traceback is exactly what the person picking the
   issue up needs — plus node path, status, observation time and an **absolute** link
   back to the node's page, because that link is read inside Jira.

   **The node draft differs from the per-line one:** its **summary** is the node's
   *first* reason line (same flattening and clamp) and its **description carries every
   line**, because the ticket is about the whole condition.

   **A draft is bounded by its transport, not by its display.** Clamping the summary is
   right about the display budget and silent about the transport one. Everything
   travels in a `GET` query string where percent-encoding roughly triples a traceback,
   so forty findings under one band (the case the node chip exists for) reach around
   nine thousand characters and a `{reasons}` field duplicates the body on top. Past
   the server's request-line limit the operator gets a **414 instead of a form**, which
   is worse than no chip because the chip still looks like it works. So `url_limit`
   bounds the whole URL, default 6000 against a common 8 KB ceiling. What gives is the
   description and the configured fields, in fair shares so a short field is not cut to
   make room for a traceback that is going to be cut anyway; the ids and the summary
   never give. Cutting is cheap here precisely because the description already carries
   a **link back to the node** — so a clamped draft says it was clamped and where the
   rest is. The one exception is a limit too small to hold even that: the limit still
   wins, because a URL the server refuses is not a draft anybody reads.
7. **Field templates substitute, they do not `format`.** A reason is captured output
   and routinely contains a brace, which `str.format` would read as a field name and
   raise on. Unknown tokens are left standing rather than erased, so a typo shows up in
   the draft instead of vanishing from it.
8. **A broken configuration costs the button and nothing else.** A missing, unreadable
   or invalid `config/jira.yaml` is logged once at startup; the provider then declines
   every line and the dashboard is untouched. A monitor that refuses to start because
   an issue tracker is misconfigured has the priorities backwards.

   What costs the button is a broken *file*. A configuration **tree** that will not
   resolve — a missing root, or the aspect stored in a shape it does not have — stays
   fatal, because that is little-sister's refusal to start and not an extension's to
   soften.

   **`base_url` is validated**, because "log it, decline the chip, touch nothing else"
   covers every value except the one deciding *where the browser goes*: a placeholder
   copied out of the example rendered a clickable chip pointing at a host that does not
   exist. It is an http(s) URL naming a host, with no query or fragment — the last of
   those is not principle but arithmetic, since the form's own parameters are appended
   after a `?`.
9. **Registration is one import.** `import little_sister_jira`, before
   `little_sister.app`, declares the aspect, reads the file and fills the slots the
   file asks for. Which extensions a deployment installs stays a decision readable
   where it is taken — it is now a line in the dependency list and a line in
   `wsgi.py`, rather than a call into the deployment's own code. `/system` then lists
   the package that answers for the aspect.

## Consequences

- Filing the issue for a red check is one click from the dashboard, with the node, the
  reason, the time and a link back already in the draft.
- The chip's reach is the reach of the URL format: `CreateIssueDetails!init.jspa` is a
  Jira Server/Cloud convenience endpoint, not a documented API. If Atlassian retires
  it, the fix is this module and `config/jira.yaml`, and the dashboard degrades to
  having no chip.
- Configuration is read **once, at startup**. An operator editing `config/jira.yaml`
  restarts to see the change — the same contract as the rest of `config/`.
- This package consumes two of little-sister's seams (template slots, configuration
  aspects) and none of its check-authoring surface beyond the typed value readers.
  Each is part of the library's version contract, so the declared floor is what keeps
  them stable and the declared API epoch is what refuses an upgrade past them.
- The `jira` aspect name is claimed in every deployment that installs this package.
  That is the cost of an aspect owned by a package rather than by a deployment, and it
  is why the name is the package's own.

## Alternatives considered

- **Create the issue ourselves over the Jira REST API**, from a POST on our own
  endpoint. One fewer click and a chance to attach the reason as a real field, but it
  needs a stored Jira credential in a monitoring deployment that currently holds none
  for it, files everything as the token's owner (the `reporter` problem again), and
  turns a read-only dashboard into something that writes to a ticket system. Rejected —
  possibly worth revisiting once little-sister has write actions of its own.
- **Keep the shell script and make it read the node from an argument.** Cheapest, and
  it stays a terminal thing: the operator is on the dashboard, and copying a node path
  into a shell is the friction this removes.
- **A generic "open URL with these tokens" filler** rather than a Jira-specific package.
  Attractive, and it is really the declarative action list little-sister considered and
  deferred (its ADR-0034, Alternatives). Building it here would mean building it in the
  wrong repository; if it is wanted, it belongs in the library where every deployment
  gets it.
- **Put the chip only on the leaf detail page.** Fewer buttons on the dashboard, but
  the moment worth capturing is the one where the operator is looking at the red card.
  The library's hover-reveal keeps the grid calm, which is what that concern was
  really about.
