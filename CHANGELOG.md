# Changelog

All notable changes to little-sister-jira, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/). These notes are for the
deployments that install this package, not a work log.

Treat **a new or renamed configuration key, a retired token, or a change to which
slots are filled as a breaking change** and say so at the top: a deployment's
`config/jira.yaml` and the drafts its operators expect are built on those.

## [Unreleased]

## [0.1.4] - 2026-10-18

A release to install beside little-sister 0.3.21, which draws a node's actions in every
head: the node chip now stands only where the failure is, and can be a square there.
Upgrading asks no edit and moves no floor — it still installs beside little-sister
0.3.18. What is new is optional: an `icon` key in the `actions.node` block, which a
`jira.yaml` may carry only from this release on, and a command that writes the file
from a Jira Cloud project's address.

### Added

- **Breaking for a configuration: a new key, `icon`, in the `actions.node` block.**
  `icon: jira` makes the node chip, in a head's row, little-sister's own icon square
  with this package's own glyph in it, a plus on an issue card; the label becomes the
  square's tooltip and its accessible name, and the draft does not change. It takes
  little-sister 0.3.21 or newer, which draws a node's actions in every head and says
  which; on an older library the chip wears its label, so no floor moves. `jira` is
  the one name the package draws — any other is named at startup and keeps the label
  — and a block without the key keeps the label too, so an upgrade changes no head
  nobody asked to change. The per-line chip takes no `icon`. `examples/jira.yaml`
  carries `icon: jira`, and the `configure` command writes it. An older release of
  this package names the key as unknown at startup and draws the label chip, so a
  deployment writes the key with the release that reads it (ADR-0001 decision 4).
- **`python -m little_sister_jira.configure` writes `config/jira.yaml` from a Jira
  Cloud project's address** (ADR-0002). Run it from the deployment's root with the
  address of one of the project's pages — a board, its backlog, its issue list or an
  issue. It names the addresses to open in a browser signed in to Jira and the file to
  save each answer as, and builds the file from what Jira answered: the ids, each field
  the issue type's create form requires written by its kind, and your account id as a
  commented `reporter:`. It holds no credential and calls nothing. Where the
  configuration has a `jira.yaml` already, or names its roots in
  `LITTLE_SISTER_CONFIG_DIR`, it prints the file instead of writing one. Jira Cloud
  only.

### Changed

- **ADR-0001 says where the library lists this package.** little-sister's System page
  is two views now, and the package that answers for the `jira` aspect is listed on
  the one called *Installed*, `/system/installed` (little-sister ADR-0100); decision 9
  says so. Prose only: no code moved.

### Fixed

- **The node chip stands where the failure is.** It was offered on a branch that is
  healthy itself whenever anything beneath it failed, and its draft was written from
  the branch's own line — a check's coverage sentence, *12 functions in scope*,
  became the summary of a ticket about one function's error. little-sister 0.3.21
  shows a node's actions in every head rather than on a hover, so the chip would have
  stood in every head on the way to the failure. It is declined now on a node whose
  **own** status is OK, whatever its children's; the node that failed keeps its chip,
  and the per-line chip is unchanged (ADR-0001 decision 5). Nothing to edit: no key,
  token or slot moved. On a library before 0.3.20, whose node does not say what it
  counts for itself, the chip stays where it was.

## [0.1.3] - 2026-09-27

### Changed

- **Breaking for an install: this package declares check API epoch 3.** little-sister
  replaced a check's `run()` with `measure()` and `grade()`, and `CheckResult` lost
  `subject` and `record` (little-sister ADR-0086). This package implements neither
  method and reads neither field, and nothing it does changes — no configuration key
  moves, no slot changes, no chip moves and no draft is worded differently. What
  changes is which library it may be installed beside: an older one is refused at
  startup naming both numbers, so a deployment moves its two pins together.

### Requires

- **`little-sister >= 0.3.18`**, up from 0.3.13: the first release that speaks check
  API epoch 3. The template slots, registered configuration aspects and typed value
  readers this package writes against are unchanged; what moved is the epoch, and a
  floor naming an older library would let a resolver install the one `require_api()`
  refuses at startup. Still a **floor, never a pin**.

## [0.1.2] - 2026-08-29

### Fixed

- **This package's own instructions were wrong about what a late registration
  costs.** The docstring a deployment reads to place `import little_sister_jira` in
  its `wsgi.py` said the line had to come before the first configuration scan "or the
  library has already warned that `config/jira.yaml` is not a known aspect" — which
  reads as advice with a log line attached, and is the kind of ordering rule somebody
  relaxes. The real consequence is harder: little-sister resolves an aspect by looking
  its name up in its own table, so an undeclared `jira` is not an *unclaimed* file but
  an **unreadable** one. `_load()` gets a `KeyError` and deliberately does not catch
  it — a failure of the configuration *tree* is not this package's to answer — so an
  import placed too late takes the deployment's boot with it rather than costing it a
  chip. `register()`'s docstring carried the same sentence and now carries this one.

  **Nothing executable moved.** The ordering requirement is exactly what it has always
  been and the shipped behavior is unchanged; what was wrong was the reason given for
  it, which is the half a reader acts on when deciding where the import may go.

