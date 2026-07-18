# Zetesis

Scientific due diligence on a claim, from inside Claude, Copilot, or any MCP host.

Zetesis takes a high-dimensional scientific or technical claim and grades it
dimension by dimension against public literature, clinical trials, and filings.
It returns an overall reading, cites every source by id, and, for a full
evaluation, translates the science into what a commitment to the claim turns on
and seals the result in an attestation anyone can re-check.

This package is a thin MCP client. It holds no keys and runs no model. Every call
is proxied to the hosted engine at <https://api.zetesis.science> with your token.

## Get a token

Free, no card, at <https://api.zetesis.science/signup>. The free plan gives you a
handful of screening evaluations each month.

## Connect it

Claude Code:

```bash
claude mcp add zetesis --env ZETESIS_TOKEN=zk_... -- uvx --from zetesis zetesis-client
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "zetesis": {
      "command": "uvx",
      "args": ["--from", "zetesis", "zetesis-client"],
      "env": { "ZETESIS_TOKEN": "zk_..." }
    }
  }
}
```

## Tools

- **evaluate_claim** — grade a claim. `depth="screen"` returns the verdict directly
  (free tier); `depth="deep"` runs the full signed dossier in the background.
  `mode="research"` is science only; `mode="diligence"` adds the capital reading.
- **check_evaluation** — get the verdict and the rendered dossier link for a deep run.
- **verify_attestation** — re-check any Zetesis attestation. No account needed.
- **account_status** — your plan and remaining evaluations or credits.

## How it grades

It grades only what the evidence supports, cites sources by hard id (PMID, DOI,
NCT, NIH grant, SEC filing), and flags gaps rather than filling them. It never
invents citations. Claim text is not logged; only metadata (the routed domain,
depth, counts) is kept.

## Configuration

- `ZETESIS_TOKEN` — your token (required for evaluations; verify works without one)
- `ZETESIS_API` — override the API base (default `https://api.zetesis.science`)

MIT licensed. The hosted engine is a separate service.

---
mcp-name: io.github.reutavidan/zetesis
