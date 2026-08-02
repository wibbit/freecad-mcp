"""Branding, attribution and licensing invariants.

These tests require neither FreeCAD nor a running RPC server. They guard the
project's identity: that the original author's copyright is preserved, that
the project points at its own home, and that no comparative claim about the
upstream project creeps into user-facing text.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

UPSTREAM_COPYRIGHT = "Copyright (c) 2025 Shirokuma (k tanaka)"
MAINTAINER_COPYRIGHT = "Copyright (c) 2025-2026 Douglas Furlong"


def read(relpath: str) -> str:
    """Return the text contents of a repository-relative file."""
    return (REPO_ROOT / relpath).read_text(encoding="utf-8")


class TestLicence:
    def test_original_copyright_preserved_verbatim(self):
        assert UPSTREAM_COPYRIGHT in read("LICENSE")

    def test_maintainer_copyright_present(self):
        assert MAINTAINER_COPYRIGHT in read("LICENSE")

    def test_original_copyright_precedes_maintainer(self):
        licence = read("LICENSE")
        assert licence.index(UPSTREAM_COPYRIGHT) < licence.index(MAINTAINER_COPYRIGHT)

    def test_still_mit(self):
        assert "MIT License" in read("LICENSE")
        assert "WITHOUT WARRANTY OF ANY KIND" in read("LICENSE")
