"""A ``jira.yaml`` from a Jira Cloud project's address (ADR-0002).

    python -m little_sister_jira.configure https://<site>/jira/software/projects/KEY/boards/1

Installing this package asks a deployment for ids it can only find in Jira: the
project's id, an issue type's id, and the number of every field the project's create
form **requires**. The address a browser shows already names two things — the site,
which is ``base_url``, and the project's key — from whichever of the project's pages it
is: a board, its backlog, its issue list, an issue. The rest only Jira answers, and only
to somebody signed in.

**So this command signs in to nothing.** It holds no credential — no token, no prompt
for one — and the deployment stores none, which is where ADR-0001 stands. It names the
addresses to open in a browser that is signed in to Jira and the file to save each
answer as, goes on when Enter is pressed, and builds the file from what Jira said. That
is two rounds, because the second address needs an answer to the first: the account and
the project with its issue types (``/rest/api/3/myself``, ``/rest/api/3/project/KEY``),
then, once an issue type is chosen, that type's create form
(``/rest/api/3/issue/createmeta/KEY/issuetypes/ID``) — the one answer that says which
fields are required. The saved answers stay, so a run again — another issue type — asks
only for what it has not got.

**A required field is written by its kind.** A text field gets a line in ``fields:``,
its name a comment above it and ``"{name}: {reason}"`` its template; a field with a list
of values gets a commented line naming each value's id and label, one to uncomment; any
other kind, which a link cannot fill — a user, a date — a comment naming the field and
saying so. What the chip already sends (the project, the issue type, the summary, the
description) and a field Jira gives a default are left out. The account that answered
is written **only as a comment**, ``# reporter: "<account id>"``, beside the reason
ADR-0001 decision 2 gives for pinning none.

**Jira Cloud only.** The command judges by Jira's first answer, never by the host's
name, which a Cloud site may choose: a ``myself.json`` without an ``accountId`` is not
Cloud's, and the command says so and stops rather than write half a file.

It prints the file, or writes ``config/jira.yaml`` where the configuration has no
``jira`` aspect yet; it never replaces one. What it says to the person goes to stderr
and a printed file to stdout, so ``> somewhere.yaml`` keeps only the file.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import urlsplit

import yaml
from little_sister.checks import CheckError
from little_sister.config_dir import sole_aspect_file

from little_sister_jira import jira

#: How the command is run, which is also what the file it writes says made it.
COMMAND = "python -m little_sister_jira.configure"

#: Where an address names its project: a board, a backlog, the issue list, the
#: project's summary — ``…/projects/KEY/…``, company-managed (``/c/``) or not.
_PROJECT_IN_PATH = re.compile(r"/projects/([A-Za-z][A-Za-z0-9_]*)(?=/|$)")
#: …or an issue, ``/browse/KEY-123``, or the project's own ``/browse/KEY``.
_BROWSE_IN_PATH = re.compile(r"/browse/([A-Za-z][A-Za-z0-9_]*)(?:-\d+)?(?=/|$)")

#: What the chip sends on every draft, so a required one is never written again.
_SENT = frozenset({"project", "issuetype", "summary", "description"})

#: The field the account id would go in — written as a comment, never as a value.
_REPORTER = "reporter"

#: The most fields one create-form answer holds: the endpoint's ``maxResults``
#: ceiling. The address asks for all of them.
_PAGE = 200

#: A field id that YAML reads as a plain key; anything else is quoted.
_PLAIN_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

#: How a field nothing in a draft can fill is named in its comment, by the kind
#: Jira's answer gives it (``schema.type``, and ``schema.items`` for a list).
_KIND_WORDS = {"user": "a user", "date": "a date", "datetime": "a date and time",
               "number": "a number", "team": "a team", "attachment": "attachments",
               "issuelinks": "links to other issues", "timetracking": "time tracking"}
_ITEM_WORDS = {"user": "users", "string": "words, such as labels",
               "attachment": "attachments", "issuelinks": "links to other issues"}


class Refusal(Exception):
    """What stops the command, as one sentence for whoever is running it."""


class _Again(Exception):
    """A saved answer that is not the one asked for — saved again, it may be."""


@dataclass(frozen=True)
class Address:
    """What an address gives without asking Jira: the site and the project's key."""
    base_url: str
    key: str


