# Codeberg Migration and Rebrand Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the project to `codeberg.org/wibbit/freecad-mcp` as an independently maintained project, with correct attribution to the original author and accurate, client-neutral documentation.

**Architecture:** This migration changes metadata, documentation and hosting only. No module, entry point, addon directory, or tool implementation is touched, so the maintainer's live setup keeps working throughout. Branding and attribution invariants are locked in by a new pure-Python test module (`tests/test_project_metadata.py`) that requires no running FreeCAD, making each content change test-driven and permanently guarded against regression.

**Tech Stack:** Python 3.12, hatchling, pytest (run via `./check`), git, Codeberg (Forgejo) REST API v1, GitHub CLI (`gh`).

**Spec:** `docs/superpowers/specs/2026-08-02-codeberg-migration-design.md`

## Global Constraints

Every task's requirements implicitly include this section.

- **`LICENSE` is not modified at all.** MIT requires only that the existing copyright and permission notice be retained, which the untouched file satisfies. Never reword, relocate or remove `Copyright (c) 2025 Shirokuma (k tanaka)`, and **never add** a maintainer or contributors copyright line — contributors hold copyright automatically, so such lines record nothing, and a licence file is a legal notice rather than a credits roll. Attribution belongs in the README (Task 4).
- **No comparative claims about upstream** in any metadata or README text. Prohibited: "expanded", "more complete than", "improved over", "enhanced version of". Statements of what the project *is* are fine; statements of how it *compares* are not.
- **No hard tool counts** in `README.md` (e.g. "79 tools"). Category descriptions only.
- **Do not rename** the Python module `freecad_mcp`, the console script `freecad-mcp`, the addon directory `FreeCADMCP`, or the local checkout directory `~/git/freecad-mcp`.
- **Do not delete** the `claude_desktop_config.json` paths from documentation. They are correct for Claude Desktop users. Supplement them; do not replace them.
- **Project name stays `freecad-mcp`.** Only the host and namespace change.
- Canonical Codeberg URL: `https://codeberg.org/wibbit/freecad-mcp`
- Test command: `./check [pytest args]` — a repo-root wrapper around `uv run --extra dev python -m pytest`. Do **not** use `uv run --extra dev pytest` (uv does not put the console script on PATH for extras) nor `--with pytest` (that ignores the pytest version pinned in `pyproject.toml`).
- **A bare `./check` runs the integration suite against a live FreeCAD over RPC**, creating and closing scratch documents in the running session. Always pass `tests/test_project_metadata.py` when you only need the metadata guards.
- **Never prefix commands with `timeout N`.** It breaks permission prefix-matching and forces a fresh approval prompt for every variant.
- Every commit message ends with:
  ```
  Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
  ```

### Why the local directory must not be renamed

Four things depend on the literal path `/home/dfurlong/git/freecad-mcp`:

1. `~/.claude.json` → `mcpServers.freecad.args[0]` (the proxy script path)
2. `freecad-mcp-proxy.py` → its internal `uv --directory ~/git/freecad-mcp` spawn command
3. `CLAUDE.md` and `docs/` path references
4. The flatpak addon **symlink**: `~/.var/app/org.freecad.FreeCAD/data/FreeCAD/v1-1/Mod/FreeCADMCP` → `/home/dfurlong/git/freecad-mcp/addon/FreeCADMCP`

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `freecad-mcp-proxy.py`, `freecad-mcp-proxy.TODO.md` | Live MCP entry point, tracked unchanged | 1 |
| `tests/test_project_metadata.py` | **New.** Branding/attribution invariants, no FreeCAD needed | 2–6 |
| `LICENSE` | Unmodified; invariants locked by tests | 2 |
| `pyproject.toml` | Package metadata, authorship, URLs | 3 |
| `README.md` | Attribution, Origins, canonical-home notice, contributors | 4 |
| `README.md` | Features, client setup, install paths | 5 |
| `docs/QUICKSTART.md`, `docs/USER_GUIDE.md`, `docs/session_guide.md`, `src/freecad_mcp/server.py` | Client neutrality, issue URLs | 6 |
| `CHANGELOG.md` | `[Unreleased]` migration entry | 7 |

`tests/test_project_metadata.py` is a single file because its assertions all answer one question — "is this project correctly identified as its own?" — and they change together.

### Deviation from spec §8, resolved

Spec §8 calls for a "README banner directing issues to Codeberg" on GitHub. Because a push mirror serves **identical content**, a GitHub-only README is impossible without diverging the mirror. Resolution: the README carries a **canonical-home notice** (correct and useful on both hosts), and GitHub-specific signalling is done via repository **description** and **disabled issues/PRs** instead. Implemented in Tasks 4 and 11.

---

### Task 1: Track the vision proxy unchanged

