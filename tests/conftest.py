# SPDX-FileCopyrightText: 2025 Purdue University
# SPDX-License-Identifier: MIT

"""Collection rules shared by every test module."""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """A collected test carrying neither the `unit` nor the `integration` marker fails the run."""
    unmarked = [item.nodeid for item in items
                if not any(item.get_closest_marker(name) for name in ('unit', 'integration'))]
    if unmarked:
        listing = '\n  '.join(unmarked)
        raise pytest.UsageError(
            f'every test must carry @pytest.mark.unit or @pytest.mark.integration; unmarked:\n  {listing}')