@dataclass(frozen=True)
class Step:
    """One address to open in the browser, and the file its answer is saved as."""
    url: str
    file: str


def parse_address(raw: str) -> Address:
    """The site and the project key in the address of one of the project's pages.

    ``base_url`` is the scheme and the host — what the chip prefixes Jira's create
    form with, and what ``jira.yaml`` checks the same way. The key comes from the
    path: ``/projects/KEY/`` on a board, a backlog, an issue list or a summary, and
    ``/browse/KEY-123`` on an issue.
    """
    text = raw.strip()
    parts = urlsplit(text)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise Refusal(f"{raw!r} is not the address of a Jira page — copy it from the "
                      f"browser's address bar, https:// and all")
    try:
        base_url = jira._base_url(f"{parts.scheme}://{parts.netloc}", "the address")
    except CheckError as error:
        raise Refusal(f"{text} names no site this package can link to ({error})"
                      ) from error
    match = _PROJECT_IN_PATH.search(parts.path) or _BROWSE_IN_PATH.search(parts.path)
    if match is None:
        raise Refusal(f"{text} names no project — give the address of one of its "
                      f"pages: a board, its backlog, its issue list, or an issue "
                      f"(…/browse/KEY-123)")
    return Address(base_url=base_url, key=match.group(1).upper())


def main(argv: Sequence[str] | None = None, *, stdin: TextIO | None = None,
         stdout: TextIO | None = None, stderr: TextIO | None = None) -> int:
    """Run the command; 0 when the file was written or printed, 1 when refused."""
    args = _arguments().parse_args(argv)
    run = _Run(stdin or sys.stdin, stdout or sys.stdout, stderr or sys.stderr)
    try:
        address = parse_address(args.address)
        folder = Path(args.answers).expanduser() if args.answers else _downloads()
        folder.mkdir(parents=True, exist_ok=True)
        session = _Session(address, folder, run)
        myself, project = session.first_round()
        issue_type = session.choose(project, args.issue_type)
        fields = session.second_round(issue_type)
        text = render(address, myself=myself, project=project,
                      issue_type=issue_type, fields=fields)
        _loads(text)
        run.say(_summary(required(fields)))
        return run.deliver(text, print_only=args.print)
    except Refusal as refusal:
        run.say(f"configure: {refusal}")
        return 1


def _arguments() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=COMMAND,
        description="Write a jira.yaml for this deployment from a Jira Cloud project's "
                    "answers, which a browser signed in to Jira saves as files.")
    parser.add_argument("address", help="the address of one of the project's pages, "
                        "as the browser shows it: a board, its backlog, its issue "
                        "list, or an issue")
    parser.add_argument("--answers", metavar="DIR", help="where the browser saves "
                        "Jira's answers (default: your Downloads folder, else the "
                        "current directory)")
    parser.add_argument("--issue-type", metavar="ID|NAME", help="the issue type a "
                        "draft is, by its id or its name (default: asked)")
    parser.add_argument("--print", action="store_true", help="print the file rather "
                        "than write config/jira.yaml")
    return parser


def _downloads() -> Path:
    """Where a browser saves by default, so the person names a file and no folder."""
    try:
        downloads = Path.home() / "Downloads"
    except RuntimeError:                  # no home directory this process can find
        return Path.cwd()
    return downloads if downloads.is_dir() else Path.cwd()


