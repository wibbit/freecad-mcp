# Design: Migrate to Codeberg and establish independent project identity

**Date:** 2026-08-02
**Status:** Approved for planning

## Problem

This repository is a fork of [`neka-nat/freecad-mcp`](https://github.com/neka-nat/freecad-mcp),
currently hosted at `github.com/wibbit/freecad-mcp`. It has diverged substantially —
56 commits and roughly 17,900 added lines beyond the fork point (`3f7d867`, 2026-05-08) —
and now constitutes a distinct project rather than a set of patches awaiting upstreaming.

Three problems follow from that:

1. **Hosting.** The project should live on Codeberg, alongside the maintainer's other
   projects (Grimoire, Golem).
2. **Misattribution in both directions.** `pyproject.toml` still names `k-tanaka` as author
   and points all five `[project.urls]` at upstream's GitHub repo. Meanwhile the original
   creator receives no visible credit in the README beyond incidental badge URLs.
3. **Stale framing.** Documentation describes the project as controlled "from Claude Desktop",
   which is inaccurate — it is driven from the Claude Code CLI in practice — and the README
   documents no feature set, so the project's actual scope is invisible to a new reader.

## Licence position

The project is MIT, copyright *Shirokuma (k tanaka)*.

MIT imposes exactly one obligation: the copyright notice and permission notice must be
retained in all copies or substantial portions. Retaining `LICENSE` with the original
copyright line intact satisfies this in full.

MIT draws no distinction between commercial and non-commercial use, so the maintainer's
intent not to monetise neither adds nor removes obligations. The retention requirement
triggers on *distribution* — publishing to a public Codeberg repository is distribution,
and the requirement applies exactly as it would to a paid product.

MIT does **not** require open-sourcing changes, contributing upstream, seeking permission,
marking modified files, or preserving the project name. Forking, renaming, restructuring
and rehosting are all permitted.

**Decision: remain MIT throughout.** A single `LICENSE` file carries two copyright lines —
the original, preserved verbatim, and the maintainer's. Copyleft for new contributions was
considered and rejected: it adds adoption friction and file-header complexity for no benefit
the maintainer is seeking.

## Decisions

### 1. Name: `freecad-mcp` (unchanged)

Canonical location becomes `codeberg.org/wibbit/freecad-mcp`, created as a **public**
repository.

Alternatives considered and rejected:

- **`Armature`** — fits the maintainer's Golem/Grimoire naming style, but collides with
  Blender's rigging terminology and is undiscoverable for anyone searching for a FreeCAD
  MCP server.
- **`freecad-mcp-workbench`** — rejected because "workbench" is precise FreeCAD vocabulary
  (Sketcher, Part Design, FEM are workbenches). The name would imply either an addon
  providing a workbench, or support limited to a single workbench. Both are wrong.

Keeping the upstream name means project distinctness is signalled by namespace
(`wibbit/` vs `neka-nat/`) plus README and metadata framing, not by the name itself.

### 2. Rename depth: repository and metadata only

Changed: `pyproject.toml` (name, description, authors, URLs), `README.md`, `docs/`.

**Unchanged:** the Python module `freecad_mcp`, the console script `freecad-mcp`, and the
FreeCAD addon directory `FreeCADMCP`.

Because the local checkout is already at `~/git/freecad-mcp`, no directory rename is needed.
Consequently `~/.claude.json`, the proxy's internal `uv --directory` path, and `CLAUDE.md`
all remain valid. **This migration breaks nothing in the live setup.**

### 3. Attribution

- **`LICENSE`** — the original copyright line is preserved verbatim and never reworded.
  A second copyright line is added for the maintainer, defaulting to the git-configured
  identity: `Copyright (c) 2026 wibbit`. See Open questions.
- **README "Origins" section** — credits Shirokuma (k tanaka) by name, links upstream, and
  states plainly that the project began as a fork and has since diverged.
- **`pyproject.toml`** — maintainer listed as author; upstream credited in the description.
- **Fork contributors** — Martin Bruno (7 commits) and MichaelZag (2 commits) credited.
  They contributed to this fork, not upstream, so upstream's contributor list does not
  cover them.

**Removals:**

- The MseeP security-assessment badge (`README.md:1`) — it assesses upstream's repository.
  Retaining it on a different repository misrepresents the assessment's subject.
- The `contrib.rocks` contributor image (`README.md:193-194`) — it renders *upstream's*
  contributor list.

### 4. Description wording: descriptive, never comparative

`pyproject.toml` description becomes:

> `FreeCAD MCP server for driving FreeCAD from MCP clients. Based on neka-nat/freecad-mcp.`

Comparative claims ("expanded assembly and FEM tooling", "more complete than upstream") are
**prohibited** in project metadata and the README tagline. Upstream may add equivalent
features at any time, silently falsifying such claims. Statements of what this project *is*
remain true regardless of upstream's roadmap; statements of how it *compares* do not.

The README feature list is not a comparative claim — it describes this codebase's surface
and stays accurate independently of upstream.

### 5. Client neutrality

The project is driven from the Claude Code CLI, not Claude Desktop. 24 references across
6 files need one of three treatments:

| Treatment | Applies to | Action |
|---|---|---|
| Make client-neutral | Generic prose implying Desktop-only: `README.md:5`, `pyproject.toml:4`, `docs/USER_GUIDE.md:3,19,34,52,54,65,67`, `docs/QUICKSTART.md:9,112` | Refer to "MCP clients" |
| Keep, and supplement | Genuinely Desktop-specific setup: `docs/QUICKSTART.md:60,66,71,76,106,108,179`, `docs/USER_GUIDE.md:493,494,496`, `README.md:79,83` | Retain as a "Claude Desktop" section — correct for Desktop users — and **add a Claude Code (CLI) section** covering `claude mcp add` / `~/.claude.json`, currently absent |
| Extend list | Already neutral: `docs/session_guide.md:136`, `src/freecad_mcp/server.py:3069` | Add Claude Code to the enumerated clients |

A blanket find-and-replace is explicitly wrong here: the `claude_desktop_config.json` paths
are accurate for Desktop users and must not be deleted.

### 6. README feature list

The README currently documents no feature set. Add a Features section grouped by capability.
The surface is 79 tools and 7 guided workflow prompts, grouped as:

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
| Escape hatch | `execute_code` for uncovered operations |
| Guided prompts | session startup, sketching, booleans, assembly, primitives, FEM |

**Hard tool counts are omitted from the README.** A "79 tools" figure goes stale on every
addition; category descriptions do not.

### 7. Branch layout

`enhanced` becomes `main` on Codeberg, carrying **full history** back through upstream's
genuine commits. History is deliberately not squashed — the commit log is the strongest
attribution artefact the project has.

Dropped:

- **`origin/main` (GitHub)** — a rewritten-history duplicate of upstream. Its tree is
  byte-identical to `upstream/main` (`51ef66d…`) with identical author and dates, but
  different commit SHAs; it diverges from `enhanced` at `3e52043` (2025-03-17), 84 commits
  versus 140. It is a parallel dead lineage, not a branch to reconcile.
- **`pr-25`, `pr-38`, `pr-39`, `integrated`** — leftover integration branches.

`enhanced` sits on genuine upstream commits (`upstream/main` is a clean ancestor,
56 ahead / 0 behind), which is what makes it the correct lineage to carry forward.

### 8. GitHub disposition: push mirror

`github.com/wibbit/freecad-mcp` remains active as a **push mirror only**:

- Issues and pull requests disabled.
- README banner directing issues and contributions to Codeberg.
- One issue tracker (Codeberg), two hosting locations.

**This requires a force-push.** GitHub's `main` holds the rewritten 84-commit lineage,
which is not an ancestor of the new `main`, so no fast-forward path exists. This is an
outward-facing, destructive, non-reversible operation and **requires separate explicit
approval at the point of execution.** It must not be bundled into an earlier step.

### 9. Vision proxy

`freecad-mcp-proxy.py` and `freecad-mcp-proxy.TODO.md` are committed **unchanged**. The proxy
is the live MCP entry point (`~/.claude.json` → `freecad` server), so leaving it untracked
would mean the live setup depends on a file existing nowhere but one machine.

Integration is explicitly **out of scope** for this migration. A Codeberg issue is filed
covering the TODO's recommended option (a): move to `src/freecad_mcp/vision_proxy.py` with a
console entry point, and replace the hardcoded Ollama base URL, model, and default vision
prompt with configuration.

### 10. Incidental correction

README install paths list Ubuntu, Debian, Arch and Snap, but the maintainer runs the
**flatpak** build (`~/.var/app/org.freecad.FreeCAD/`). That path is missing and is added.

## Order of operations

Content changes land before publication, so the repository's first public state is already
correctly branded and attributed.

| # | Step | Reversible |
|---|---|---|
| 1 | Commit proxy files as-is | Yes |
| 2 | Rebrand edits: `LICENSE`, `pyproject.toml`, `README.md`, `docs/`, `CHANGELOG.md` | Yes |
| 3 | Local branch reshuffle: delete stale `main`, rename `enhanced` → `main` | Yes |
| 4 | Create Codeberg repo, push `main`, set default branch | Yes |
| 5 | File the proxy-integration issue on Codeberg | Yes |
| 6 | **Gate on explicit approval** → GitHub mirror force-push, disable issues/PRs, add banner | **No** |

Steps 1–5 are safe. Step 6 is the only destructive operation and is gated.

## Repository conventions

Per `CLAUDE.md`, every change carries its documentation and test updates in the same commit:

- A `[Unreleased]` entry in `CHANGELOG.md` covering the migration and rebrand.
- Documentation updates land with the code change, not afterwards.
- Fixed bugs are not added to `tests/INTEGRATION_TEST_PLAN.md` Known Bugs (open issues only).

No test changes are anticipated: this migration alters metadata, documentation and hosting,
and does not touch the module, entry point, addon, or any tool implementation.

## Open questions

1. **Copyright attribution name.** The `LICENSE` addition defaults to `wibbit`, matching the
   git-configured `user.name`. A legal name (Douglas Furlong) would also be valid and is
   arguably more conventional for a copyright notice. Either works; this is a personal
   identity choice, not a technical one, and is confirmed before `LICENSE` is edited.

## Success criteria

1. `codeberg.org/wibbit/freecad-mcp` exists with `main` as default, carrying full history
   back through upstream's genuine commits.
2. `LICENSE` retains the original copyright verbatim and adds the maintainer's.
3. No file references `neka-nat` as the current home; upstream is referenced only as origin.
4. No comparative claim about upstream appears in metadata or README.
5. README documents the feature set and both Claude Desktop and Claude Code CLI setup.
6. The live setup (`~/.claude.json` → proxy → server) continues working untouched.
7. A Codeberg issue exists for vision-proxy integration.
8. GitHub carries a mirror with issues disabled and a pointer to Codeberg.
