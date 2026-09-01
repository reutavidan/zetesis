# Zetesis

[Available on Smithery](https://smithery.ai/servers/reutavidan/zetesis)

Scientific due diligence on a claim, from inside Claude, Copilot, or any MCP host.

Give Zetesis a claim, an abstract, a paper, a grant or a deck. It routes the claim to its
scientific class, then returns the questions a domain reviewer would ask, the failure patterns
that caught comparable claims before, and the public evidence bearing on it, with a PMID, DOI,
NCT number, NIH grant number or SEC filing reference on every source. Every identifier it hands
back was retrieved. None are generated.

It can also evaluate a claim **as it stood in an earlier year**, restricting evidence to what
existed by then, so a claim is judged on what was knowable at the time rather than on how it
turned out.

## Connect it

The hosted server is at `https://api.zetesis.science/mcp`, over Streamable HTTP.
**No account, key or token is required.**

Claude Code:

```bash
claude mcp add --transport http zetesis https://api.zetesis.science/mcp
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "zetesis": {
      "type": "http",
      "url": "https://api.zetesis.science/mcp"
    }
  }
}
```

Any other MCP client:

| Client | How |
|---|---|
| **Microsoft Copilot Studio** | Tools, then Add a tool, then Model Context Protocol. Server URL, auth **None**. |
| **ChatGPT** | Settings, then Connectors, then Developer mode. Add the URL. |
| **Gemini CLI** | `gemini mcp add --transport http zetesis https://api.zetesis.science/mcp` |

For Gemini's `settings.json`, use `httpUrl` rather than `url`; the latter is SSE and will not
connect. Full setup notes: <https://api.zetesis.science/docs>

## Tools

**`zetesis_scope`** routes the claim and returns the diligence apparatus for its class: the
questions a reviewer would ask, structured by substrate, methods, cohort and risk of bias, a
failure-pattern taxonomy carrying the companies each pattern was derived from, and the edge cases
where those patterns were wrong. A checklist that only ever fires positive teaches over-rejection,
so the counterexamples ship alongside it.

**`zetesis_evidence`** runs the searches and returns a deduplicated bundle from Europe PMC,
ClinicalTrials.gov, openFDA, NIH RePORTER and SEC EDGAR, every source carrying a hard public
identifier, followed by the grading rubric so you grade the evidence yourself in context.

**Neither of those calls a language model.** They return in under a second, cost nothing to run,
and send nothing to a model provider. That is usually the answer a security reviewer is looking
for.

**`evaluate_claim`** produces Zetesis's own graded reading server-side. Slower, and only needed
when the assessment itself is the deliverable rather than the evidence.

**`verify_attestation`** re-checks a signed Zetesis record to confirm its claim, evidence and
conclusion have not been altered since signing. Needs no account.

Claim classes: genomics and Mendelian randomisation, single-cell, bulk omics, CRISPR screens,
clinical trials, real-world evidence, AI clinical decision support, diagnostics, preclinical
models, cell and gene therapy, structural biology.

## Why the year fence matters

Ask a general model about a 2020 claim today and it answers with years of hindsight; the
publication that mattered at the time is buried under everything published since.

Measured on a control claim: unfenced retrieval **missed the pivotal publication entirely** and
scored 35% evidence coverage. Fenced to the claim's own year, the same query set retrieved it and
coverage rose to 79%. So the fence is not only about honesty in retrospect. It is a retrieval
precision feature.

Set `as_of` to the year a claim was made for anything that is not brand new.

## Try it

```
What did the published evidence actually support about aducanumab and cognitive
decline at the end of 2019, using only sources available by then?
```

Then ask the same question without the year and compare. The difference is the point.

## Privacy

The evidence tools send nothing to a model provider. `evaluate_claim` processes claim text through
a model sub-processor, named along with retention terms and hosting region in the
[privacy policy](https://api.zetesis.science/privacy). Claim text is not logged; only metadata
(the routed class, depth, counts) is kept.

## The Python client

This repository also publishes a thin stdio MCP client to PyPI, which predates the hosted server
and exposes an older tool set (`evaluate_claim`, `check_evaluation`, `verify_attestation`,
`account_status`). It holds no keys and runs no model; every call is proxied to the hosted engine,
and it needs a token.

**Prefer the hosted endpoint above.** It needs no token and carries the current tools. The client
remains for existing stdio setups:

```bash
claude mcp add zetesis --env ZETESIS_TOKEN=zk_... -- uvx --from zetesis zetesis-client
```

Tokens: <https://api.zetesis.science/request-access>

- `ZETESIS_TOKEN` sets the token (verification works without one)
- `ZETESIS_API` overrides the API base, default `https://api.zetesis.science`

## Security

Report vulnerabilities privately to <avidan.r@zetesis.science>. See [SECURITY.md](SECURITY.md).

MIT licensed. The hosted engine is a separate service.

---
mcp-name: io.github.reutavidan/zetesis
