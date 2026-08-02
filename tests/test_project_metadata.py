"""Branding, attribution and licensing invariants.

These tests require neither FreeCAD nor a running RPC server. They guard the
project's identity: that the original author's copyright is preserved, that
the project points at its own home, and that no comparative claim about the
upstream project creeps into user-facing text.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

UPSTREAM_COPYRIGHT = "Copyright (c) 2025 Shirokuma (k tanaka)"


def read(relpath: str) -> str:
    """Return the text contents of a repository-relative file."""
    return (REPO_ROOT / relpath).read_text(encoding="utf-8")


class TestLicence:
    def test_original_copyright_preserved_verbatim(self):
        assert UPSTREAM_COPYRIGHT in read("LICENSE")

    def test_no_copyright_lines_added(self):
        """A licence file is a legal notice, not a credits roll.

        MIT requires only that the existing notice be retained. Contributors
        hold copyright automatically, so extra lines record nothing; attribution
        belongs in the README instead.
        """
        copyright_lines = [
            l for l in read("LICENSE").splitlines() if l.startswith("Copyright (c)")
        ]
        assert copyright_lines == [UPSTREAM_COPYRIGHT]

    def test_still_mit(self):
        assert "MIT License" in read("LICENSE")
        assert "WITHOUT WARRANTY OF ANY KIND" in read("LICENSE")
