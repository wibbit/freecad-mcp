# TODO (for a future agent): genericise the vision proxy and fold it into freecad-mcp

`freecad-mcp-proxy.py` was moved here from `~/git/` on 2026-06-15. It is **not yet
integrated** — it is the original standalone proxy, dropped in as-is for rework.

## What it is
An MCP **stdio proxy** that sits between the editor (Claude Code / OpenCode) and the
real `freecad-mcp` server. It spawns the upstream server (`uv --directory
~/git/freecad-mcp run freecad-mcp`), watches tool responses for **base64 viewport
screenshots**, sends each to a local **Ollama `llava:7b`**, and **replaces the image
blob with a short text description**. Net effect: ~2,000–5,000 fewer tokens per
`execute_code` / `get_view` call.

Per-call vision prompts it currently supports (preserve these):
- `execute_code`: a `# __vision__: <prompt>` comment at the top of the code block.
- `get_view`: `focus_object="Name|<prompt>"` (text after `|` becomes the prompt).

## The task
1. **Make it generic.** Remove the hard-coded parasol-holder `DEFAULT_VISION_PROMPT`
   and make these configurable (env vars and/or a config file): Ollama base URL,
   vision model, default prompt, the upstream command, and an on/off switch.
2. **Fold it into the package.** Decide and implement one of:
   - **(a) Packaged proxy** — move into `src/freecad_mcp/vision_proxy.py` with a
     console entry point (e.g. `freecad-mcp-proxy`) in `pyproject.toml`. Lowest risk;
     keeps the "intercept any image in any response" generality.
   - **(b) Integrated into the server** — make the summarisation an optional,
     config-gated post-processing step inside the server itself, so no separate proxy
     process is needed. Cleaner topology; bigger change to the working server.
   Recommend (a) unless there's a reason to merge into the server.
3. **Update docs + tests + CHANGELOG** in the same commit (see this repo's `CLAUDE.md`
   "update docs and tests alongside every change" rule). Add the entry point to
   `docs/API_REFERENCE.md` and a `[Unreleased]` CHANGELOG note.

## Heads-up: the editor registration points at this file
`~/.claude.json` (mcpServers → `freecad`) currently runs
`python3 /home/dfurlong/git/freecad-mcp/freecad-mcp-proxy.py`. (It was repointed from
the old `~/git/freecad-mcp-proxy.py` location when the file was moved.) When you fold
this into the package / add a console entry point, update that registration — and the
OpenCode ones if relevant.

## Dependencies / context
- Needs a local **Ollama** with a vision model (currently `llava:7b`).
- Logs to `/tmp/freecad-mcp-proxy.log`.
- This file and `freecad-mcp-proxy.py` are **tracked** in git — they were committed
  during the Codeberg migration. Do the rework on a working branch.
- The script as committed is maintainer-specific: `freecad-mcp-proxy.py` hardcodes the
  absolute path `/home/dfurlong/git/freecad-mcp` (in `UPSTREAM_CMD` and in the usage
  docstring), so it cannot run for anyone else — genericising those paths is a
  prerequisite of the integration work in step 1 above.
