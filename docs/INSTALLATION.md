# Install the source candidate

This is a source installation procedure for evaluation. Independent clean-package acceptance
is still required. Controller deployment and real credential setup require the owner's
explicit approval; no installation command below authorizes paid resources.

## Windows desktop

Use Windows 11, Windows PowerShell 5.1 with WPF, Python 3.12 or newer on PATH, and the
Windows OpenSSH Client. The core desktop uses the Python standard library. It does not
require Colab, WSL, provider login, a GPU, or coding-tool configuration on the desktop.

Verify the candidate archive and its SOURCE_MANIFEST.json against the separately supplied
reviewed digest. Extract to a new per-user directory. Preserve its relative files; do not
copy runtime state from an older project. Inspect EngineRoom.ps1 before running it:

```powershell
powershell.exe -NoProfile -STA -File .\EngineRoom.ps1
```

Run from the extracted engine-room-source directory. If Windows blocks downloaded scripts,
inspect the download and resolve the trust decision through normal Windows policy; do not
disable execution policy or organizational controls. If prerequisites are missing, install
them through their trusted vendor or Windows settings and reopen the window. No administrator
privilege is required to open the application. After inspecting and verifying the archive, run `powershell.exe -NoProfile -File .\Install-EngineRoom.ps1`
to install a verified copy into a new per-user version directory and create a revision-named
Desktop shortcut. It never overwrites an installation or shortcut. `-Destination` and
`-ShortcutDirectory` select explicit new source/shortcut locations; `-NoShortcut` installs
source only. The installer does not launch, authenticate, rent, migrate state or change policy.
A failed installation preserves any partial new directory for inspection. A manifest verifies
file integrity, not publisher identity; compare the independently supplied archive digest first.

First launch reports no provider. Configure a private, independently powered controller
before adding connections. Verify its SSH host key through a trusted separate channel.
Use a dedicated client SSH identity and confirm the exact controller enrollment IDs.
Never paste a provider secret into the connection-name or credential-reference fields.

## Independent Linux controller

The deployment proposal in controller/README.md describes a dedicated non-root account,
private SSH forced command, owner-only state, service hardening and logout/reboot survival.
Inspect and adapt the templates to the approved host before installation. Templates do not
deploy themselves. Verify the selected Python interpreter; the supplied service/wrapper
currently name /usr/bin/python3, so optional dependencies installed in a virtual environment
need an explicitly reviewed interpreter-path adjustment in both templates.

RunPod and the core use the standard library. Colab additionally needs the exact optional
Linux Python 3.12 dependency lock in controller/requirements.lock, installed into the
controller interpreter using pip --require-hashes. Never install desktop credentials,
ambient ADC or another application's login cache as a substitute. Colab's explicit
interactive PKCE command and its consent boundary are documented in docs/COLAB_CONNECTOR.md.
RunPod API credentials are entered with the controller's interactive credential command.
The model credential, when required, is a separate explicitly saved reference.

Before any rental, validate actual private SSH, enrollment, pinned keys, service health,
independent-host survival and provider recovery. The desktop refuses managed rental starts
without required controller protection. These checks still need live acceptance evidence.
