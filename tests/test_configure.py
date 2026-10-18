"""A ``jira.yaml`` from a project's address — the command, by its settled sentences.

Each test is one sentence of what ADR-0002 settles, with the values it is about. Jira's
answers are files here, which is also how the command receives them: a browser signed in
to Jira saves each one, and nothing in this package — nor in this suite — calls Jira.
The answers under ``answers/`` follow Jira Cloud's REST documentation of the four
addresses the command names — ``User``, ``Project``, ``IssueTypeDetails`` and
``PageOfCreateMetaIssueTypeWithField`` with its ``FieldCreateMetadata`` — and are
nobody's: a documentation host, placeholder ids, an account id out of Atlassian's own
examples.
"""
from __future__ import annotations

import io
import json
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from little_sister_jira import configure, jira

ANSWERS = Path(__file__).resolve().parent / "answers"
SITE = "https://tracker.example.org"
BOARD = f"{SITE}/jira/software/projects/EX/boards/1"
ACCOUNT = "5b10a2844c20165700ede21g"

#: The four addresses, as the command names them for the project EX on this site.
MYSELF = f"{SITE}/rest/api/3/myself"
PROJECT = f"{SITE}/rest/api/3/project/EX"
TASK_FORM = f"{SITE}/rest/api/3/issue/createmeta/EX/issuetypes/3?maxResults=200"
BUG_FORM = f"{SITE}/rest/api/3/issue/createmeta/EX/issuetypes/1?maxResults=200"


class Person:
    """The terminal's input, as the person at it: before each line they type, they
    save in the browser what the command asked for — ``(answer, saved as)`` pairs."""

    def __init__(self, folder: Path, *turns: tuple[tuple[tuple[str, str], ...], str]
                 ) -> None:
        self.folder, self.turns = folder, list(turns)

    def readline(self) -> str:
        if not self.turns:
            return ""                                   # the end of the input
        saves, line = self.turns.pop(0)
        for answer, saved_as in saves:
            shutil.copyfile(ANSWERS / answer, self.folder / saved_as)
        return f"{line}\n"


def _saved(folder: Path, *names: str) -> None:
    """Answers saved by an earlier run, under the names the command asks for."""
    for name in names:
        shutil.copyfile(ANSWERS / name, folder / name)


