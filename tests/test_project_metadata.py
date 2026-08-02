"""Branding, attribution and licensing invariants.

These tests require neither FreeCAD nor a running RPC server. They guard the
project's identity: that the original author's copyright is preserved, that
the project points at its own home, and that no comparative claim about the
upstream project creeps into user-facing text.
"""

from pathlib import Path
import tomllib

REPO_ROOT = Path(__file__).resolve().parent.parent

UPSTREAM_COPYRIGHT = "Copyright (c) 2025 Shirokuma (k tanaka)"

CODEBERG_URL = "https://codeberg.org/wibbit/freecad-mcp"

BANNED_COMPARATIVES = [
    "expanded",
    "more complete",
    "improved over",
    "enhanced version",
    "better than",
]


def read(relpath: str) -> str:
    """Return the text contents of a repository-relative file."""
    return (REPO_ROOT / relpath).read_text(encoding="utf-8")


def load_pyproject() -> dict:
    """Return the parsed pyproject.toml as a dict."""
    return tomllib.loads(read("pyproject.toml"))


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


class TestPyproject:
    def test_name_unchanged(self):
        assert load_pyproject()["project"]["name"] == "freecad-mcp"

    def test_authors_is_maintainer(self):
        authors = load_pyproject()["project"]["authors"]
        names = [a.get("name") for a in authors]
        assert names == ["Douglas Furlong"]

    def test_description_credits_upstream(self):
        description = load_pyproject()["project"]["description"]
        assert "neka-nat/freecad-mcp" in description

    def test_description_is_not_desktop_specific(self):
        assert "Claude Desktop" not in load_pyproject()["project"]["description"]

    def test_description_makes_no_comparative_claim(self):
        description = load_pyproject()["project"]["description"].lower()
        for phrase in BANNED_COMPARATIVES:
            assert phrase not in description, f"comparative claim: {phrase!r}"

    def test_all_urls_point_at_codeberg(self):
        urls = load_pyproject()["project"]["urls"]
        assert set(urls) == {
            "Homepage",
            "Documentation",
            "Repository",
            "Issues",
            "Changelog",
        }
        for label, url in urls.items():
            assert url.startswith(CODEBERG_URL), f"{label} still points at {url}"

    def test_entry_point_unchanged(self):
        assert load_pyproject()["project"]["scripts"]["freecad-mcp"] == (
            "freecad_mcp.server:main"
        )


class TestReadmeAttribution:
    def test_no_upstream_security_badge(self):
        """The MseeP badge assesses upstream's repo, not this one."""
        assert "mseep" not in read("README.md").lower()

    def test_no_upstream_contributor_image(self):
        """contrib.rocks renders upstream's contributor list."""
        assert "contrib.rocks" not in read("README.md")

    def test_has_origins_section(self):
        assert "## Origins" in read("README.md")

    def test_origins_credits_original_author_by_name(self):
        assert "Shirokuma (k tanaka)" in read("README.md")

    def test_origins_links_upstream(self):
        assert "https://github.com/neka-nat/freecad-mcp" in read("README.md")

    def test_states_canonical_home(self):
        assert CODEBERG_URL in read("README.md")

    def test_credits_fork_contributors(self):
        readme = read("README.md")
        assert "Martin Bruno" in readme
        assert "MichaelZag" in readme

    def test_makes_no_comparative_claim(self):
        readme = read("README.md").lower()
        for phrase in BANNED_COMPARATIVES:
            assert phrase not in readme, f"comparative claim: {phrase!r}"

    def test_states_no_affiliation(self):
        assert "not affiliated" in read("README.md").lower()


class TestReadmeContent:
    def test_clone_urls_point_at_codeberg(self):
        readme = read("README.md")
        assert "git clone https://codeberg.org/wibbit/freecad-mcp.git" in readme
        assert "git clone https://github.com/neka-nat/freecad-mcp.git" not in readme

    def test_documents_flatpak_addon_path(self):
        assert "~/.var/app/org.freecad.FreeCAD/data/FreeCAD/v1-1/Mod/" in read("README.md")

    def test_retains_claude_desktop_setup(self):
        """Desktop config paths are correct for Desktop users and must survive."""
        assert "claude_desktop_config.json" in read("README.md")

    def test_documents_claude_code_setup(self):
        readme = read("README.md")
        assert "Claude Code" in readme
        assert "claude mcp add" in readme

    def test_has_features_section(self):
        assert "## Features" in read("README.md")

    def test_features_cover_each_capability_group(self):
        readme = read("README.md")
        for group in [
            "Documents & objects",
            "Sketching",
            "Solid modelling",
            "Booleans",
            "Assembly",
            "FEM",
            "TechDraw",
            "Import & export",
            "Inspection",
            "Spreadsheets",
        ]:
            assert group in readme, f"missing feature group: {group}"

    def test_no_hard_tool_count(self):
        """Counts go stale on every tool added."""
        import re
        assert not re.search(r"\b\d{2,}\s+tools\b", read("README.md"))


DOC_FILES = [
    "README.md",
    "docs/QUICKSTART.md",
    "docs/USER_GUIDE.md",
    "docs/session_guide.md",
    "CONTRIBUTING.md",
]


class TestClientNeutrality:
    def test_no_doc_points_issues_at_upstream(self):
        for path in DOC_FILES:
            assert "github.com/neka-nat/freecad-mcp/issues" not in read(path), path

    def test_issue_links_point_at_codeberg(self):
        for path in ["docs/QUICKSTART.md", "docs/USER_GUIDE.md"]:
            assert f"{CODEBERG_URL}/issues" in read(path), path

    def test_server_error_message_lists_claude_code(self):
        source = read("src/freecad_mcp/server.py")
        assert "Claude Code" in source

    def test_session_guide_log_line_lists_claude_code(self):
        """The client list on the log-capture line, not merely anywhere in the file.

        `session_guide.md:4` already mentions Claude Code, so a whole-file check
        would pass without the line 136 edit ever being made.
        """
        line = next(
            l for l in read("docs/session_guide.md").splitlines()
            if "stdout of the `freecad-mcp` process" in l
        )
        assert "Claude Code" in line

    def test_user_guide_intro_is_client_neutral(self):
        """The opening description must not imply Desktop is the only client."""
        intro = read("docs/USER_GUIDE.md")[:2000]
        assert "MCP client" in intro

    def test_quickstart_retains_desktop_config_paths(self):
        """Desktop paths are accurate for Desktop users; supplement, never delete."""
        quickstart = read("docs/QUICKSTART.md")
        assert "claude_desktop_config.json" in quickstart

    def test_quickstart_documents_claude_code(self):
        assert "claude mcp add" in read("docs/QUICKSTART.md")

    def test_no_doc_clones_from_upstream(self):
        """Upstream may be credited as origin, never used as the clone source."""
        for path in DOC_FILES:
            assert "git clone https://github.com/neka-nat/freecad-mcp.git" not in read(path), path
