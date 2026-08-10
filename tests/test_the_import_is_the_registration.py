"""One import wires the whole extension — the claim the package is built on.

ADR-0001 decision 9, the README's install snippet and a deployment's `wsgi.py` all
rest on ``import little_sister_jira`` doing three things: declaring the ``jira``
aspect, reading it, and filling the slots the file asks for. Every other test here
calls :func:`~little_sister_jira.jira.register` by hand, so all of them would keep
passing if that call were dropped from ``__init__`` — and a deployment would then
boot with no aspect and no chips, its only trace a warning about an unknown
configuration file.

It runs in a **subprocess** because the import has already happened by the time any
in-process test could look, and re-importing a module does not re-run it.

The probe's environment is built from scratch rather than inherited, which is a
second property and not tidiness: with no ``PYTHONPATH`` handed down, the subprocess
can only find this package where a **deployment** finds it — installed. So these two
also fail if the package is merely on a path, which is the same class of illusion a
source checkout creates for package data (``plugin-repository.md`` §7).

The consequence for whoever is reading this because they just saw
``ModuleNotFoundError: No module named 'little_sister_jira'``: run the suite through
``uv run pytest``, which syncs this project into the environment first. A bare
``pytest`` with ``PYTHONPATH=src`` passes every other test here and fails these two,
and that failure is about how the suite was invoked, not about the code. If it ever
has to work both ways, inherit ``os.environ`` and override
``LITTLE_SISTER_CONFIG_DIR`` alone — at the cost of the property above.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "jira.yaml"

PROBE = """
import json, sys
import little_sister_jira
from little_sister import config_dir, slots

print(json.dumps({
    "aspects": sorted(config_dir.registered_aspects()),
    "fillers": sorted([f.package, f.template]
                      for name in ("reason.actions", "node.actions")
                      for f in slots.fillers(name)),
    "configured": little_sister_jira.jira._config is not None,
}))
"""


def _probe(tmp_path, aspect_file: bool):
    root = tmp_path / "config"
    root.mkdir()
    if aspect_file:
        # The example with its placeholder host replaced — the document an operator
        # ends up with. Copied unedited it is refused, which is a different test.
        (root / "jira.yaml").write_text(
            EXAMPLE.read_text(encoding="utf-8").replace(
                "https://<your-site>.atlassian.net", "https://tracker.example.org"),
            encoding="utf-8")
    done = subprocess.run([sys.executable, "-c", PROBE], capture_output=True,
                          text=True, cwd=tmp_path,
                          env={"PATH": "/usr/bin:/bin",
                               "LITTLE_SISTER_CONFIG_DIR": str(root)})
    assert done.returncode == 0, done.stderr
    import json
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_importing_the_package_declares_the_aspect_and_fills_both_slots(tmp_path):
    result = _probe(tmp_path, aspect_file=True)
    assert result["aspects"] == ["jira"]
    assert result["configured"] is True
    assert result["fillers"] == [["little_sister_jira", "node_actions.html"],
                                 ["little_sister_jira", "reason_actions.html"]]


def test_importing_it_without_a_configuration_still_declares_and_still_draws_nothing(
        tmp_path):
    # The aspect must be declared even when the file is absent, or writing one later
    # earns "not a known configuration aspect" instead of a chip. The reason filler
    # is registered too, and declines every line until there is a configuration.
    result = _probe(tmp_path, aspect_file=False)
    assert result["aspects"] == ["jira"]
    assert result["configured"] is False
    assert result["fillers"] == [["little_sister_jira", "reason_actions.html"]]
