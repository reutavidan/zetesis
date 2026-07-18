"""Thin-client MCP server. Proxies to the hosted Zetesis API.

This is the server that lists on the Official MCP Registry and the Claude
Connectors Directory. It holds no engine, no Anthropic key, and no signing key:
the user sets ZETESIS_TOKEN (only for the full dossier) and every call goes to
https://api.zetesis.science. If MCP is superseded, this file is rewritten and the
hosted engine is untouched.

Tool descriptions are written for discovery: the model reads them to decide when
to reach for Zetesis, so they name the intents this tool should win.

Config:
  ZETESIS_TOKEN  the user's token (only for a full dossier; the free screen needs none)
  ZETESIS_API    override the API base (default https://api.zetesis.science)
"""
import json
import os
import urllib.error
import urllib.request

from mcp.server.fastmcp import FastMCP

API = os.environ.get("ZETESIS_API", "https://api.zetesis.science").rstrip("/")
TOKEN = os.environ.get("ZETESIS_TOKEN", "")

mcp = FastMCP("zetesis")

# every tool here only reads / requests an evaluation; nothing mutates the user's
# environment. openWorld because each call reaches an external service.
_READ = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": True}


@mcp.tool(annotations={**_READ, "title": "Evaluate a scientific or AI claim"})
def evaluate_claim(claim: str, context: str = "", documents: str = "", depth: str = "screen", mode: str = "research") -> str:
    """Evaluate how rigorously a scientific, biomedical, clinical, or AI/ML claim was derived, and how well the evidence supports it.

    Use this whenever someone wants to assess, screen, sanity-check, or do due
    diligence on a research claim, a study, a paper, an abstract, a preprint, a
    grant or a pitch: whether the methodology is sound, whether the data was
    harmonized and controlled properly, whether the statistics hold, whether the
    result reproduces, and how well the public literature, clinical trials, and
    filings back it. It grades each evidence dimension and returns an overall
    reading with sources cited by hard id (PMID, DOI, NCT, NIH grant, SEC filing).
    Works for drug, omics, target-validation, diagnostic, and AI-model claims.

    A screen is free and needs no token. A full attested dossier (deep) is the
    signed, independently re-checkable audit and needs access.

    Args:
        claim: the claim to evaluate, in one or two sentences.
        context: optional background (stage, field, the decision at hand).
        documents: optional source text (a deck, abstract, or paper).
        depth: "screen" for a fast, free pass (no token needed), "deep" for the full
            attested dossier (needs access).
        mode: "research" (science only) or "diligence" (adds the capital reading); deep only.
    """
    if depth == "screen":
        status, d = _call("POST", "/screen",
                          {"claim": claim, "context": context, "documents": documents}, auth=False)
        if status == 429:
            return d.get("detail", "Free screens are used up for now.")
        if status == 0:
            return d.get("detail", "network error")
        if status >= 400:
            return f"Error: {d.get('detail', status)}"
        return d.get("summary", "(no summary returned)")

    if not TOKEN:
        return f"A full attested dossier needs access. Request it at {API}/request-access."
    status, d = _call("POST", "/evaluate",
                      {"claim": claim, "context": context, "documents": documents, "depth": "deep", "mode": mode})
    if status == 401:
        return "Your token was rejected. Check ZETESIS_TOKEN."
    if status == 402:
        return f"{d.get('detail', 'This needs a paid plan.')} Manage your plan at {API}."
    if status == 0:
        return d.get("detail", "network error")
    if status >= 400:
        return f"Error: {d.get('detail', status)}"
    jid = d.get("job_id")
    return (f"Full evaluation started (job {jid}). It runs in the background.\n"
            f"Call check_evaluation with job_id \"{jid}\" for the result, "
            f"or open the dossier at {API}/d/{jid} once it is ready.")


@mcp.tool(annotations={**_READ, "title": "Get a full dossier result"})
def check_evaluation(job_id: str) -> str:
    """Get the result of a full (deep) Zetesis dossier started earlier. Returns the
    reading and the rendered dossier link once it is ready.

    Args:
        job_id: the id returned by evaluate_claim for a deep evaluation.
    """
    status, d = _call("GET", f"/jobs/{job_id}")
    if status >= 400:
        return f"Error: {d.get('detail', status)}"
    st = d.get("status")
    if st == "pending":
        return "Still running. Check again in a moment."
    if st == "error":
        return f"The evaluation failed: {d.get('error')}"
    return d.get("summary", "(no summary)") + f"\n\nRendered dossier: {API}{d.get('dossier_url', '')}"


@mcp.tool(annotations={**_READ, "title": "Verify a Zetesis attestation"})
def verify_attestation(attestation_json: str) -> str:
    """Verify a Zetesis attestation, confirming an evaluation's claim, evidence, and
    conclusion have not been altered since it was signed. Use when someone has a
    Zetesis dossier or attestation and wants to independently re-check it. No
    account needed.

    Args:
        attestation_json: the full attestation object as JSON text.
    """
    try:
        att = json.loads(attestation_json)
    except json.JSONDecodeError as e:
        return f"Not valid JSON: {e}"
    status, d = _call("POST", "/verify", att, auth=False)
    if status >= 400:
        return f"Error: {d.get('detail', status)}"
    if not d.get("valid"):
        return f"INVALID: {d.get('reason', 'verification failed')}"
    v = d.get("verdict", {})
    return (f"VALID. Attestation {str(d.get('id', ''))[:16]} signed at {d.get('created')} "
            f"using {d.get('model')}. Overall reading: {v.get('overall')}. "
            f"{d.get('evidence_count')} public sources pinned.")


@mcp.tool(annotations={**_READ, "title": "Zetesis account status"})
def account_status() -> str:
    """Show the caller's Zetesis plan and remaining free evaluations or dossier credits."""
    if not TOKEN:
        return f"No ZETESIS_TOKEN set. Request access at {API}/request-access."
    status, d = _call("GET", "/me")
    if status >= 400:
        return f"Error: {d.get('detail', status)}"
    cap = d.get("screen_cap")
    cap = "unlimited" if cap is None else cap
    return (f"Plan: {d.get('plan')}. Screens this month: {d.get('screens_used')}/{cap}. "
            f"Dossier credits: {d.get('dossier_balance')}.")


def _call(method, path, body=None, auth=True):
    headers = {"Content-Type": "application/json"}
    if auth and TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=175) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except Exception:
            return e.code, {"detail": e.reason}
    except Exception as e:  # network / timeout
        return 0, {"detail": f"could not reach Zetesis ({type(e).__name__})"}


def main():
    mcp.run()


if __name__ == "__main__":
    main()
