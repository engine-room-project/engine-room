# Coding-tool configuration and validation status

Engine Room prepares settings for a newly launched tool process. It does not edit
normal OpenCode JSON/JSONC, Codex configuration/profile files, stored accounts,
permissions, integrations or the normal model choice. It does not read another tool's
authentication files. Existing process-environment settings are copied for the child;
the parent environment is never temporarily changed.

## Implemented local paths

- OpenCode: merge a unique provider and selected model into the child's inline config,
  preserving unrelated inline settings and providers. Existing custom-file/directory
  environment settings remain in place. The new provider references a unique environment
  variable for the session key; the key is not placed in arguments or inline JSON.
- Codex CLI: use per-run model/provider/context overrides and a unique environment-key
  reference. Keep CODEX_HOME and normal configuration unchanged. Effort is overridden
  only when explicitly selected and supported by model metadata. It requires a compatible
  Responses API; a successful model-list response is insufficient proof.
- Discovery: inspect conventional Windows locations or command paths without executing
  candidate files or scanning a drive. Detection never reports a completed registration.
  Native executable launch is implemented. Script launchers are detected with an explicit
  limitation, not silently executed. An executable can also be selected explicitly.

All tool/model/engine combinations currently carry experimental warnings. Tool-call
support and requested effort derive from checked model metadata, not from a claim that
a live coding task passed. OpenCode's output allowance uses the selected conversation
capacity; no arbitrary 32,768-token thinking limit is introduced.

A single-instance OpenCode desktop application must be closed before it is opened with
new settings. Engine Room must check that condition and explain it, never terminate an
existing editor or assume a second process receives new environment settings. That
check still needs wiring into the Windows interface. Other detected tools, including
Claude Code and ComfyUI, are not marked automatically registered; their protocols and
end-to-end combinations remain explicit validation work.

## Preservation and removal

No Engine Room settings file is written inside a tool's normal configuration directory.
There is therefore no normal configuration edit to undo. Stop/revoke the session and
close its loopback endpoint. A launched editor may remain open with an expired local
connection; never kill it or remove its history/work to clean up Engine Room. The tool
may maintain its own normal UI/history state when used; that is not Engine Room-owned
configuration and must not be deleted.

Malformed existing inline settings fail with a plain message and remain unchanged.
Existing project/admin/provider restrictions can still override or forbid a custom
connection. Do not disable them or silently choose another account/provider. Actual
compatibility/preflight must detect this before a paid session is offered as ready.

## Evidence and remaining acceptance

Synthetic tests prove unchanged normal-file bytes, preservation of unrelated providers,
preferences and integrations, strict malformed-settings refusal, TOML parsing of Codex
overrides and absence of the session key from command arguments/config content. An
actual synthetic child process receives the overlay while the parent environment and
project config remain unchanged. Read-only discovery accepts harmless fake executable
files without executing them; PowerShell 7 and Windows PowerShell 5.1 pass.

These tests do not run a real coding conversation. Live release acceptance still needs
explicit supported tool versions and package/SDK resolution, actual model tool calls,
Responses compatibility for Codex, desktop single-instance behavior, project/admin
settings, script-launcher disposition and WPF event wiring. OpenCode's custom provider
SDK reference is not yet pinned/validated as a release dependency; R9 stays open. Do not
advertise a tool combination as supported solely from these tests.

## Official references inspected

The [OpenAI advanced configuration documentation](https://learn.chatgpt.com/docs/config-file/config-advanced)
describes per-run overrides, provider environment-key references and separate profile
files. The existing development profile format is valid; this release path uses
per-run settings to avoid creating or replacing that file.

The [OpenCode configuration documentation](https://opencode.ai/docs/config/) describes
inline configuration, merge precedence and environment substitutions. Those documented
interfaces still require acceptance against the exact selected tool version.