class _Run:
    """The command's three streams, and what it does with the file at the end."""

    def __init__(self, stdin: TextIO, stdout: TextIO, stderr: TextIO) -> None:
        self.stdin, self.stdout, self.stderr = stdin, stdout, stderr

    def say(self, text: str = "") -> None:
        print(text, file=self.stderr, flush=True)

    def ask(self, prompt: str) -> str:
        """One line from the person; the end of the input stops the command."""
        self.stderr.write(prompt)
        self.stderr.flush()
        line = self.stdin.readline()
        if not line:
            self.stderr.write("\n")
            raise Refusal("stopped before it was answered — run it again; the "
                          "answers already saved are kept")
        return line.strip()

    def deliver(self, text: str, *, print_only: bool) -> int:
        """Write ``config/jira.yaml`` where the configuration has no ``jira`` aspect,
        or print the file — never over one that is there."""
        existing = sole_aspect_file(jira.ASPECT)
        target = Path("config") / f"{jira.ASPECT}.yaml"
        why = ""
        if print_only:
            pass
        elif existing is not None:
            why = f"{existing} is there already, and is not replaced"
        elif os.environ.get("LITTLE_SISTER_CONFIG_DIR", "").strip():
            why = ("LITTLE_SISTER_CONFIG_DIR names this deployment's configuration "
                   "roots — put the file in the one it belongs to")
        # With no roots named, `config/` is the one root, and it is there: importing
        # this package resolved it, and a root that does not resolve stops the import.
        if print_only or why:
            self.stdout.write(text)
            self.stdout.flush()
            if why:
                self.say(f"Printed rather than written: {why}.")
            return 0
        target.write_text(text, encoding="utf-8")
        self.say(f"Wrote {target}. Restart the deployment to read it.")
        return 0


