# Private controller deployment proposal

These files are reviewable templates, not an installed service. Deployment, the host
and credential setup require owner approval. Do not run these steps on shared
infrastructure by assumption. No provider or model credential is included here.

## Required host and account

Use an independently powered, available Linux host, Python 3.12, OpenSSH client/server,
and a dedicated non-root account. The controller needs outbound HTTPS for the selected
providers/model metadata and SSH to its owned rental. Desktop SSH ingress must be private
network only. Do not change existing routes, public ingress or another application's keys.
The controller Python code uses the standard library; remote model dependencies are separate.

Place the inspected source at the account's `~/engine-room`, with owner-controlled code
and no writable source for unrelated users. Use owner-only state at
`~/.local/share/engine-room-controller`. The socket path must fit Linux's Unix socket
limit; choose a shorter state path and consistently adjust templates if needed.

A later approved installation must:

1. Record the desktop's one-way host identity using `engine_room.protection.host_identity`.
   On the host, run the `enroll` command with explicit controller ID, client host ID and
   `--confirm-independent-host`. Confirm physical/power independence separately. Enrollment
   refuses replacement; do not discard it while recovery records remain.
2. Save provider credentials directly in an interactive controller terminal with
   `python3 -m engine_room.controller_service credential --root <private-state> --reference <chosen-reference>`.
   Input is hidden; never put credentials in command arguments, environment, RPC or logs.
   Explicit replacement uses `--replace`. This does not migrate credentials from the desktop.
   Colab uses its separate explicit interactive PKCE command in docs/COLAB_CONNECTOR.md; real consent remains unvalidated.
3. Verify the host's Ed25519 public host key through its trusted console/admin channel.
   An unauthenticated `ssh-keyscan` result alone is not verification. Configure the desktop
   with that exact public key, private IP, dedicated account and dedicated client identity.
   No existing SSH or coding-tool configuration is edited by the client.
4. Install `engine-room-controller-rpc.sh` as the fixed command
   `engine-room-controller-rpc` with executable permissions. It assumes the source/state
   locations above. The dedicated desktop public key must have an `authorized_keys` entry
   with `restrict,command="<absolute-installed-wrapper>"` before the key. This forbids
   interactive shells, agent/X11/port forwarding and PTYs for that key. The wrapper also
   rejects a different original SSH command. Keep administrative access separate.
5. Review/install the user service template as `engine-room-controller.service`. Create
   state before starting it. The deployment must explicitly enable persistent user-service
   execution across logout (systemd lingering, requiring administrator approval), or prepare
   a reviewed equivalent system service under the same dedicated user. The template alone
   does not enable lingering. Unsupported sandbox settings must fail setup, not be silently
   removed. Restart-on-failure handles crashes; intentional service stop does not guarantee
   that a provider accepted cleanup.
6. Verify actual forced-command SSH, host-key mismatch refusal, permission isolation,
   startup/reboot/logout survival, crash recovery and private ingress before permitting
   any paid test. Model traffic forwarding and desktop heartbeat integration now have
   synthetic tests; the actual deployed combination remains unvalidated.

`serve` owns the controller process lock before binding the socket. `rpc` bridges one
bounded message to that socket. Neither installs software, changes SSH settings or starts
systemd. No source command automatically grants access or deploys the templates.

## State and removal

Protect the entire state directory, including enrollment, named connections, credential
references/files, receipts and generated per-rental SSH material. The latter is removed
only after provider-confirmed absence. Backups contain secrets and need the same boundary.
Never publish or package state. The socket itself is transient.

First stop/recover each rental and independently confirm provider absence; preserve any
uncertain receipt. Existing provider storage is separately billed and is not deleted by
removing a connection or this service. Revoke the dedicated SSH key and provider credentials
explicitly, then disable/remove the service/wrapper and remove state only when recovery is
complete. Do not stop a shared SSH server or edit other authorized keys. Final end-user
installation/update/removal documentation remains a release gate.


SSH configuration references: the [OpenSSH client manual](https://man.openbsd.org/ssh_config)
describes explicit known-hosts files, host-key checks and host-key updates. The
[OpenSSH server manual](https://man.openbsd.org/sshd#AUTHORIZED_KEYS_FILE_FORMAT)
describes forced commands and the `restrict` authorized-key option. Both client
host-key databases are explicitly limited to Engine Room's pinned file. Deployment
must verify these restrictions on the actual installed OpenSSH version.
