# ADR-0002 — A configuration from a project's address

- **Status:** Accepted
- **Date:** 2026-10-17
- **Related:** ADR-0001 (the chip — its decision 1, no credential, and decision 2, no
  pinned reporter), little-sister **ADR-0035** (registered configuration aspects — the
  file this writes is one)

## Context

Installing this package asks a deployment for ids it can only find in Jira:
`project_id`, `issue_type_id`, and the number of every field its project's create form
**requires**. The last matter as much as the first two: a draft that leaves a required
field empty opens a form Jira will not submit until somebody fills it in by hand, every
time. The help was three endpoints of Jira's API, named in the README and the example,
and one of them, `/rest/api/3/field`, lists every field of the site without saying
which a project's create form requires — so a required field was found by reading the
form.

Every one of those answers is Jira's, and Jira gives them only to somebody signed in.
That is the whole difficulty. ADR-0001 rests on this package holding no credential — the
chip is a link, and the browser's own Jira session decides who is filing — and the
obvious tool, one that asks Jira, would need one.

## Decision

Ship a command, `python -m little_sister_jira.configure`, which a deployment runs once
from its root with the address of one of its Jira Cloud project's pages, and which
writes the `jira.yaml` that project's answers make. **This package now reads Jira's
answers; it still holds no credential.**

1. **What the address gives, the command takes from it.** The address as the browser
   shows it — a board, its backlog, the project's issue list, an issue — names the site,
   which is `base_url`, its scheme and host, and the project's key: `/projects/<KEY>/`
   on the first three, `/browse/<KEY>-<n>` on an issue. An address that names no
   project is refused, saying so.
2. **The browser's own session answers; the command signs in to nothing.** No token, no
   prompt for one, no request of its own: it names the addresses to open in a browser
   that is signed in to Jira, and builds the file from what Jira answered there, so the
   deployment stores nothing either. That is two rounds, because the second address
   needs an answer to the first: the account and the project with its issue types
   (`/rest/api/3/myself`, `/rest/api/3/project/<KEY>`), then, once an issue type is
   chosen, that type's create form
   (`/rest/api/3/issue/createmeta/<KEY>/issuetypes/<id>`) — the one answer that says
   which fields are required. Jira documents the issue types as part of every project's
   answer; where one arrives without them, the project's list
   (`/rest/api/3/issuetype/project?projectId=<id>`) is one more address in the first
   round. A sub-task type is not offered: it needs a parent, which a link from a
   dashboard does not have.
3. **The answers come back as files the browser saved**, in one interactive run: at
   each step the command names the address to open and the file to save its answer as
   — `myself.json`, `project.json`, then `fields-<KEY>-<id>.json` — in the browser's
   own download folder unless told otherwise, and goes on when Enter is pressed. A file
   is checked for being the answer asked for — JSON, not Jira's login page; this site's,
   by the link Jira puts in it; this project's — and named again with what is wrong with
   it when it is not. The files stay, so a run again — another issue type — asks only for
   what it has not got.
4. **A required field is written by its kind.** A text field gets a line in `fields:`,
   its name a comment above it and `"{name}: {reason}"` its template. A field with a
   list of values — a select's options, a component, a version — gets a commented line
   naming each value's id and label, one to uncomment; the id is what Jira's create-issue
   link takes for a select list, and an option Jira marks disabled is not offered. Any
   other kind — a user, a date, a number — gets a comment naming the field and saying
   that nothing a draft carries can fill it, so Jira's form asks for it. Left out: what
   the chip sends on every draft (the project, the issue type, the summary, the
   description) and every field Jira gives a default.
5. **The account id is read, and written only as a comment**: `# reporter: "<account
   id>"`, beside ADR-0001 decision 2's reason — Jira files a ticket as whoever is signed
   in, and a pinned reporter files everyone's tickets under one name. An instance only
   one person uses uncomments it; a shared one leaves it, the choice decision 2 already
   leaves a deployment, made one keystroke.
6. **It writes a file only where there is none.** Where the configuration has no
   `jira` aspect it writes `config/jira.yaml`; where it has one, or where
   `LITTLE_SISTER_CONFIG_DIR` names the roots and the right one is the deployment's to
   say, it prints the file instead and replaces nothing. What it built is parsed by
   this package's own reader before it is handed over. What it says to the person goes
   to stderr and a printed file to stdout.
7. **Jira Cloud only, for now.** The command judges by Jira's first answer, never by the
   host's name, which a Cloud site may choose: a `myself.json` without an `accountId` is
   not Cloud's, and the command says so and stops, writing nothing. Data Center —
   `/rest/api/2`, a user's key where Cloud has an account id, a board's address without
   the project's key — is work of its own, for when a deployment has one to verify
   against.

## Consequences

- Installing the package is one command and a few files saved from a browser, and a
  project's required fields are found by reading Jira's answer rather than its form.
- The command is published surface: its module name, its options and the file names it
  asks for are what a deployment's own instructions will be written against, so a rename
  is a breaking change like a renamed configuration key.
- It runs inside a deployment's root, because importing this package registers its
  aspect and reads the configuration, and a root that does not resolve is
  little-sister's refusal to start.
- What a saved answer says is trusted as far as it is checked and no further: a create
  form saved weeks ago is used as it is, and saving it again is how it is refreshed.
- Nothing calls Jira, in the command or in its tests: the answers the suite reads follow
  Jira Cloud's documentation of the four addresses, with placeholder ids.

## Alternatives considered

- **A step in little-sister's GUI.** It would need the library to take a plugin's setup
  page, and the server to sign in to Jira — the API call ADR-0001 rejected. It can come
  later as a face on this command.
- **An Atlassian API token**, one run and no copying. It is a credential, which this
  package would then hold for the length of a run and a deployment be tempted to keep,
  and some sites refuse personal tokens.
- **OAuth.** It needs an app registered with Atlassian, and a secret no public package
  can carry.
- **Pasting each answer at a prompt.** A create form's answer runs to tens of kilobytes,
  which is where a paste into a terminal breaks, and it says so only as a parse error;
  and nothing stays for a second run.
- **A template for every required field**, whatever its kind. Wrong for a list, whose
  value is an option's id that no template over the node's text produces.
- **The field's id alone, its value left to the deployment.** It leaves the commonest
  case — a required text field — to be written by hand, which is what the command is
  for.
