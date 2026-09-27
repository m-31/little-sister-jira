# little-sister-jira

Raise a **Jira** issue from what
[little-sister](https://github.com/m-31/little-sister) is already showing: a chip
beside a failing reason line, or one for the whole node, linking to Jira's own
pre-filled create-issue form.

It is a **surface extension**, not a check type — it measures nothing and adds no
`type:` name. What it adds is a button in two places little-sister declares, drawn
only where an issue would make sense: not on a healthy node, not on a container's
roll-up sentence, and not twice for the same finding.

Nothing is created behind the operator's back. The chip is a plain link opened in a
new tab; Jira renders its own form, the browser's Jira session decides who is
filing, and nothing exists until a human presses **Create**. This package stores no
Jira credential and holds no token.

## The contract

- **Requires** `little-sister >= 0.3.18` — a floor, never a pin.
- **Runs on** Python **3.11 or newer** — the library's floor, not a higher
  one of its own.
- **Registers** the `jira` **configuration aspect** (`config/jira.yaml`) and fills
  two template slots, `reason.actions` and `node.actions`. It registers **no check
  type**.

## Install

```toml
# your deployment's pyproject.toml — both come from the index
[project]
# Pin them. A deployment names exact versions so an upgrade is a deliberate edit
# rather than drift; a plugin is the one that declares a floor, because two plugins
# that each pinned could not be installed together.
dependencies = ["little-sister==0.3.18", "little-sister-jira==0.1.3"]
```

```python
# wsgi.py — registrations first, the app last. The order is load-bearing in both
# directions: the aspect must be declared before little-sister first scans the
# configuration directory, and the slots filled before the first render.
# `isort: off` keeps an import sorter from quietly reversing that.
# isort: off
import little_sister_jira               # noqa: F401  aspect + both chips
from little_sister.app import app
# isort: on

__all__ = ["app"]                       # without it, lint calls the app import unused
```

## Configure

Copy [`examples/jira.yaml`](examples/jira.yaml) into your configuration root as
`config/jira.yaml` and replace the ids with your own:

```yaml
base_url: https://<your-site>.atlassian.net
project_id: "10000"
issue_type_id: "10002"
```

Those three are required; everything else has a default. The ids come from Jira's
own API — `/rest/api/3/project/<KEY>`, `/rest/api/3/issuetype/project?projectId=…`
and `/rest/api/3/field`.

`base_url` is **checked**: an http(s) URL naming a host, with no query or fragment.
The example's value is deliberately not one, so copying the file unedited is refused
at startup rather than rendering a chip that points at a host which cannot resolve —
a dead button looks exactly like a working one.

| Config | Decides |
|---|---|
| `label` | the chip's text. Default `Jira` |
| `summary_limit` | where the summary is cut with an ellipsis. Default 200; Jira's own limit is 255 |
| `url_limit` | how long the whole chip URL may get. Default 6000 — see **Long drafts** below |
| `fields` | extra Jira fields by id, each a template over the tokens below — this is how a project's required custom field gets filled |
| `actions` | which chips are offered: `reason`, `node`, or both. Each inherits `label` and `fields` and may override either. **Absent means the per-reason chip only** |

A field template may interpolate `{path}` `{name}` `{status}` `{observed}`
`{reason}` `{reasons}` `{summary}` `{url}`. Substitution is plain replacement, not
`str.format`: a reason is captured output and routinely contains a brace. An
unknown token is left standing, so a typo shows up in the draft rather than
vanishing from it.

Nothing in that file is a credential, so no secret reference is involved. Delete it
and the chips simply stop appearing — a **missing or broken `config/jira.yaml`
costs the button and nothing else**, because a monitor that will not start because
an issue tracker is misconfigured has the priorities backwards. A configuration
*directory* that will not resolve is little-sister's own refusal to start, and this
package does not soften it.

## What a draft looks like

The **summary** is `<node path>: <the reason on one line>`, path first, because a
Jira board shows the head of a summary and cuts the tail. The **description**
carries the reason **whole** — a fenced traceback is what the person picking the
issue up needs — plus the node path, its status, when it was last observed, and an
absolute link back to its page, since that link is read inside Jira.

The two placements differ in subject. The `reason` chip is about **one line**: its
summary and description are that line. The `node` chip is about the **whole
condition**: its summary is the node's first line and its description carries every
line.

Where both are offered, **each steps aside where the other is the right subject**.
Where a check declares its findings as addressable members, the node chip is the
*file them all* shortcut and stands down for a node with exactly one member, whose
own chip already says the same thing. Where the reasons are **prose** — a failure
message and its stack trace are one condition — the per-line chips stand down
instead, because there is one thing to file and a chip per line would offer to raise
a ticket about a traceback. Neither rule can cost you a button you cannot get back:
a deployment that offers only one placement keeps it in every case, and a container
declaring a single member keeps its node chip, because the per-line chip it would
have deferred to is never drawn on a container.

## Long drafts

Everything the chip carries travels in a `GET` query string, where percent-encoding
roughly triples a traceback. Forty findings under one critical band — exactly the
case the node chip exists for — reach around nine thousand characters, and a
`{reasons}` field template duplicates the body on top of that. Past the server's
request-line limit the operator gets a **414 from Jira instead of a form**, which is
worse than no chip because the chip still looks like it works.

So the whole URL is clamped to `url_limit` (default **6000**). What gives is the
description and the configured fields, in fair shares — a short field is not cut to
make room for a traceback that is going to be cut anyway. The project ids and the
summary are never cut. A clamped body says so and keeps its `dashboard:` link, which
is what makes cutting safe: the full text is one click away. The link is the *last*
thing given up, and it goes only when the budget cannot hold even it.

A `description` set in `fields:` is **yours**: it is cut like any other field, never
replaced by the stock body.

The default leaves roughly two kilobytes under the common 8 KB request-line default
(Tomcat's `maxHttpHeaderSize`, nginx's `large_client_header_buffers`) for the cookies
and headers a logged-in Jira session sends. **The real ceiling belongs to your Jira**
and nothing here can discover it, so confirm it and set `url_limit` accordingly.

## Develop

little-sister is declared as a **floor** — the release that promised the surface
this package writes against — and a release resolves it **from the index**, like any
other dependency: a released tree carries no `[tool.uv.sources]` table, and its
`uv.lock` names the index. Working against a library that is not on the index yet
takes a redirect to the checkout beside this one:

```toml
# pyproject.toml — while the library is unreleased, and never in a release
[tool.uv.sources]
little-sister = { path = "../little-sister", editable = true }
```

The redirect leaves a second trace by itself — the next `uv run`, and the pre-commit
gate is one, rewrites `uv.lock` to name the directory — and the two go together:
while the library is unreleased both may be committed, and neither may reach a
release. uv reads the sources table of a dependency it resolves from a path or a
checkout, so a released one would be imposed on every deployment that installs this
package that way; an install from the index is unaffected. The comment on the sources
table in `pyproject.toml` says what the window costs.

```bash
uv sync
uv run ruff check
uv run shellcheck $(git ls-files -- '*.sh' 'hooks/pre-commit')
uv run mypy
uv run mypy --python-version 3.11   # against the floor, not the interpreter you have
uv run pytest -q
# The same gate runs before every commit once the hook is enabled:
git config core.hooksPath hooks
```

The tests are fixture-based; nothing in this repository calls Jira. Run them with
`uv run pytest`, not a bare `pytest`: one test probes a subprocess with no
`PYTHONPATH`, so it only finds this package where a deployment does — installed.

Two seams are worth knowing when changing it. The chips are **package data** —
Jinja files inside `src/little_sister_jira/templates/` — and a source checkout finds
them whether or not a wheel would, so a change there is worth verifying against a
built wheel rather than the checkout. And the chip needs **no
Content-Security-Policy contribution**: it is a link, not a fetch, and no directive
governs where an `<a href>` may point. A future chip that *called* Jira would need
one.

## License

MIT — see [LICENSE](LICENSE).
