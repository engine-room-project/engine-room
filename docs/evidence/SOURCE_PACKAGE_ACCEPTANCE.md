# Source-package candidate acceptance

This records automated and same-machine installation evidence only. It does not establish
independent-account onboarding, real provider/GPU behavior, controller deployment or billing.
Neither candidate is a published release. Required owner licence/governance/publication
and full release gates remain open.

## Candidate 1

Source commit: b043207a6f3a11cc5657165106ec681d59abedeb.
Archive SHA-256: 60f6dc62f147fcbbd7fa657c4876bb87d4b7d6cc41c1ee6dc91ef3a33cb3f862.
167 source files plus SOURCE_MANIFEST.json. Verified ZIP inventory/CRC, every manifest file
hash/byte count and required third-party notices. Known personal-identifier/private-network
scan found no matches; Gitleaks found no secrets in 1.61 MB. This is evidence for those
scans and selected bytes, not proof of all possible private information or history safety.

Extracted into a new directory. A new Windows Python environment without pip/optional
packages ran all 518 tests:434 passed,84 skipped. Packaged Windows model planning:17 checks
passed. First startup with a new state path reported no provider and created no state.
An initial tool-sandbox run failed with temporary-directory ACL errors; a separate run with
required filesystem permission passed. Execution policy was not disabled.

## Candidate 2 with installer

Source commit: b7b113ff5caf1b82914b334db4a87d4b874b4020.
Archive SHA-256: d4b0825d9a3808ae036798cf8680f79a8f1df63e4226274fb4bb8478ba3afcad.
170 source files plus manifest. Exact inventory/CRC, all file hashes, known-identifier scan
and third-party notices verified. Gitleaks found no secrets in 1.63 MB.

From the extracted candidate, Install-EngineRoom.ps1 ran with a fresh Python environment,
a new destination containing a space and a temporary shortcut directory. It installed the
manifest files and created a revision-specific shortcut. The actual installed source then
ran 525 Windows tests:439 passed,86 platform/optional skips. Packaged planning:17 checks
passed. Empty startup reported no provider and created no state; the native installed
first-launch screen was rendered and inspected. Native tests verify shortcut target,
arguments, working directory, no overwrite and separate recovery state preservation.

The isolated Linux full suite on that actual installed package passed525 tests:
518 passed,7 Windows-only skips. Its optional Colab dependency environment was isolated
from ambient Google/Cloud configuration; no provider authentication occurred.
No real account, credentials, paid resource or shared infrastructure was configured.
The Windows account/OS was the development account, not an independent user account.
No source has been pushed; unpublished development history still needs separate sanitation.

## Candidate 3 after independent-review corrections

Source commit:97606be93f85a71e1f4e7bd714371d8b993b6804.
Archive SHA-256:52179cc534209135a51eb5709c9857bb8ce04ee63a65e5a0e06af29f5caf2370.
170 source files plus manifest. Verified exact inventory/CRC and every file hash/byte count;
known personal/private-network pattern scan found no matches. Gitleaks found no secrets
in1.63MB; required notices are present. The actual installer created a new spaced directory
and temporary shortcut using a fresh interpreter without pip. Empty first launch created no
provider state. Installed Windows530 tests:441 passed,89 skipped; installed Linux530 tests:
522 passed,8 skipped. Packaged planning17 checks passed. Separate exact Hub2.3 authentication
regressions passed8 tests. No real provider account or paid resource was used.

The same code state passed independent follow-up review; see INDEPENDENT_REVIEW.md.
This remains same-machine automated/package evidence, not independent user-account,
actual controller deployment, provider/GPU/tool-protocol or billing acceptance.

## Candidate 4 with owner-selected MIT

Source commit:80ea9de89e80b1a1394fc9ec11fda1c91073d046.
Archive SHA-256:f191cccc239729a602eec624f61119b0a9bd1a9f84622460e5caa50a2031f9e8.
171 source files plus manifest. Exact inventory, ZIP CRC, every file hash and byte count,
MIT licence and all four required upstream licence texts passed inspection. Known personal
and private-network patterns had no matches; Gitleaks scanned1.64MB and found no leaks.

The actual extracted installer created a new spaced destination and temporary shortcut
using a fresh Python environment without pip. The installed source passed531 Windows tests:
442 passed,89 skips, plus17 planning checks. In an empty Linux home with the isolated pinned
optional Colab dependencies, the installed source passed531 tests:523 passed,8 skips.
Empty Windows startup reported no provider/controller and created no runtime state.
The exact source code also passed independent follow-up review.

These are same-machine package and automated cross-platform checks. Independent Windows
account/OS onboarding, real provider/GPU/shutdown, tool-protocol and billing gates remain open.
No provider credentials, paid resources or finished release publication were used here.
