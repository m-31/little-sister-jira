"""little-sister surface extension: the Jira issue chip.

Importing this package registers everything the extension owns — the ``jira``
configuration aspect and the two slot fillers that draw the chips. A deployment
therefore needs one line in its ``wsgi.py``, before it imports
``little_sister.app``::

    import little_sister_jira               # noqa: F401  aspect + both chips
    from little_sister.app import app       # builds the engine, scans the config

The order is load-bearing in both directions: the aspect has to be declared before
the first configuration scan, or the library has already warned that
``config/jira.yaml`` is not a known aspect, and a slot has to be filled before the
first render.

Unlike a check type, which registers by the ``@register`` side effect of defining
its class, this extension has work to do at registration time — declare the aspect,
read the file, and fill only the slots the file asks for. So the import calls
:func:`~little_sister_jira.jira.register` explicitly here, and that call is what
the deployment's single import stands for.

``require_api`` declares the **check API epoch** this package was built for. It
refuses at startup, naming both epochs, when the library has moved past the surface
this package writes against — the upgrade an install-time floor cannot see, because
a floor has no ceiling (little-sister ADR-0051). The epoch versions little-sister's
whole promised surface, not only the names a check type uses, which is why an
extension that registers no check type still declares one.
"""
from importlib.metadata import PackageNotFoundError, version

from little_sister.checks import require_api

require_api(2)

from little_sister_jira import jira  # noqa: E402  imported after the epoch check

jira.register()

try:
    __version__ = version("little-sister-jira")
except PackageNotFoundError:  # running from a source tree with no install
    __version__ = "0+unknown"

__all__ = ["jira"]
