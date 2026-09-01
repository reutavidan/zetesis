# Security Policy

## Reporting a vulnerability

Report suspected vulnerabilities privately to **avidan.r@zetesis.science**. Please do not open a
public issue for a security report.

Include what you need to describe the problem: the endpoint or tool involved, what you observed,
and the steps to reproduce it. If a proof of concept is easier to show than to describe, send it
directly rather than posting it.

You can expect an acknowledgement, and we will tell you what we intend to do about the report and
when. If a fix ships, we will credit you unless you would rather we did not.

## Scope

In scope:

- The hosted MCP server at `https://api.zetesis.science/mcp`
- The HTTP API at `https://api.zetesis.science`
- This client package

Out of scope: the third-party registries Zetesis reads from (Europe PMC, ClinicalTrials.gov,
openFDA, NIH RePORTER, SEC EDGAR). Report issues in those to their own maintainers.

## What the service handles

The two evidence tools, `zetesis_scope` and `zetesis_evidence`, call no language model and send
nothing to any model provider. `evaluate_claim` processes claim text through a model
sub-processor, named along with retention terms and hosting region in the
[privacy policy](https://api.zetesis.science/privacy).

Attestations are signed with an ed25519 key held on the server. If you believe a signed record can
be altered without detection, or that `verify_attestation` can be made to accept a modified
record, treat that as a security report rather than a bug.
