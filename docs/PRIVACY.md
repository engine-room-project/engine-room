# Privacy and credentials

A fresh desktop has no configured provider. Engine Room does not import an existing CLI,
ADC, browser, SSH-agent or coding-tool account automatically. Connections reference an
explicit credential saved on the independent controller. Real credential setup and any new
access boundary require approval. Never include credentials in a command line, source,
archive, issue, screenshot or diagnostic log.

Windows secret storage uses the current user's DPAPI; Linux credential files and controller
state require owner-only permissions. DPAPI is not a boundary against other software running
as that same user. Protect the controller, the desktop SSH identity, backups and account
access. The desktop retains enrollment, connection/account identifiers and operation records;
the controller retains credentials, original-scope journals and runtime access material.
Neither directory belongs in a source package.

Selected provider APIs receive the account-authorized resource requests. Hugging Face receives
model metadata/download requests; restricted access uses only the explicitly selected model
credential. Colab OAuth uses explicit narrow consent; see docs/COLAB_CONNECTOR.md. There is no
permission to broaden returned/requested scopes automatically. Optional dependencies may
contact their documented upstream endpoints during installation or operation.

Model prompts, code and responses travel through private authenticated access to the chosen
remote model. The provider and model runtime are separate trust boundaries; private transport
does not establish their retention policy. Review those terms before sending sensitive work.
A coding tool may have its own telemetry/network behavior. Experimental child overlays do not
change the tool's normal stored settings or grant authority to kill another session.

The application has no built-in central telemetry service. Local test output can contain
operation metadata. Share only inspected/redacted diagnostics. Account IDs and device-derived
enrollment hashes are runtime state, not public release examples. Provider confirmation and
billing evidence must be retained privately with credentials removed from public evidence.
