"""A configuration root, before anything imports the package.

Importing ``little_sister_jira`` registers the ``jira`` aspect and immediately
reads it, which means it resolves little-sister's configuration roots — and a root
that does not exist is fatal by design, exactly as it is for the library's own
startup. Inside a deployment that never comes up: the deployment *is* the working
directory and its ``config/`` is right there. A test suite has no such directory,
so it supplies an empty one.

Empty on purpose. Nothing here declares the aspect, so the package loads with no
configuration — the same state a deployment that has not written ``jira.yaml`` is
in, and the state every test then overrides for itself.

This module has to run **before** the first test module imports the package, which
is precisely what a ``conftest.py`` is: pytest imports it during collection, ahead
of the tests beside it.
"""
from __future__ import annotations

import os
import tempfile

os.environ.setdefault("LITTLE_SISTER_CONFIG_DIR",
                      tempfile.mkdtemp(prefix="little-sister-jira-config-"))


# Below the environment on purpose, like everything else in this suite: nothing here
# imports the package, but keeping the order visible is the point of the file.
import pytest
from flask import Flask


@pytest.fixture
def dashboard_context():
    """A request context with a `status` route, so a draft carries its link back.

    The same stand-in `tests/test_dashboard_link.py` builds: the endpoint *name* is
    what this package writes against, so that is what a stand-in has to reproduce.
    """
    app = Flask(__name__)
    app.add_url_rule("/status/<path:branch>", "status", lambda branch: "")
    with app.test_request_context("/", base_url="https://monitor.example.org"):
        yield
