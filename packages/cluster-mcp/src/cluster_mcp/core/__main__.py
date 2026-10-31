# SPDX-FileCopyrightText: 2026 Purdue RCAC and Contributors
# SPDX-License-Identifier: MIT

"""Allow running as ``python -m cluster_mcp.core``."""

import sys

from cluster_mcp.core import main

sys.exit(main())