The proxy is the live MCP entry point but is untracked, so the working setup currently depends on a file that exists on exactly one machine. Commit it byte-for-byte unchanged; integration is out of scope (Task 10 files the issue).

**Files:**
- Add (untracked → tracked): `freecad-mcp-proxy.py`
- Add (untracked → tracked): `freecad-mcp-proxy.TODO.md`

**Interfaces:**
- Consumes: nothing
- Produces: nothing (later tasks do not import or modify these files)

- [ ] **Step 1: Record the current checksums**

```bash
cd /home/dfurlong/git/freecad-mcp
sha256sum freecad-mcp-proxy.py freecad-mcp-proxy.TODO.md | tee /tmp/proxy-checksums.txt
```

Expected: two lines of output, saved for Step 3.

- [ ] **Step 2: Stage and commit both files**

```bash
git add freecad-mcp-proxy.py freecad-mcp-proxy.TODO.md
git commit -m "$(cat <<'EOF'
chore: track vision proxy as-is ahead of migration

The proxy is the live MCP entry point but was untracked, leaving the
working setup dependent on a file present on only one machine. Committed
unchanged; integration into the package remains outstanding and is
tracked as a separate issue.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3: Verify the files were not modified**

```bash
sha256sum -c /tmp/proxy-checksums.txt && git status --porcelain freecad-mcp-proxy.py freecad-mcp-proxy.TODO.md
```

Expected: both files report `OK`, and `git status --porcelain` prints **nothing** (clean, tracked).

---

### Task 2: Establish the metadata test module and licence invariants

**`LICENSE` is not modified by this migration.** MIT's only obligation is that the existing
copyright and permission notice be retained, which an untouched file already satisfies. Adding
a maintainer line is optional and cosmetic; adding a contributors line is misleading, because
copyright arises automatically on authorship and no notice affects who holds it. A licence file
is a legal notice, not a credits roll. Attribution is handled properly in the README by Task 4.

These tests are **regression guards, not TDD drivers** — they pass the moment the module exists,
because they lock in a state that is already correct. That is the point: they make a future
edit to `LICENSE` fail loudly.

**Files:**
- Create: `tests/test_project_metadata.py`
- Restore: `LICENSE` (must end byte-identical to its pre-migration state)

**Interfaces:**
- Consumes: nothing
- Produces: `tests/test_project_metadata.py` containing module-level constant `REPO_ROOT` (a `pathlib.Path` pointing at the repository root) and helper `read(relpath: str) -> str` returning file contents as text. Tasks 3–6 add tests to this same file and reuse both.

- [ ] **Step 1: Restore `LICENSE` to its original, unmodified state**

The file must contain exactly one copyright line, `Copyright (c) 2025 Shirokuma (k tanaka)`,
and nothing else may differ from upstream's version.

```bash
git checkout eb4ae67 -- LICENSE
git show eb4ae67:LICENSE | sha256sum
sha256sum LICENSE
```

Expected: the two hashes match.

- [ ] **Step 2: Write the test module**

Create `tests/test_project_metadata.py`:

```python
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
```

- [ ] **Step 3: Run the tests**

```bash
./check tests/test_project_metadata.py -v
```

Expected: **3 passed.** All three pass immediately — see the note at the head of this task.
`test_no_copyright_lines_added` is the one that matters: it fails if anyone later appends a
copyright line, which is exactly the mistake this task exists to prevent.

- [ ] **Step 4: Confirm `LICENSE` is unchanged from its pre-migration state**

```bash
git diff eb4ae67 -- LICENSE
```

Expected: **no output.** Any diff here is a failure of the task.

- [ ] **Step 5: Commit**

```bash
git add LICENSE tests/test_project_metadata.py
git commit -m "$(cat <<'EOF'
test: guard licence invariants; leave LICENSE unmodified

MIT requires only that the existing copyright and permission notice be
retained, which the untouched file already satisfies. An earlier attempt
added maintainer and contributor copyright lines; both are reverted.
Contributors hold copyright automatically, so such lines record nothing,
and a licence file is a legal notice rather than a credits roll.
Attribution is handled in the README instead.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Correct package metadata in pyproject.toml

`authors` currently names `k-tanaka` and all five URLs point at upstream's GitHub repo — both inherited from the fork and inaccurate for this project.

**Files:**
- Modify: `pyproject.toml:4` (description), `pyproject.toml:6-8` (authors), `pyproject.toml:37-42` (urls)
- Modify: `tests/test_project_metadata.py` (append)

**Interfaces:**
- Consumes: `REPO_ROOT`, `read()` from Task 2
- Produces: module-level constant `CODEBERG_URL = "https://codeberg.org/wibbit/freecad-mcp"` and helper `load_pyproject() -> dict`, both reused by Tasks 4–6

