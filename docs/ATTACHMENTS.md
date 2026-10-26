# Existing-machine access candidate

Existing-machine connections use a separate lifecycle from managed rentals. The current
SSH connector is offered as an optional experimental existing-machine connector. The
Windows connection, confirmation, coding-tool and recovery flows have automated evidence;
independent live acceptance remains a release gate.

An attachment selects an already served model. Engine Room does not install software,
start or stop that model, rent the machine, terminate it, or manage its external billing.
Disconnect closes only Engine Room access. Existing compute and storage costs continue
under the original service or machine owner.

The enrolled controller saves the original connection, selected model and operation
before starting a forward. The controller compares the reviewed account, resource and
model preview again at startup, refusing a changed target. Lost replies never replay connection startup. Cancelling a
pending operation saves a denial before waiting for startup to settle; a late request
cannot reopen it. Explicit desktop access pulses keep access alive through the persistent session helper.
The SSH helper independently closes its owned forward after parent loss or pulse expiry.

For coding tools, enter a conversation limit from the existing model server settings.
No value is preselected. This is a user-declared tool limit, not a probe of the server's
capacity. Engine, reasoning, vision and tool-call capabilities are not inferred. OpenCode
and Codex handoff remain experimental; Codex needs a compatible Responses API. Only the
selected new process receives the session connection; normal tool settings are preserved.
An access session is bounded to one day and requires continued window pulses.

The controller rechecks the original connection and selected model before model access.
Its stream bridge checks one bounded JSON inference request against that exact model,
then forwards only the checked request. Additional pipelined requests are discarded.
No client authorization headers are forwarded to the existing model service.

Recovery uses the original local operation evidence. A rotated key does not prevent
closing a retained local forward. Restart never adopts a PID, reconnects a machine or
replays startup. Confirmed local closure records `detached`; uncertain closure remains
`unresolved`. Neither state asserts that the existing machine is off. Keep original
records when evidence is damaged or incomplete. The desktop recovery index identifies
rental and attachment records separately; an attachment recovery action cannot invoke
rental cancellation. Local saved records are history until checked with the controller.

Connector implementations advertising attachment mode provide `attachment_target`,
`attach`, `pulse`, `model_endpoint` and `disconnect`, in addition to the base contract.
`attachment_target` returns explicit account, resource and served-model identifiers.
The core contains no provider-name branches. Connector code is trusted installed code;
configuration cannot name executable plugin paths.

Current evidence is automated and synthetic: durable state/replay tests, cancellation
races, credential-rotation recovery, scoped RPC and Linux helper/stream tests. This does
not establish live SSH authentication, independent-account installation or billing
acceptance, and does not close the public-release validation gates.