## [0.1.1] - 2026-08-23

### Changed

- **Breaking for an install: this package declares check API epoch 2.** little-sister
  took the whole `subnodes:` block into its own hands and three names left its
  promised surface (little-sister ADR-0025). Nothing in this package used them, and nothing it
  does changes — no configuration key moves, no slot changes, no draft is worded
  differently. What changes is which library it may be installed beside: the epoch
  versions little-sister's *whole* surface, so an extension that registers no check
  type still declares it, and an older library is refused at startup naming both
  numbers.

### Fixed

- **`little_sister_jira.__version__` reports the installed version again.** It was a
  literal, frozen at `0.1.0` — right for the first release and wrong from this one on,
  a second source of a fact `pyproject.toml` already owns. It is read from the
  installed distribution's metadata now, the way little-sister reads its own, so it
  cannot disagree with the package that carries it; in a source tree with no install
  it reads `0+unknown` rather than a number that would be wrong.

### Requires

- **`little-sister >= 0.3.13`**, up from 0.3.11: that is the release whose
  surface this package's epoch names. The reason the floor already carried
  still holds — the template slots, registered configuration aspects and typed
  value readers this package writes against — and what the epoch adds is the
  upgrade a floor cannot see: an older library is refused at startup naming
  both numbers. Still a **floor, never a pin**.

## [0.1.0] - 2026-08-09

### Added

- **First release: the Jira issue chip**, extracted from the private deployment it
  grew up in — same drafts, same configuration file, and the placement rules below,
  two of which are new with the move. It is a **surface extension**: it registers no
  check type and measures nothing.
- Two placements, chosen by the `actions:` block. **`reason`** puts one chip beside
  each reason line of a failing leaf, which is the right place where a check
  declares its findings as addressable members. **`node`** puts one chip on the
  whole node — in the card head and beside the status on the leaf page — which is
  the right place where the reasons are prose, and which doubles as the *file them
  all* shortcut when several members share one condition. **Omitting the block
  leaves only the per-reason chip**, so installing the node chip is a decision.
- The chip is a **plain link** to Jira's own pre-filled create-issue form, opened in
  a new tab. This package stores no Jira credential and holds no token; the
  browser's Jira session decides who is filing, and nothing exists until a human
  presses Create.
- The **`jira` configuration aspect** — `config/jira.yaml`, layered and
  shape-checked by little-sister like one of its own. `base_url`, `project_id` and
  `issue_type_id` are required; `label`, `summary_limit` and a `fields` map of Jira
  field ids to templates are optional, and a placement may override `label` and
  `fields` — the ids and the limits are properties of the project and its server,
  not of a placement.
  A field template interpolates `{path}` `{name}` `{status}` `{observed}`
  `{reason}` `{reasons}` `{summary}` `{url}` by plain substitution, so a brace in
  captured output cannot raise and an unknown token is left standing.
- **`url_limit` bounds the whole chip URL**, default 6000. Everything a draft
  carries travels in a `GET` query string, where percent-encoding roughly triples a
  traceback: forty findings under one band — the case the node chip exists for —
  reach around nine thousand characters, and past a server's request-line limit the
  operator gets a **414 from Jira instead of a form**, which is worse than no chip
  because the chip still looks like it works. Only the description and the
  configured fields are cut, never the ids or the summary, and a cut body says so
  and keeps its link back to the node — the link is the last thing given up. A
  `description` set in `fields:` is yours: it is cut, never rebuilt. The common ceiling is 8 KB (Tomcat's
  `maxHttpHeaderSize`, nginx's `large_client_header_buffers`) but the real one is
  your Jira's: confirm it and set the key.
- **`base_url` is validated** — an http(s) URL naming a host, with no query or
  fragment. A placeholder copied out of the example is refused at startup, where it
  used to render a clickable chip pointing at a host that cannot resolve.
- **Where both placements are offered, each steps aside where the other is the right
  subject.** The node chip already stood down for a node with exactly one member;
  now the per-line chips stand down on **prose**, where a failure message and its
  stack trace are one condition and a chip per line would offer to file a traceback.
  A deployment that offers only one placement keeps it in every case.
- **A missing or broken `config/jira.yaml` costs the button and nothing else** —
  the failure is logged, the chips decline every line, and the dashboard is
  untouched. A configuration *tree* that will not resolve is a different thing and
  stays fatal: little-sister refuses to start, which is its decision to make.

### Requires

- `little-sister >= 0.3.11` — the floor is 0.3.11, not the 0.3.0 that first
  promised the template slots, registered configuration aspects and typed value
  readers this package writes against: 0.3.0 was tagged but never uploaded, so it
  names no version a resolver can fetch, and it is 0.3.11 that lowered the
  library's own Python floor to the one below.
  A **floor, never a pin**. The package declares check API epoch **1**; a
  library that has moved past that surface refuses at startup rather than failing as
  an import error from inside this package.
- **Python 3.11 or newer** — the library's floor, not a higher one of this
  package's own: a plugin that asked for more would mean somebody installs
  little-sister and then cannot install the package they came for. The claim is
  checked rather than declared — the type check runs against 3.11 on every commit
  and the whole suite against a real 3.11 on every release.
