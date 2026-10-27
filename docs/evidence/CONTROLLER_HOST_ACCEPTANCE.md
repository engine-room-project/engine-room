# Credential-free independent-host acceptance

Scope: owner-approved initial deployment on an independently powered existing Linux host.
No real provider credentials, provider connections, rentals or persistent volumes were created.
This is infrastructure/transport evidence, not provider shutdown, GPU or billing acceptance.

Deployed source: inspected candidate3 at97606be93f85a71e1f4e7bd714371d8b993b6804.
Archive SHA-256:52179cc534209135a51eb5709c9857bb8ce04ee63a65e5a0e06af29f5caf2370.
The host verified the archive and every manifest file before installing the reviewed source.

The actual host has Linux, Python3.12, OpenSSH and systemd255. A dedicated non-root account,
root-owned read-only source and owner-only state were created without importing older runtime
state. A system service explicitly runs as that account with NoNewPrivileges, strict system
protection, read-only home and one writable state directory. Its private Unix socket is active;
no controller TCP listener exists. Both initial connector modules and optional SSH discover,
but no account is configured. Optional connector dependency/consent acceptance remains open.

Authenticated local and actual private SSH RPC returned healthy controller protection,
empty connections and empty storage records. A new dedicated desktop identity has owner-only
Windows ACLs. Its server key entry restricts access to the fixed reviewed controller command.
Host trust came from a separately authenticated administrator channel; no TOFU was used.

Actual negative checks refused arbitrary remote commands, direct TCP forwarding, incorrect
controller enrollment and a mismatched pinned host key. The original client remained healthy.
An initial forced-wrapper parent permission issue was resolved by selecting the reviewed
root-owned source wrapper, without broadening the parent directory permissions.

Only the new controller service was intentionally crashed. Its configured failure restart
created a new process and healthy private RPC returned afterward. Boot startup is enabled;
the shared host was not rebooted, so actual reboot survival is not claimed. Closing the
administrative session did not stop the independent system service.

Required shared-server routing validation passed before changes. Authoritative routing,
proxy and portal artifacts matched the private canonical repository before and after.
No shared application, proxy route, ingress, existing key or service was changed.
Private host addresses, account/device identifiers, SSH keys and raw logs remain outside
release source. Provider/account/GPU/tool-protocol, billing, independent Windows onboarding,
actual shared-host reboot and final owner gates remain open.
