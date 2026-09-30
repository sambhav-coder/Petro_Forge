"""Pytest session isolation: ML registry writes go to a temp directory.

The canonical ModelRegistry persists to ``artifact_dir`` on registration.
Without isolation, test runs rewrite the tracked
``project/ml/artifacts/registry.json`` (timestamps), dirtying the working
tree. This session-scoped autouse fixture redirects the global ML config
to a pytest-managed temp dir and restores it afterwards, so ``pytest``
leaves ``git status`` clean.
"""

import pytest


@pytest.fixture(scope="session", autouse=True)
def _isolate_ml_artifact_dir(tmp_path_factory):
    from ml import config as ml_config

    original = ml_config.config.artifact_dir
    ml_config.config.artifact_dir = str(tmp_path_factory.mktemp("ml_artifacts"))
    yield
    ml_config.config.artifact_dir = original
