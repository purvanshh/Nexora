#!/usr/bin/env python3
"""Reset mock_app JSON data to seed snapshots."""

from __future__ import annotations

from mock_app.routers.finance import reset_chaos
from mock_app.store import reset_data


def main() -> None:
    reset_data()
    reset_chaos()
    print("Mock app data reset to seed.")


if __name__ == "__main__":
    main()