- [ ] **Step 1: Write the failing test**

Append to `tests/test_project_metadata.py`:

```python
import tomllib

CODEBERG_URL = "https://codeberg.org/wibbit/freecad-mcp"

BANNED_COMPARATIVES = [
    "expanded",
    "more complete",
    "improved over",
    "enhanced version",
    "better than",
]


def load_pyproject() -> dict:
    """Return the parsed pyproject.toml as a dict."""
    return tomllib.loads(read("pyproject.toml"))


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
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
./check tests/test_project_metadata.py::TestPyproject -v
```

Expected: **4 failed, 3 passed.** `test_name_unchanged`, `test_entry_point_unchanged` and
`test_description_makes_no_comparative_claim` pass (the current description contains no banned
phrase). The four failures are `test_authors_is_maintainer` (author is `k-tanaka`),
`test_description_credits_upstream` and `test_description_is_not_desktop_specific`
(description reads "Control FreeCAD from Claude Desktop"), and `test_all_urls_point_at_codeberg`
(URLs point at `github.com/neka-nat`).

- [ ] **Step 3: Update the metadata**

In `pyproject.toml`, replace line 4:

```toml
description = "FreeCAD MCP server - Control FreeCAD from Claude Desktop"
```

with:

```toml
description = "FreeCAD MCP server for driving FreeCAD from MCP clients. Based on neka-nat/freecad-mcp."
```

Replace lines 6-8:

```toml
authors = [
    { name = "k-tanaka", email = "" }
]
```

with:

```toml
authors = [
    { name = "Douglas Furlong" }
]
```

Replace lines 37-42:

```toml
[project.urls]
Homepage = "https://github.com/neka-nat/freecad-mcp"
Documentation = "https://github.com/neka-nat/freecad-mcp/blob/main/README.md"
Repository = "https://github.com/neka-nat/freecad-mcp"
Issues = "https://github.com/neka-nat/freecad-mcp/issues"
Changelog = "https://github.com/neka-nat/freecad-mcp/blob/main/CHANGELOG.md"
```

with (note Forgejo's `/src/branch/main/` file-path form, which differs from GitHub's `/blob/main/`):

```toml
[project.urls]
Homepage = "https://codeberg.org/wibbit/freecad-mcp"
Documentation = "https://codeberg.org/wibbit/freecad-mcp/src/branch/main/README.md"
Repository = "https://codeberg.org/wibbit/freecad-mcp"
Issues = "https://codeberg.org/wibbit/freecad-mcp/issues"
Changelog = "https://codeberg.org/wibbit/freecad-mcp/src/branch/main/CHANGELOG.md"
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
./check tests/test_project_metadata.py -v
```

Expected: 10 passed.

- [ ] **Step 5: Verify the package still builds**

```bash
uv build 2>&1 | tail -5
```

Expected: builds a `.whl` and `.tar.gz` under `dist/` with no error. Then clean up:

```bash
rm -rf dist/
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml tests/test_project_metadata.py
git commit -m "$(cat <<'EOF'
chore: point package metadata at Codeberg and correct authorship

The authors field and all five project URLs were inherited from upstream
and named the wrong author and repository. Description is now
client-neutral and credits the project it is based on, without making
any comparative claim that upstream's roadmap could falsify.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: README attribution, Origins and contributors

Removes two badges that describe *upstream's* repository, adds the Origins section, the canonical-home notice, and a contributors list covering this fork's contributors.

**Files:**
- Modify: `README.md:1` (MseeP badge), `README.md:3-5` (title/tagline), `README.md:191-197` (contributors)
- Modify: `tests/test_project_metadata.py` (append)

**Interfaces:**
- Consumes: `read()`, `CODEBERG_URL`, `BANNED_COMPARATIVES` from Tasks 2–3
- Produces: nothing new

- [ ] **Step 1: Write the failing test**

Append to `tests/test_project_metadata.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
./check tests/test_project_metadata.py::TestReadmeAttribution -v
```

Expected: **7 failed, 2 passed.** Two pass incidentally: `test_origins_links_upstream` (upstream
URLs are already present via the clone commands) and `test_makes_no_comparative_claim` (the
current README contains no banned phrase). The other seven fail.

- [ ] **Step 3: Replace the README header**

Replace `README.md` lines 1-5 (the MseeP badge, blank line, title, blank line, and the "control FreeCAD from Claude Desktop" sentence) with:

```markdown
# FreeCAD MCP

Drive FreeCAD from any MCP client — parametric modelling, sketching, assemblies,
FEM analysis and technical drawings, exposed as MCP tools.