class _Session:
    """The rounds of one run: what to ask the browser for, and what came back."""

    def __init__(self, address: Address, folder: Path, run: _Run) -> None:
        self.address, self.folder, self.run = address, folder, run
        self.host = urlsplit(address.base_url).netloc.lower()

    def first_round(self) -> tuple[dict[str, Any], dict[str, Any]]:
        """The account and the project — the two answers that need nothing chosen."""
        base, key = self.address.base_url, self.address.key
        myself, project = self._round(
            "The account you sign in with, and the project",
            [(Step(f"{base}/rest/api/3/myself", "myself.json"), self._myself),
             (Step(f"{base}/rest/api/3/project/{key}", "project.json"),
              self._project)])
        if not isinstance(project.get("issueTypes"), list):
            # Jira documents the issue types as part of every project answer; where
            # one arrives without them, the project's own list is one more address.
            [types] = self._round("The project's issue types", [(
                Step(f"{base}/rest/api/3/issuetype/project"
                     f"?projectId={project['id']}", f"issuetypes-{key}.json"),
                self._issue_types)])
            project = {**project, "issueTypes": types}
        return myself, project

    def choose(self, project: Mapping[str, Any], wanted: str | None
               ) -> dict[str, Any]:
        """The issue type a draft is: named, the only one, or asked for.

        A sub-task is never offered — it needs a parent issue, and a link from a
        dashboard has none to give.
        """
        types = [dict(item) for item in project["issueTypes"]
                 if isinstance(item, Mapping) and item.get("id") is not None
                 and not item.get("subtask") and item.get("hierarchyLevel") != -1]
        names = ", ".join(f"{_one_line(item.get('name'))} ({item['id']})"
                          for item in types)
        if not types:
            raise Refusal(f"{self.address.key} has no issue type a ticket can be "
                          f"created as — only sub-tasks, which need a parent")
        if wanted:
            for item in types:
                if (wanted == str(item["id"]) or
                        _one_line(item.get("name")).casefold() == wanted.casefold()):
                    return item
            raise Refusal(f"{self.address.key} has no issue type {wanted!r}: its "
                          f"types are {names}")
        if len(types) == 1:
            self.run.say(f"Its one issue type is {names}.")
            return types[0]
        self.run.say()
        self.run.say("Which issue type should a chip's draft be?")
        for number, item in enumerate(types, 1):
            self.run.say(f"  {number}. {_one_line(item.get('name'))}  "
                         f"(id {item['id']})")
        while True:
            answer = self.run.ask(f"Its number, 1 to {len(types)}: ")
            if answer.isdigit() and 1 <= int(answer) <= len(types):
                return types[int(answer) - 1]

    def second_round(self, issue_type: Mapping[str, Any]) -> list[dict[str, Any]]:
        """The chosen type's create form: every field it has, which it requires."""
        base, key, type_id = self.address.base_url, self.address.key, issue_type["id"]
        [fields] = self._round(
            f"The create form of {_one_line(issue_type.get('name'))}",
            [(Step(f"{base}/rest/api/3/issue/createmeta/{key}/issuetypes/{type_id}"
                   f"?maxResults={_PAGE}", f"fields-{key}-{type_id}.json"),
              self._fields)])
        return list(fields)

    def _round(self, subject: str,
               steps: Sequence[tuple[Step, Callable[[Any, Step], Any]]]) -> list[Any]:
        """Every step's answer, asking the browser for those not saved yet.

        An answer already saved — by an earlier run — is used as it is, so a run
        again needs no browser. One that is not the answer asked for is named with
        what is wrong with it and asked for again; one that rules the run out, a site
        that is not Jira Cloud, stops it.
        """
        asked = False
        while True:
            answers: list[Any] = []
            missing: list[tuple[Step, str]] = []
            for step, read in steps:
                path = self.folder / step.file
                if not path.is_file():
                    missing.append((step, ""))
                    continue
                try:
                    answers.append(read(_saved(path), step))
                except _Again as again:
                    missing.append((step, str(again)))
            if not missing:
                if not asked:
                    self.run.say(f"Using {' and '.join(step.file for step, _ in steps)}"
                                 f", saved earlier in {self.folder}.")
                return answers
            self._name(subject, missing)
            self.run.ask("Press Enter once "
                         f"{'it is' if len(missing) == 1 else 'they are'} saved. ")
            asked = True

    def _name(self, subject: str, missing: Sequence[tuple[Step, str]]) -> None:
        """The addresses to open, and the file each answer is saved as."""
        self.run.say()
        self.run.say(f"{subject} — Jira answers that only to somebody signed in. "
                     f"Sign in to {self.address.base_url} in your browser, open each "
                     f"address below there, and save what it shows in {self.folder} "
                     f"under the name beside it.")
        for step, wrong in missing:
            self.run.say(f"  {step.url}")
            self.run.say(f"    → {step.file}" + (f"  ({wrong})" if wrong else ""))

    def _myself(self, body: Any, step: Step) -> dict[str, Any]:
        """The account that answered — and with it, whether this is Jira Cloud."""
        answer = self._from_this_site(body, step)
        if not answer.get("accountId"):
            raise Refusal(
                f"{self.address.base_url} is not Jira Cloud: its answer to "
                f"{step.url} carries no accountId. Only Jira Cloud is supported for "
                f"now — Data Center names its users and its addresses differently — "
                f"so nothing was written")
        return answer

    def _project(self, body: Any, step: Step) -> dict[str, Any]:
        answer = self._from_this_site(body, step)
        if answer.get("id") is None or not answer.get("key"):
            raise _Again(f"that is not Jira's answer to {step.url}")
        if str(answer["key"]) != self.address.key:
            raise _Again(f"that one is project {answer['key']}'s answer, not "
                         f"{self.address.key}'s")
        return answer

    def _issue_types(self, body: Any, step: Step) -> list[Any]:
        if not isinstance(body, list):
            raise _Again("that is not a list of issue types")
        return body

    def _fields(self, body: Any, step: Step) -> list[dict[str, Any]]:
        """The create form's fields — under ``fields``, as Jira Cloud documents the
        answer, or ``results``, which its schema names beside it."""
        if not isinstance(body, Mapping):
            raise _Again("that is not a create form's answer")
        entries = next((body[name] for name in ("fields", "results")
                        if isinstance(body.get(name), list)), None)
        if entries is None:
            raise _Again("that is not a create form's answer")
        total = body.get("total")
        if isinstance(total, int) and total > len(entries):
            # A required field may be among those it does not hold. Fewer than a page
            # is an address opened without its `maxResults`; a full page is a form
            # one answer cannot hold at all.
            if len(entries) < _PAGE:
                raise _Again(f"it holds {len(entries)} of the form's {total} fields — "
                             f"open the address as it is given, maxResults and all")
            raise Refusal(f"the create form has {total} fields and one answer holds "
                          f"{len(entries)}, so a required one may be missing — "
                          f"nothing was written")
        return [dict(entry) for entry in entries if isinstance(entry, Mapping)]

    def _from_this_site(self, body: Any, step: Step) -> dict[str, Any]:
        if not isinstance(body, Mapping):
            raise _Again(f"that is not Jira's answer to {step.url}")
        own = urlsplit(str(body.get("self", ""))).netloc.lower()
        if own and own != self.host:
            raise _Again(f"that one is {own}'s answer, not {self.host}'s")
        return dict(body)


