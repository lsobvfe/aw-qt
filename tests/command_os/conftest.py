import os
from pathlib import Path
import sys

import pytest
from PyQt6.QtWidgets import QApplication


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
activitywatch_root = Path(__file__).resolve().parents[3]
for package_root in (
    activitywatch_root / "aw-qt",
    activitywatch_root / "aw-client",
    activitywatch_root / "aw-core",
):
    sys.path.insert(0, str(package_root))


@pytest.fixture(scope="session", autouse=True)
def qt_application():
    application = QApplication.instance() or QApplication([])
    yield application