> **Canonical home:** [codeberg.org/wibbit/freecad-mcp](https://codeberg.org/wibbit/freecad-mcp)
> The GitHub repository is a read-only mirror. Please file issues and pull requests on Codeberg.
```

- [ ] **Step 4: Replace the Contributors section and add Origins**

Replace `README.md` lines 191-197 (the entire `## Contributors` section including the `contrib.rocks` anchor, image, and "Made with" line) with:

```markdown
## Contributors

- **Shirokuma (k tanaka)** — author of the upstream project this is based on
- **Douglas Furlong** — maintainer
- **Martin Bruno** — advanced modelling, sketch workflow, assembly and boolean tooling
- **MichaelZag** — GUI defaults and startup quality-of-life improvements

## Origins

This project began as a fork of
[`neka-nat/freecad-mcp`](https://github.com/neka-nat/freecad-mcp) by
**Shirokuma (k tanaka)**, whose work is the foundation everything here is built on.

It has since diverged and is developed and maintained independently, with its own
tool surface, documentation and release history. It is not affiliated with, nor
endorsed by, the upstream project.

The original MIT licence and copyright notice are retained in full — see
[`LICENSE`](LICENSE).
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
./check tests/test_project_metadata.py -v
```

Expected: 19 passed.

- [ ] **Step 6: Commit**

```bash
git add README.md tests/test_project_metadata.py
git commit -m "$(cat <<'EOF'
docs: credit the original author and state project independence

Adds an Origins section crediting Shirokuma (k tanaka) and linking
upstream, plus a contributor list covering this fork's contributors.
Removes the MseeP badge and contrib.rocks image, both of which describe
upstream's repository rather than this one.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: README features, install paths and client setup

Adds the missing feature overview, the flatpak addon path, a Claude Code CLI setup section, and repoints clone URLs at Codeberg.

**Files:**
- Modify: `README.md` — install-path list, clone URLs, `## Setting up Claude Desktop` section, `## Tools` section
- Modify: `tests/test_project_metadata.py` (append)

**Interfaces:**
- Consumes: `read()`, `CODEBERG_URL` from Tasks 2–3
- Produces: nothing new

- [ ] **Step 1: Write the failing test**

Append to `tests/test_project_metadata.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
./check tests/test_project_metadata.py::TestReadmeContent -v
```

Expected: **5 failed, 2 passed.** `test_retains_claude_desktop_setup` and `test_no_hard_tool_count`
pass; the other five fail.

- [ ] **Step 3: Add the flatpak addon path**

In the addon-directory list, after the `Arch / CachyOS` bullet, add a new bullet at the same indentation:

```markdown
  * Flatpak: `~/.var/app/org.freecad.FreeCAD/data/FreeCAD/v1-1/Mod/`
```

- [ ] **Step 4: Repoint both clone URLs**

There are **two** occurrences of the clone command (in the addon-install block and the "For developer" block). Change both from:

```bash
git clone https://github.com/neka-nat/freecad-mcp.git
```

to:

```bash
git clone https://codeberg.org/wibbit/freecad-mcp.git
```

Also add a flatpak copy example to the addon-install code block, after the Arch/CachyOS lines:

```bash
# For Linux (Flatpak)
mkdir -p ~/.var/app/org.freecad.FreeCAD/data/FreeCAD/v1-1/Mod/
cp -r addon/FreeCADMCP ~/.var/app/org.freecad.FreeCAD/data/FreeCAD/v1-1/Mod/
```

- [ ] **Step 5: Retitle the client setup section and add Claude Code**

Change the heading `## Setting up Claude Desktop` to `## Setting up an MCP client`, and change the sentence `And you need to edit Claude Desktop config file, \`claude_desktop_config.json\`.` to `Then configure your MCP client.`

Immediately after that sentence, insert a new subsection **before** the existing JSON examples:

```markdown
### Claude Code (CLI)

```bash
claude mcp add freecad -- uvx freecad-mcp
```

Or edit `~/.claude.json` directly, using the same `mcpServers` block shown below.

### Claude Desktop

Edit `claude_desktop_config.json`:
```

The existing JSON examples then follow unchanged under the Claude Desktop subsection.

- [ ] **Step 6: Add the Features section**

Immediately **before** the `## Tools` heading, insert:

```markdown
## Features

| Group | Covers |
|---|---|
| Documents & objects | create/load/save/close, object CRUD, rename, copy, visibility, undo, status |
| Sketching | sketches on plane/face/body, datum planes, contour building, attachment |
| Sketch-based features | pad/extrude (bidirectional), pocket, groove |
| Solid modelling | loft, revolve, sweep, tube, 3D splines, fillet, chamfer, shell |
| Transform & pattern | transform, align, mirror, linear and circular patterns, reference planes/axes |
| Booleans | union, cut, intersection |
| Assembly | Assembly3 (constraints + solver), Assembly4 (LCS-based), parts library, BOM, assembly export |
| FEM | CalculiX-driven stress analysis |
| TechDraw | pages, views, dimensions |
| Import & export | STEP, DXF, airfoil profiles, object export |
| Inspection | viewport capture, shape topology, measurement, FreeCAD error log access |
| Spreadsheets | read and write |
| Escape hatch | `execute_code` for operations without a dedicated tool |
| Guided prompts | workflow prompts for session startup, sketching, booleans, assembly, primitives and FEM |

Full signatures and examples: [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md).
```

- [ ] **Step 7: Run the tests to verify they pass**

```bash
./check tests/test_project_metadata.py -v
```

Expected: 26 passed.

- [ ] **Step 8: Commit**

```bash
git add README.md tests/test_project_metadata.py
git commit -m "$(cat <<'EOF'
docs: document feature set, flatpak path and Claude Code setup

The README documented no feature set, omitted the flatpak addon path,
and covered only Claude Desktop despite the CLI being a supported
client. Desktop instructions are retained as one client among several.
Clone URLs now point at Codeberg.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Client neutrality across docs and server

Three different treatments — see spec §5. A blanket find-and-replace is wrong: `claude_desktop_config.json` paths are correct for Desktop users.

**Files:**
- Modify: `docs/QUICKSTART.md:9,60,112,204`
- Modify: `docs/USER_GUIDE.md:3,19,34,52,54,569`
- Modify: `docs/session_guide.md:136`
- Modify: `src/freecad_mcp/server.py:3069`
- Modify: `tests/test_project_metadata.py` (append)

**Interfaces:**
- Consumes: `read()`, `CODEBERG_URL` from Tasks 2–3
- Produces: nothing new

- [ ] **Step 1: Write the failing test**

Append to `tests/test_project_metadata.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
./check tests/test_project_metadata.py::TestClientNeutrality -v
```

Expected: **6 failed, 1 passed.** Only `test_quickstart_retains_desktop_config_paths` passes.

- [ ] **Step 3: Make `docs/USER_GUIDE.md` client-neutral**

- Line 3: change `Complete guide to using FreeCAD MCP with Claude Desktop.` → `Complete guide to using FreeCAD MCP with an MCP client such as Claude Code or Claude Desktop.`
- Line 19: change `FreeCAD MCP enables you to control FreeCAD through Claude Desktop using natural language.` → `FreeCAD MCP enables you to control FreeCAD through an MCP client using natural language.`
- Line 34: in the architecture diagram, change `Claude Desktop (User Interface)` → `MCP client (Claude Code, Claude Desktop, …)`
- Lines 52 and 54: change `- ✅ Claude Desktop installed` → `- ✅ An MCP client installed (Claude Code or Claude Desktop)` and `- ✅ Claude Desktop configured` → `- ✅ Your MCP client configured`
- Line 569: change `[Report bugs](https://github.com/neka-nat/freecad-mcp/issues)` → `[Report bugs](https://codeberg.org/wibbit/freecad-mcp/issues)`
- Line 493-496: leave the Desktop restart/config/log troubleshooting steps as they are — they are Desktop-specific and correct.

- [ ] **Step 4: Make `docs/QUICKSTART.md` client-neutral**

- Line 9: change `- ✅ Claude Desktop installed` → `- ✅ An MCP client installed (Claude Code or Claude Desktop)`
- Line 60: change the heading `## Step 3: Configure Claude Desktop (1 minute)` → `## Step 3: Configure your MCP client (1 minute)`
- Immediately under that heading, insert a Claude Code subsection **before** the existing `### Find Config File` block:

```markdown
### Claude Code (CLI)

```bash
claude mcp add freecad -- uvx freecad-mcp
```

That is the whole setup — skip to Step 4.

### Claude Desktop
```

  The existing `### Find Config File`, config paths, `### Add Configuration` and
  `### Restart Claude Desktop` blocks then follow unchanged, nested under Claude Desktop.
- Line 112: change `Open Claude Desktop and try these commands:` → `In your MCP client, try these commands:`
- Line 204: change `[Report bugs or request features](https://github.com/neka-nat/freecad-mcp/issues)` → `[Report bugs or request features](https://codeberg.org/wibbit/freecad-mcp/issues)`

- [ ] **Step 5: Extend the already-neutral client lists**

In `docs/session_guide.md:136`, change:

```
**Path**: stdout of the `freecad-mcp` process (captured by Claude Desktop, OpenCode, or your MCP client's log)
```

to:

```
**Path**: stdout of the `freecad-mcp` process (captured by Claude Code, Claude Desktop, OpenCode, or your MCP client's log)
```

In `src/freecad_mcp/server.py:3069`, change:

```python
            "ERROR: freecad-mcp must be launched as a subprocess by an MCP client (e.g. Claude Desktop, opencode).\n"
```

to:

```python
            "ERROR: freecad-mcp must be launched as a subprocess by an MCP client (e.g. Claude Code, Claude Desktop, opencode).\n"
```

- [ ] **Step 6: Check for any remaining upstream issue links**

```bash
grep -rn "github.com/neka-nat/freecad-mcp/issues" --include="*.md" --include="*.py" --include="*.toml" . | grep -v '.venv/' | grep -v 'docs/superpowers/'
```

Expected: **no output**. If any line is printed, repoint it at `https://codeberg.org/wibbit/freecad-mcp/issues` and re-run.

- [ ] **Step 7: Run the full metadata suite**

```bash
./check tests/test_project_metadata.py -v
```

Expected: 33 passed.

- [ ] **Step 8: Verify the server module still imports**

```bash
uv run python -c "import freecad_mcp.server; print('import OK')"
```

Expected: `import OK` (guards against a typo in the `server.py` string edit).

- [ ] **Step 9: Commit**

```bash
git add docs/ src/freecad_mcp/server.py tests/test_project_metadata.py
git commit -m "$(cat <<'EOF'
docs: describe supported MCP clients accurately

Documentation described Claude Desktop as the only client, which is
inaccurate — the CLI is the primary client in practice. Desktop-specific
setup is retained and supplemented with Claude Code instructions rather
than replaced. Issue links now point at Codeberg.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: CHANGELOG entry

`CLAUDE.md` requires a `[Unreleased]` entry for every change. This migration is recorded as one coherent entry rather than fragmented across Tasks 2–6, which `CLAUDE.md` permits ("in the same commit as the code change, **or immediately after it**").

**Files:**
- Modify: `CHANGELOG.md:8` (insert a new `[Unreleased]` block above the existing one)

**Interfaces:**
- Consumes: nothing
- Produces: nothing

- [ ] **Step 1: Insert the entry**

In `CHANGELOG.md`, immediately after line 6 (the "adheres to Semantic Versioning" line) and its following blank line, insert:

```markdown
## [Unreleased] - 2026-08-02

### 🔄 Changed

- **Project moved to Codeberg** — the canonical repository is now
  [codeberg.org/wibbit/freecad-mcp](https://codeberg.org/wibbit/freecad-mcp). The GitHub
  repository continues as a read-only push mirror with issues disabled. All package URLs,
  clone commands and issue links updated.
- **Authorship corrected** — `pyproject.toml` named the upstream author and pointed all five
  project URLs at upstream's repository. Now names the maintainer and this project's URLs.
- **Client-neutral documentation** — docs described Claude Desktop as the only supported
  client. They now cover Claude Code (CLI) as well; Desktop instructions are retained
  unchanged for Desktop users.

### ✨ Added

- **README feature overview** — capability groups covering documents, sketching, solid
  modelling, booleans, assembly, FEM, TechDraw, import/export, inspection and spreadsheets.
- **README "Origins" section** — credits Shirokuma (k tanaka), links the upstream project,
  and states that this project is independently maintained and unaffiliated.
- **Flatpak addon path** — `~/.var/app/org.freecad.FreeCAD/data/FreeCAD/v1-1/Mod/`, previously
  undocumented despite being a common Linux install route.
- **`tests/test_project_metadata.py`** — guards branding, attribution and licensing
  invariants. Runs without FreeCAD.
- **Vision proxy tracked** — `freecad-mcp-proxy.py` and its TODO are now in version control.
  Integration into the package remains outstanding.

### 🐛 Fixed

- **Misleading badges removed** — the MseeP security-assessment badge and the `contrib.rocks`
  contributor image both described upstream's repository, not this one.

---

```

- [ ] **Step 2: Verify the file structure is intact**

```bash
head -45 CHANGELOG.md && grep -c "^## \[Unreleased\]" CHANGELOG.md
```

Expected: the new entry appears first, the previous `[Unreleased] - 2026-05-12` entry is intact below it, and the count is `3`.

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "$(cat <<'EOF'
docs: record Codeberg migration in CHANGELOG

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Local branch reshuffle

`enhanced` holds all the work; local `main` is a stale copy of upstream's fork point. Rename so the project's default branch has a name that makes sense for an independent project.

**Files:** none — git refs only.

**Interfaces:**
- Consumes: nothing
- Produces: local branch `main` at the tip of the former `enhanced`

- [ ] **Step 1: Record the current tip for rollback**

```bash
git rev-parse enhanced | tee /tmp/enhanced-tip.txt
git status --porcelain
```

Expected: a 40-character SHA, and **empty** `git status` output. **If `git status` is not empty, stop** — commit or stash first.

- [ ] **Step 2: Confirm nothing unique is lost**

```bash
git log --oneline main ^enhanced
```

Expected: **no output** — every commit on stale `main` is already contained in `enhanced`. If any commit is listed, stop and report it.

- [ ] **Step 3: Delete the stale local main and rename**

```bash
git branch -D main
git branch -m enhanced main
git branch -vv
```

Expected: `main` is listed at the SHA from Step 1, and `enhanced` no longer exists.

- [ ] **Step 4: Verify history depth and upstream ancestry**

```bash
git merge-base --is-ancestor upstream/main main && echo "upstream ancestry intact"
git log --oneline | wc -l
```

Expected: `upstream ancestry intact`, and a commit count well over 100 (full history preserved, not squashed).

- [ ] **Step 5: Leave the leftover integration branches in place locally**

```bash
git branch --list 'pr-*' integrated
```

Expected: `pr-25`, `pr-38`, `pr-39`, `integrated` all still listed.

Spec §7 drops these from the *published* repository, which Task 9 achieves by pushing only
`main`. **Do not delete them locally.** `pr-38` (RPC response envelope standardisation) and
`pr-39` (GUI startup defaults) contain work that was never merged into `main`, and deleting
the branches would be the only way to lose it. They stay as local-only refs until the
maintainer decides their fate — a separate decision, out of scope here.

---

### Task 9: Create the Codeberg repository and push

**Files:** none — remote configuration only.

**Interfaces:**
- Consumes: local branch `main` from Task 8
- Produces: remote `codeberg` and the published repository

- [ ] **Step 1: Confirm API access**

```bash
curl -s -H "Authorization: token $CODEBERG_RW_TOKEN" \
  https://codeberg.org/api/v1/user | python3 -c "import json,sys; print(json.load(sys.stdin)['login'])"
```

Expected: `wibbit`. **Never echo the token itself.**

- [ ] **Step 2: Create the repository**

```bash
curl -s -X POST -H "Authorization: token $CODEBERG_RW_TOKEN" \
  -H "Content-Type: application/json" \
  https://codeberg.org/api/v1/user/repos \
  -d '{
    "name": "freecad-mcp",
    "description": "FreeCAD MCP server for driving FreeCAD from MCP clients. Based on neka-nat/freecad-mcp.",
    "private": false,
    "auto_init": false,
    "default_branch": "main"
  }' | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('full_name'), d.get('html_url'))"
```

Expected: `wibbit/freecad-mcp https://codeberg.org/wibbit/freecad-mcp`

`auto_init` is false so the push is not blocked by a conflicting initial commit.

- [ ] **Step 3: Add the remote and push**

```bash
git remote add codeberg git@codeberg.org:wibbit/freecad-mcp.git
git push -u codeberg main
```

Expected: push succeeds and `main` tracks `codeberg/main`. SSH is used to match the maintainer's other Codeberg repos (Grimoire, Golem).

- [ ] **Step 4: Verify the published state**

```bash
git ls-remote --heads codeberg
curl -s https://codeberg.org/api/v1/repos/wibbit/freecad-mcp | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print('default:', d['default_branch'], '| private:', d['private'])"
```

Expected: exactly one head, `refs/heads/main`; `default: main | private: False`.

- [ ] **Step 5: Verify attribution survived the push**

```bash
git show codeberg/main:LICENSE | head -5
```

Expected: both copyright lines present, original first.

---

### Task 10: File the vision-proxy integration issue

**Files:** none — Codeberg issue only.

**Interfaces:**
- Consumes: the repository from Task 9
- Produces: nothing

- [ ] **Step 1: Create the issue**

```bash
curl -s -X POST -H "Authorization: token $CODEBERG_RW_TOKEN" \
  -H "Content-Type: application/json" \
  https://codeberg.org/api/v1/repos/wibbit/freecad-mcp/issues \
  -d '{
    "title": "Integrate the vision proxy into the package",
    "body": "`freecad-mcp-proxy.py` is tracked but not integrated. It is an MCP stdio proxy that intercepts base64 viewport screenshots, sends them to a local Ollama vision model, and replaces the image blob with a short text description — saving roughly 2,000-5,000 tokens per `execute_code` or `get_view` call.\n\n## Tasks\n\n- [ ] Move to `src/freecad_mcp/vision_proxy.py` with a `freecad-mcp-proxy` console entry point in `pyproject.toml`.\n- [ ] Replace hardcoded configuration with env vars and/or a config file: Ollama base URL, vision model, default prompt, upstream command, and an on/off switch.\n- [ ] Remove the project-specific default vision prompt.\n- [ ] Preserve both per-call prompt mechanisms: the `# __vision__: <prompt>` comment for `execute_code`, and `focus_object=\"Name|<prompt>\"` for `get_view`.\n- [ ] Update `docs/`, tests and `CHANGELOG.md` in the same commit, per `CLAUDE.md`.\n\nSee `freecad-mcp-proxy.TODO.md` for the full write-up. Option (a) (packaged proxy) is recommended over folding it into the server.",
    "labels": []
  }' | python3 -c "import json,sys; d=json.load(sys.stdin); print('issue #%s: %s' % (d['number'], d['html_url']))"
```

Expected: `issue #1: https://codeberg.org/wibbit/freecad-mcp/issues/1`

- [ ] **Step 2: Verify**

```bash
curl -s https://codeberg.org/api/v1/repos/wibbit/freecad-mcp/issues | \
  python3 -c "import json,sys; [print(i['number'], i['title']) for i in json.load(sys.stdin)]"
```

Expected: one open issue, "Integrate the vision proxy into the package".

---

### Task 11: GitHub mirror — GATED, DESTRUCTIVE

> **STOP.** Do not begin this task without fresh, explicit approval from the maintainer at
> this point in execution. The force-push overwrites 84 commits on GitHub's `main` and
> **cannot be undone** through the GitHub UI. Approval given for Tasks 1-10 does **not**
> carry over. Present the impact, then wait.

GitHub's `main` holds a rewritten-history duplicate of upstream that is not an ancestor of the new `main`, so no fast-forward path exists.

**Files:** none — remote configuration only.

**Interfaces:**
- Consumes: local `main` from Task 8
- Produces: nothing

- [ ] **Step 1: Capture a rollback ref before doing anything**

```bash
git fetch origin
git branch github-main-backup origin/main
git rev-parse github-main-backup
```

Expected: a SHA (`5533a60…`). This local branch is the only remaining copy of GitHub's old lineage after the force-push — **do not delete it.**

- [ ] **Step 2: Present the impact and obtain explicit approval**

State plainly to the maintainer:

- 84 commits on GitHub's `main` will be overwritten and are recoverable only from the local `github-main-backup` branch.
- The old lineage is a rewritten duplicate of upstream with no unique content (verified: tree identical to `upstream/main`).
- Issues and pull requests on GitHub will be disabled.

**Wait for an explicit yes.** Do not proceed on inference.

- [ ] **Step 3: Force-push the new history**

```bash
git push --force-with-lease origin main
```

`--force-with-lease` rather than `--force`: it aborts if the remote moved since the Step 1 fetch, preventing loss of anything pushed in the interim.

- [ ] **Step 4: Remove the now-redundant remote `enhanced` branch**

A mirror should carry only `main`. `origin/enhanced` is the pre-rename copy of the same
lineage and is now fully contained in `origin/main`.

```bash
git ls-remote --heads origin
git push origin --delete enhanced
git ls-remote --heads origin
```

Expected: `refs/heads/enhanced` present before, absent after, leaving only `refs/heads/main`.
This is safe — Step 3 already pushed a superset of its content — but it is still a remote
deletion, so it belongs inside this gated task.

- [ ] **Step 5: Disable issues and pull requests, and repoint the description**

```bash
gh repo edit wibbit/freecad-mcp \
  --description "Mirror of codeberg.org/wibbit/freecad-mcp — issues and PRs are on Codeberg" \
  --homepage "https://codeberg.org/wibbit/freecad-mcp" \
  --enable-issues=false \
  --enable-wiki=false
```

- [ ] **Step 6: Verify the mirror**

```bash
gh repo view wibbit/freecad-mcp --json description,homepageUrl,hasIssuesEnabled,defaultBranchRef \
  | python3 -m json.tool
git ls-remote --heads origin main
```

Expected: `hasIssuesEnabled: false`, homepage set to the Codeberg URL, and `origin/main` at the same SHA as `codeberg/main`.

- [ ] **Step 7: Confirm both remotes agree**

```bash
[ "$(git rev-parse codeberg/main)" = "$(git rev-parse origin/main)" ] \
  && echo "mirrors in sync" || echo "MISMATCH — investigate"
```

Expected: `mirrors in sync`.

---

## Post-migration verification

- [ ] **Full metadata suite passes**

```bash
./check tests/test_project_metadata.py -v
```

Expected: 33 passed.

- [ ] **The live setup still works.** In FreeCAD, start the RPC server, then in a fresh Claude Code session call `get_freecad_status`. Expected: a successful response. This exercises `~/.claude.json` → proxy → `uv --directory ~/git/freecad-mcp` → server → addon symlink, the whole chain the migration deliberately left untouched.

- [ ] **No stale upstream references remain**

```bash
grep -rn "neka-nat" --include="*.md" --include="*.toml" --include="*.py" . \
  | grep -v '.venv/' | grep -v 'docs/superpowers/'
```

Expected: only lines that credit upstream as the *origin* (README Origins section, contributors list, `pyproject.toml` description, CHANGELOG). No line should present upstream as the project's current home, issue tracker, or clone source.