def _saved(path: Path) -> Any:
    """One saved answer, parsed — or what is wrong with it, to save it again."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as error:
        raise _Again(f"it could not be read: {error}") from error
    try:
        body = json.loads(text)
    except ValueError as error:
        raise _Again("it is not Jira's answer but a page — a browser not signed in "
                     "to Jira is shown its login; sign in and save it again"
                     ) from error
    if isinstance(body, Mapping) and body.get("errorMessages"):
        said = "; ".join(_one_line(message) for message in body["errorMessages"])
        raise _Again(f"Jira answered with an error: {said}")
    return body


def render(address: Address, *, myself: Mapping[str, Any],
           project: Mapping[str, Any], issue_type: Mapping[str, Any],
           fields: Sequence[Mapping[str, Any]]) -> str:
    """The ``jira.yaml`` these answers make, as text — YAML written by hand, because
    its comments are half of what it says."""
    name = _one_line(project.get("name")) or address.key
    lines = [
        f"# The `jira` aspect for {name} ({address.key}) on {address.base_url},",
        f"# written by `{COMMAND}` from Jira's own answers. The",
        "# package's README describes every key; edit it here, and restart.",
        "",
        f"base_url: {_quoted(address.base_url)}",
        f"project_id: {_quoted(project['id'])}  # {name}",
        f"issue_type_id: {_quoted(issue_type['id'])}  "
        f"# {_one_line(issue_type.get('name'))}",
        "",
        "fields:",
        *_reporter(myself),
    ]
    for key, field, kind in required(fields):
        lines.extend(["", *_field(key, field, kind)])
    lines.extend([
        "",
        "# Both chips, on the fields above: one per reason line of a failing leaf, and",
        "# one for the whole node — in a head's row a square with this package's own",
        "# glyph, its label the tooltip. Without `node:` only the per-line chip is",
        "# offered; without `icon:` the node chip wears its label.",
        "actions:",
        "  reason: {}",
        "  node:",
        "    label: Jira all",
        "    icon: jira",
        "",
    ])
    return "\n".join(lines)


def _reporter(myself: Mapping[str, Any]) -> list[str]:
    """The account that answered, as a line to uncomment — and the reason it is one
    (ADR-0001 decision 2)."""
    return [
        "  # Jira files a ticket as whoever is signed in to the browser that opens the",
        "  # draft, and a pinned reporter files everyone's tickets under one name. On",
        "  # an instance only you use, pin yourself; on a shared one, leave this be.",
        f"  # {_REPORTER}: {_quoted(myself['accountId'])}",
    ]


def required(fields: Sequence[Mapping[str, Any]]
             ) -> list[tuple[str, Mapping[str, Any], str]]:
    """The fields a draft has to say something about, each with its kind: ``text``,
    ``list`` or ``other``.

    A field the create form does not require is left out, and so is one Jira gives a
    default, what the chip sends on every draft and the reporter, whose line is the
    commented account. A field with values to choose from is a ``list`` whatever its
    type — a select, a priority, a component — and one whose type is a string is
    ``text``; what is left has a kind nothing in a draft can fill.
    """
    found: list[tuple[str, Mapping[str, Any], str]] = []
    for field in fields:
        key = str(field.get("key") or field.get("fieldId") or "")
        if (not key or not field.get("required") or field.get("hasDefaultValue")
                or key in _SENT or key == _REPORTER):
            continue
        kind = ("list" if _values(field) else
                "text" if _schema(field).get("type") == "string" else "other")
        found.append((key, field, kind))
    return found


def _field(key: str, field: Mapping[str, Any], kind: str) -> list[str]:
    """One required field, written by its kind."""
    name = _one_line(field.get("name")) or key
    if kind == "list":
        return [f"  # {name}: required, and one of a list — uncomment the value every",
                "  # draft should carry.",
                *(f"  # {_key(key)}: {_quoted(value['id'])}  "
                  f"# {_one_line(value.get('value') or value.get('name'))}"
                  for value in _values(field))]
    if kind == "text":
        return [f"  # {name}: required",
                f"  {_key(key)}: {_quoted('{name}: {reason}')}"]
    return [f"  # {name} ({key}): required, and {_kind_words(_schema(field))} —",
            "  # nothing a draft carries can fill it, so Jira's form asks for it",
            "  # before the ticket is created."]


def _schema(field: Mapping[str, Any]) -> Mapping[str, Any]:
    schema = field.get("schema")
    return schema if isinstance(schema, Mapping) else {}


def _values(field: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The values a field may take, as its create form offers them — a disabled
    option is one nobody may choose any more, and is not offered."""
    offered = field.get("allowedValues")
    return [value for value in offered if isinstance(value, Mapping)
            and value.get("id") is not None and not value.get("disabled")
            ] if isinstance(offered, list) else []