def _run(folder: Path, *args: str, person: Person | None = None,
         address: str = BOARD) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = configure.main([address, "--answers", str(folder), *args],
                          stdin=person or Person(folder), stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


@pytest.fixture
def folder(tmp_path):
    answers = tmp_path / "answers"
    answers.mkdir()
    return answers


@pytest.fixture
def written(folder):
    """The file the command makes from the saved answers of a Task, as text."""
    _saved(folder, "myself.json", "project.json", "fields-EX-3.json")
    code, out, err = _run(folder, "--issue-type", "Task")
    assert code == 0, err
    return out


# --- what the address gives without asking Jira ----------------------------------

@pytest.mark.parametrize("address", [
    f"{SITE}/jira/software/projects/EX/boards/1",              # a board
    f"{SITE}/jira/software/projects/EX/boards/1/backlog",      # its backlog
    f"{SITE}/jira/software/c/projects/EX/boards/12",           # company-managed
    f"{SITE}/jira/software/projects/EX/issues",                # the issue list
    f"{SITE}/jira/software/projects/EX/issues/EX-7?filter=all",
    f"{SITE}/jira/core/projects/EX/summary",
    f"{SITE}/jira/servicedesk/projects/EX/queues/custom/1",
    f"{SITE}/browse/EX-123",                                   # an issue
    f"{SITE}/browse/EX-123?focusedCommentId=10",
    f"{SITE}/browse/EX",                                       # the project itself
    f"{SITE}/projects/EX/issues/EX-1",                         # the older pages
    f"  {SITE}/browse/ex-9  ",                                 # pasted, lower case
])
def test_the_address_gives_the_site_and_the_projects_key(address):
    assert configure.parse_address(address) == configure.Address(SITE, "EX")


def test_the_site_keeps_its_port():
    parsed = configure.parse_address("https://tracker.example.org:8443/browse/EX-1")
    assert parsed.base_url == "https://tracker.example.org:8443"


@pytest.mark.parametrize("address", [
    f"{SITE}/jira/your-work",
    f"{SITE}/jira/dashboards/10000",
    f"{SITE}/jira/projects",
    f"{SITE}/issues/?jql=project%20%3D%20EX",
    f"{SITE}/",
])
def test_an_address_that_names_no_project_is_refused_saying_so(address):
    with pytest.raises(configure.Refusal, match="names no project"):
        configure.parse_address(address)


@pytest.mark.parametrize("address", ["tracker.example.org/browse/EX-1",
                                     "ftp://tracker.example.org/browse/EX-1",
                                     "https:///browse/EX-1"])
def test_an_address_that_is_not_a_page_is_refused(address):
    with pytest.raises(configure.Refusal, match="not the address of a Jira page"):
        configure.parse_address(address)


def test_a_site_the_chip_could_not_link_to_is_refused():
    # The same check `base_url` gets when the package reads it: a login in the host
    # part is not a site.
    with pytest.raises(configure.Refusal, match="names no site this package can link"):
        configure.parse_address("https://someone@tracker.example.org/browse/EX-1")


# --- it signs in to nothing: the browser's own session answers --------------------

def test_it_names_the_addresses_to_open_in_two_rounds_and_goes_on_at_enter(folder):
    # The account and the project first, which need nothing chosen; then the chosen
    # type's create form. Every line the person types is an Enter or a choice.
    person = Person(folder,
                    ((("myself.json", "myself.json"),
                      ("project.json", "project.json")), ""),
                    ((), "1"),                                  # Task, the first
                    ((("fields-EX-3.json", "fields-EX-3.json"),), ""))
    code, out, err = _run(folder, person=person)
    assert code == 0, err
    for address, file in ((MYSELF, "myself.json"), (PROJECT, "project.json"),
                          (TASK_FORM, "fields-EX-3.json")):
        assert f"  {address}\n    → {file}\n" in err
    assert err.index(MYSELF) < err.index(PROJECT) < err.index("1. Task")
    assert err.index("1. Task") < err.index(TASK_FORM)
    assert "2. Bug" in err
    assert "base_url:" in out


def test_it_opens_no_connection(written, folder, monkeypatch):
    # The whole run, with the network refused: there is nothing it could sign in to.
    def refuse(*args, **kwargs):
        raise AssertionError("the command opened a connection")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    code, out, err = _run(folder, "--issue-type", "3")
    assert code == 0, err
    assert out == written


# --- Jira's answers come back as files the browser saved --------------------------

def test_the_saved_answers_stay_and_a_run_again_asks_only_for_what_is_new(written,
                                                                         folder):
    # Another issue type: the account and the project are still there, so the one
    # address it names is the new type's create form.
    person = Person(folder, ((("fields-EX-1.json", "fields-EX-1.json"),), ""))
    code, out, err = _run(folder, "--issue-type", "Bug", person=person)
    assert code == 0, err
    assert MYSELF not in err and PROJECT not in err
    assert f"  {BUG_FORM}\n    → fields-EX-1.json\n" in err
    assert "Using myself.json and project.json, saved earlier in" in err
    assert 'issue_type_id: "1"  # Bug' in out


def test_a_page_saved_in_place_of_an_answer_is_asked_for_again(folder):
    # A browser that is not signed in is shown Jira's login, which saves fine.
    person = Person(folder,
                    ((("login-page.html", "myself.json"),
                      ("project.json", "project.json")), ""),
                    ((("myself.json", "myself.json"),), ""),
                    ((("fields-EX-3.json", "fields-EX-3.json"),), ""))
    code, _out, err = _run(folder, "--issue-type", "3", person=person)
    assert code == 0, err
    assert "→ myself.json  (it is not Jira's answer but a page" in err
    assert err.count(f"  {MYSELF}\n") == 2 and err.count(f"  {PROJECT}\n") == 1


def test_an_error_answer_says_what_jira_said_and_is_asked_for_again(folder):
    person = Person(folder,
                    ((("not-authenticated.json", "myself.json"),
                      ("project.json", "project.json")), ""),
                    ((("myself.json", "myself.json"),), ""),
                    ((("fields-EX-3.json", "fields-EX-3.json"),), ""))
    code, _out, err = _run(folder, "--issue-type", "3", person=person)
    assert code == 0, err
    assert ("(Jira answered with an error: You are not authenticated. "
            "Authentication required to perform this operation.)") in err


def test_another_projects_answer_is_asked_for_again(folder):
    other = json.loads((ANSWERS / "project.json").read_text(encoding="utf-8"))
    other["key"] = "OPS"
    (folder / "project.json").write_text(json.dumps(other), encoding="utf-8")
    _saved(folder, "myself.json")
    person = Person(folder, ((("project.json", "project.json"),), ""),
                    ((("fields-EX-3.json", "fields-EX-3.json"),), ""))
    code, _out, err = _run(folder, "--issue-type", "3", person=person)
    assert code == 0, err
    assert "→ project.json  (that one is project OPS's answer, not EX's)" in err
    assert MYSELF not in err                       # the account was fine as it was


def test_another_sites_answer_is_asked_for_again(folder):
    _saved(folder, "myself.json", "project.json", "fields-EX-3.json")
    code, _out, err = _run(folder, "--issue-type", "3",
                           address="https://other.example.org/browse/EX-1")
    assert code == 1                               # and the input ends there
    assert ("→ myself.json  (that one is tracker.example.org's answer, not "
            "other.example.org's)") in err


def test_the_end_of_the_input_stops_it_and_keeps_what_was_saved(folder):
    _saved(folder, "myself.json")
    code, out, err = _run(folder)
    assert code == 1 and out == ""
    assert "stopped before it was answered" in err
    assert (folder / "myself.json").is_file()


# --- Jira Cloud only ---------------------------------------------------------------

def test_a_site_whose_first_answer_has_no_account_id_is_refused_and_nothing_written(
        folder, tmp_path, monkeypatch):
    # Data Center answers /myself with a user's key and name, and no accountId. The
    # command judges by that answer and never by the host, which a Cloud site chooses.
    root = tmp_path / "deployment"
    (root / "config").mkdir(parents=True)
    monkeypatch.chdir(root)
    monkeypatch.delenv("LITTLE_SISTER_CONFIG_DIR")
    shutil.copyfile(ANSWERS / "myself-data-center.json", folder / "myself.json")
    _saved(folder, "project.json")
    code, out, err = _run(folder)
    assert code == 1 and out == ""
    assert f"{SITE} is not Jira Cloud" in err and "carries no accountId" in err
    assert "nothing was written" in err
    assert "createmeta" not in err                 # no second round
    assert list((root / "config").iterdir()) == []


def test_an_answer_that_holds_part_of_the_form_is_asked_for_again(folder):
    # The address asks for every field at once; opened without its query, Jira
    # answers with its first page alone, and a required field may be on the next.
    form = json.loads((ANSWERS / "fields-EX-3.json").read_text(encoding="utf-8"))
    form["total"], form["maxResults"] = 60, 50
    (folder / "fields-EX-3.json").write_text(json.dumps(form), encoding="utf-8")
    _saved(folder, "myself.json", "project.json")
    person = Person(folder, ((("fields-EX-3.json", "fields-EX-3.json"),), ""))
    code, _out, err = _run(folder, "--issue-type", "3", person=person)
    assert code == 0, err
    assert ("→ fields-EX-3.json  (it holds 13 of the form's 60 fields — open the "
            "address as it is given, maxResults and all)") in err


def test_a_form_one_answer_cannot_hold_is_refused(folder):
    form = json.loads((ANSWERS / "fields-EX-3.json").read_text(encoding="utf-8"))
    template = form["fields"][-1]
    form["fields"] = [{**template, "key": f"customfield_{20000 + number}",
                       "fieldId": f"customfield_{20000 + number}"}
                      for number in range(200)]
    form["total"] = 250
    (folder / "fields-EX-3.json").write_text(json.dumps(form), encoding="utf-8")
    _saved(folder, "myself.json", "project.json")
    code, out, err = _run(folder, "--issue-type", "3")
    assert code == 1 and out == ""
    assert "has 250 fields and one answer holds 200" in err
    assert "nothing was written" in err


# --- the issue type -----------------------------------------------------------------

def test_a_sub_task_is_never_offered(folder):
    _saved(folder, "myself.json", "project.json")
    code, _out, err = _run(folder, "--issue-type", "Sub-task")
    assert code == 1
    assert "EX has no issue type 'Sub-task': its types are Task (3), Bug (1)" in err


def test_the_one_issue_type_is_taken_without_asking(folder):
    project = json.loads((ANSWERS / "project.json").read_text(encoding="utf-8"))
    project["issueTypes"] = [kind for kind in project["issueTypes"]
                             if kind["name"] in ("Bug", "Sub-task")]
    (folder / "project.json").write_text(json.dumps(project), encoding="utf-8")
    _saved(folder, "myself.json", "fields-EX-1.json")
    code, out, err = _run(folder)                  # no --issue-type, and no input
    assert code == 0, err
    assert "Its one issue type is Bug (1)." in err
    assert 'issue_type_id: "1"  # Bug' in out


def test_an_answer_that_is_no_create_form_is_asked_for_again(folder):
    shutil.copyfile(ANSWERS / "project.json", folder / "fields-EX-3.json")
    _saved(folder, "myself.json", "project.json")
    person = Person(folder, ((("fields-EX-3.json", "fields-EX-3.json"),), ""))
    code, _out, err = _run(folder, "--issue-type", "3", person=person)
    assert code == 0, err
    assert "→ fields-EX-3.json  (that is not a create form's answer)" in err


def test_a_project_answer_without_its_issue_types_asks_for_the_projects_list(folder):
    project = json.loads((ANSWERS / "project.json").read_text(encoding="utf-8"))
    del project["issueTypes"]
    (folder / "project.json").write_text(json.dumps(project), encoding="utf-8")
    _saved(folder, "myself.json", "fields-EX-3.json")
    person = Person(folder, ((("issuetypes-EX.json", "issuetypes-EX.json"),), ""))
    code, out, err = _run(folder, "--issue-type", "Task", person=person)
    assert code == 0, err
    assert (f"  {SITE}/rest/api/3/issuetype/project?projectId=10000\n"
            f"    → issuetypes-EX.json\n") in err
    assert 'issue_type_id: "3"  # Task' in out


# --- a required field is written by its kind ---------------------------------------

def test_a_text_field_is_a_line_with_its_name_above_and_name_reason_its_template(
        written):
    assert ('  # Short description: required\n'
            '  customfield_10101: "{name}: {reason}"\n') in written


def test_a_list_field_is_a_commented_line_per_value_with_its_id_and_label(written):
    # A select's options and a component alike: one value to uncomment. An option
    # nobody may choose any more is not offered.
    assert ('  # Severity: required, and one of a list — uncomment the value every\n'
            '  # draft should carry.\n'
            '  # customfield_10200: "10300"  # Critical\n'
            '  # customfield_10200: "10301"  # Major\n') in written
    assert "10302" not in written
    assert ('  # components: "10500"  # Backend\n'
            '  # components: "10501"  # Frontend\n') in written


def test_any_other_kind_is_a_comment_naming_the_field_and_saying_a_draft_cannot(
        written):
    for name, words in (("Due date (duedate)", "a date"),
                        ("Approvers (customfield_10300)", "a list of users")):
        assert (f"  # {name}: required, and {words} —\n"
                "  # nothing a draft carries can fill it, so Jira's form asks for it\n"
                "  # before the ticket is created.\n") in written


def test_what_the_chip_sends_and_a_field_jira_gives_a_default_are_left_out(written):
    # The project, the issue type, the summary and the description travel on every
    # draft; the reporter is the commented account; the team and the priority have
    # Jira's own defaults.
    keys = set(re.findall(r"^ *(?:# )?([A-Za-z_][A-Za-z0-9_]*):(?: |$)", written,
                          re.MULTILINE))
    for key in ("summary", "issuetype", "project", "description", "priority",
                "customfield_10001", "labels"):
        assert key not in keys and f"({key})" not in written
    assert {"customfield_10101", "customfield_10200", "components"} <= keys
    fields = yaml.safe_load(written)["fields"]
    assert fields == {"customfield_10101": "{name}: {reason}"}


def test_the_account_id_is_written_only_as_a_comment_with_its_reason(written):
    assert f'  # reporter: "{ACCOUNT}"\n' in written
    assert "reporter" not in yaml.safe_load(written)["fields"]
    reason = written.split("fields:\n", 1)[1].split("# reporter:", 1)[0]
    assert "whoever is signed in" in reason and "under one name" in reason


# --- what it hands over -------------------------------------------------------------

def test_the_file_is_one_the_package_loads(written):
    config = jira._parse(yaml.safe_load(written), "jira.yaml")
    assert (config.base_url, config.project_id, config.issue_type_id) == (
        SITE, "10000", "3")
    assert config.fields == {"customfield_10101": "{name}: {reason}"}
    assert config.action("reason") is not None
    node = config.action("node")
    assert node is not None and (node.label, node.icon) == ("Jira all", "jira")


def test_it_writes_config_jira_yaml_where_there_is_none(folder, tmp_path,
                                                         monkeypatch):
    root = tmp_path / "deployment"
    (root / "config").mkdir(parents=True)
    monkeypatch.chdir(root)
    monkeypatch.delenv("LITTLE_SISTER_CONFIG_DIR")
    _saved(folder, "myself.json", "project.json", "fields-EX-3.json")
    code, out, err = _run(folder, "--issue-type", "3")
    assert code == 0, err
    assert out == ""
    assert "Wrote config/jira.yaml." in err
    written = (root / "config" / "jira.yaml").read_text(encoding="utf-8")
    assert jira._parse(yaml.safe_load(written), "config/jira.yaml").project_id == (
        "10000")


def test_it_prints_the_file_where_one_is_there_and_leaves_that_one_alone(
        folder, tmp_path, monkeypatch):
    root = tmp_path / "deployment"
    (root / "config").mkdir(parents=True)
    (root / "config" / "jira.yaml").write_text("# the deployment's own\n",
                                               encoding="utf-8")
    monkeypatch.chdir(root)
    monkeypatch.delenv("LITTLE_SISTER_CONFIG_DIR")
    _saved(folder, "myself.json", "project.json", "fields-EX-3.json")
    code, out, err = _run(folder, "--issue-type", "3")
    assert code == 0, err
    assert out.startswith("# The `jira` aspect for Example (EX)")
    assert "config/jira.yaml is there already, and is not replaced" in err
    assert (root / "config" / "jira.yaml").read_text(encoding="utf-8") == (
        "# the deployment's own\n")


def test_it_prints_when_asked_to_where_it_could_write(folder, tmp_path, monkeypatch):
    root = tmp_path / "deployment"
    (root / "config").mkdir(parents=True)
    monkeypatch.chdir(root)
    monkeypatch.delenv("LITTLE_SISTER_CONFIG_DIR")
    _saved(folder, "myself.json", "project.json", "fields-EX-3.json")
    code, out, err = _run(folder, "--issue-type", "3", "--print")
    assert code == 0, err
    assert out.startswith("# The `jira` aspect") and "Printed rather" not in err
    assert list((root / "config").iterdir()) == []


def test_it_prints_where_the_configuration_names_its_roots(written, folder):
    # The suite runs with LITTLE_SISTER_CONFIG_DIR set, as a deployment with roots of
    # its own does: which of them the file belongs in is the deployment's to say.
    code, out, err = _run(folder, "--issue-type", "3")
    assert code == 0 and out == written
    assert "LITTLE_SISTER_CONFIG_DIR names this deployment's configuration roots" in err


def test_the_command_runs_where_a_deployment_runs_it(folder, tmp_path):
    # `python -m`, in a deployment's root, with the package installed and nothing on
    # PYTHONPATH — and the file it writes is one the package then registers from.
    root = tmp_path / "deployment"
    (root / "config").mkdir(parents=True)
    _saved(folder, "myself.json", "project.json", "fields-EX-3.json")
    env = {"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"}
    done = subprocess.run([sys.executable, "-m", "little_sister_jira.configure", BOARD,
                           "--answers", str(folder), "--issue-type", "Task"],
                          capture_output=True, text=True, cwd=root, env=env,
                          stdin=subprocess.DEVNULL)
    assert done.returncode == 0, done.stderr
    assert "Wrote config/jira.yaml." in done.stderr
    probe = ("import json, little_sister_jira as p; c = p.jira._config; "
             "print(json.dumps([c.project_id, c.issue_type_id]))")
    loaded = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                            text=True, cwd=root, env=env)
    assert loaded.returncode == 0, loaded.stderr
    assert json.loads(loaded.stdout.strip().splitlines()[-1]) == ["10000", "3"]
