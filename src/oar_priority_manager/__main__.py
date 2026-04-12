"""Allow the package to be run directly via ``python -m oar_priority_manager``.

Delegates immediately to the application entry point in
``oar_priority_manager.app.main``.
"""
from __future__ import annotations

import sys

from oar_priority_manager.app.main import main

sys.exit(main())