def _kind_words(schema: Mapping[str, Any]) -> str:
    kind = str(schema.get("type") or "")
    if kind == "array":
        items = str(schema.get("items") or "")
        return f"a list of {_ITEM_WORDS.get(items, items + 's' if items else 'values')}"
    return _KIND_WORDS.get(kind, f"of the kind Jira calls {kind or 'none'}")


def _summary(found: Sequence[tuple[str, Mapping[str, Any], str]]) -> str:
    """What the create form asked of a draft, and what the file does about it."""
    if not found:
        return ("The create form requires nothing that a draft does not carry "
                "already, or that Jira does not fill in itself.")
    counts = {kind: sum(1 for _key, _field, of in found if of == kind)
              for kind in ("text", "list", "other")}
    said = [f"{counts['text']} written with a template" if counts["text"] else "",
            f"{counts['list']} with a value of a list to uncomment"
            if counts["list"] else "",
            f"{counts['other']} left to Jira's form" if counts["other"] else ""]
    return (f"The create form requires {len(found)} more field(s) of a draft: "
            f"{', '.join(part for part in said if part)}.")


def _loads(text: str) -> None:
    """Refuse to hand over a file the package would not load — which would be this
    module's mistake, never the person's."""
    try:
        jira._parse(yaml.safe_load(text), "the file this command built")
    except (yaml.YAMLError, CheckError) as error:
        raise Refusal(f"the file it built does not load ({error}) — a bug in this "
                      f"command; nothing was written") from error


def _quoted(value: object) -> str:
    """A YAML double-quoted scalar: JSON's string syntax, which YAML reads as is."""
    return json.dumps(str(value), ensure_ascii=False)


def _key(key: str) -> str:
    return key if _PLAIN_KEY.fullmatch(key) else _quoted(key)


def _one_line(text: object) -> str:
    """A name out of Jira's answer as one line, fit for a comment."""
    return " ".join(str(text if text is not None else "").split())


if __name__ == "__main__":
    raise SystemExit(main())
