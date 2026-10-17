"""Zetesis in the terminal: a diligence conversation with the hosted Zetesis agent.

Type `zetesis` and a chat opens. Each turn goes to the same endpoint as the web chat
(POST /app/agent) and streams back as server-sent events, so the steps print as they
happen: the claim is scoped, the dated public record is searched, then the graded
answer arrives. Nothing runs locally but this client; no Anthropic key is needed.

Config:
  ZETESIS_TOKEN  optional access token (higher limits)
  ZETESIS_API    override the API base (default https://api.zetesis.science)
"""
import html
import json
import os
import re
import select
import sys
import time
import webbrowser
import zipfile
from pathlib import Path

import httpx
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from . import __version__

API = os.environ.get("ZETESIS_API", "https://api.zetesis.science").rstrip("/")
TOKEN = os.environ.get("ZETESIS_TOKEN", "")
MAX_DOC = 120000

TEAL = "#3fa7b4"
BRONZE = "#c9974f"
NAMES = {"scope_claim": "Scope claim", "search_evidence": "Search evidence"}

console = Console(highlight=False)

HELP = """\
[bold]Commands[/]
  [bold]/attach[/] <path>   attach a PDF, DOCX, PPTX, TXT or MD file to your next message
  [bold]/sources[/]         list every source retrieved in this conversation, with links
  [bold]/new[/]             start a new conversation
  [bold]/web[/]             open the Zetesis web chat in your browser
  [bold]/help[/]            show this list
  [bold]/exit[/]            leave (or Ctrl-D)

A file path on its own attaches that file and asks for an assessment of it.
Add a year to judge a claim as it stood then: "as of 2021: ..."."""

EXAMPLES = [
    "Is PRMT5 a validated target in MTAP-deleted cancers?",
    "As of 2021, did the evidence support faricimab every 16 weeks in nAMD?",
    "Drag a deck or a paper into this window",
]


def welcome():
    body = Text()
    body.append("ζ ", style=f"bold italic {TEAL}")
    body.append("Welcome to Zetesis", style="bold")
    body.append(f"  v{__version__}\n", style="dim")
    body.append("Translating complex science into capital decisions.\n\n",
                style="dim")
    body.append("Drop in a deck, a paper or a protocol, or ask me anything that would help\n"
                "you assess and review the science behind a decision. I'll find the central\n"
                "hypothesis, search the dated public record and show you what holds up,\n"
                "with every source cited.\n\n")
    body.append("Try\n", style=f"bold {BRONZE}")
    for e in EXAMPLES:
        body.append("  › ", style=TEAL)
        body.append(e + "\n")
    body.append("\n/help for commands · /exit to leave", style="dim")
    console.print(Panel(body, border_style=TEAL, padding=(1, 2), expand=False))
    if TOKEN:
        console.print("  [dim]Signed in with ZETESIS_TOKEN.[/]")
    console.print()


# --- documents -------------------------------------------------------------------

def _xml_text(xml, tag):
    out = re.findall(rf"<{tag}>([^<]*)</{tag}>", xml)
    s = " ".join(out)
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'")):
        s = s.replace(a, b)
    return s


def read_document(path):
    p = Path(path).expanduser()
    if not p.is_file():
        raise ValueError(f"No file at {p}.")
    ext = p.suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        text = "\n\n".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages[:150])
    elif ext == ".docx":
        with zipfile.ZipFile(p) as z:
            xml = z.read("word/document.xml").decode("utf8", "ignore")
        text = "\n".join(_xml_text(para, "w:t") for para in xml.split("</w:p>"))
    elif ext == ".pptx":
        with zipfile.ZipFile(p) as z:
            slides = sorted((n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)),
                            key=lambda n: int(re.search(r"\d+", n).group()))
            text = "\n\n".join(_xml_text(z.read(n).decode("utf8", "ignore"), "a:t") for n in slides)
    elif ext in (".txt", ".md"):
        text = p.read_text(errors="ignore")
    else:
        raise ValueError("Unsupported file type. Use PDF, DOCX, PPTX, TXT or MD.")
    text = re.sub(r"\s+\n", "\n", text).strip()
    if len(text) < 200:
        raise ValueError("Not enough readable text was found. If this is a scanned PDF, "
                         "attach a text-based version.")
    return {"name": p.name, "text": text[:MAX_DOC]}


# --- rendering -------------------------------------------------------------------

def _id_url(i):
    if i.startswith("PMID:"):
        return f"https://pubmed.ncbi.nlm.nih.gov/{i[5:]}/"
    if i.startswith("NCT"):
        return f"https://clinicaltrials.gov/study/{i}"
    return "https://doi.org/" + re.sub(r"^DOI:", "", i, flags=re.I)


def _link_ids(md):
    # Plain cited ids become terminal hyperlinks; ids already inside a link are left alone.
    return re.sub(r"(?<![\[/])\b(PMID:\d+|NCT\d{8})\b(?!\]\()",
                  lambda m: f"[{m.group(1)}]({_id_url(m.group(1))})", md)


def _clean(title):
    t = re.sub(r"<[^>]+>", "", html.unescape(str(title or "")))
    return t.replace("[", "\\[")


def _args(name, inp):
    inp = inp or {}
    if name == "search_evidence":
        s = " · ".join(inp.get("queries") or [])
        if inp.get("as_of"):
            s += f"  (as of {inp['as_of']})"
        if inp.get("include_capital"):
            s += "  + funding and filings"
        return s
    s = str(inp.get("claim") or "")
    s = s if len(s) <= 140 else s[:140] + "…"
    return s + (f"  (as of {inp['as_of']})" if inp.get("as_of") else "")


class Answer:
    """Prints streamed markdown one finished block at a time, so tables arrive whole."""

    def __init__(self):
        self.buf = ""

    def feed(self, text):
        self.buf += text
        while True:
            i = self._cut()
            if i < 0:
                return
            block, self.buf = self.buf[:i], self.buf[i:].lstrip("\n")
            self._print(block)

    def _cut(self):
        # A blank line ends a block, unless it sits inside a code fence.
        pos = 0
        while True:
            i = self.buf.find("\n\n", pos)
            if i < 0:
                return -1
            if self.buf[:i].count("```") % 2 == 0:
                return i
            pos = i + 2

    def flush(self):
        if self.buf.strip():
            self._print(self.buf)
        self.buf = ""

    @staticmethod
    def _print(block):
        if block.strip():
            console.print(Markdown(_link_ids(block)))
            console.print()


# --- conversation ------------------------------------------------------------------

class Chat:
    def __init__(self):
        self.sid = ""
        self.doc = None
        self.sources = {}

    def turn(self, message):
        headers = {"Content-Type": "application/json"}
        if TOKEN:
            headers["Authorization"] = f"Bearer {TOKEN}"
        body = {"session_id": self.sid, "message": message, "document": self.doc}
        if self.doc:
            console.print(f"  [dim]📄 {self.doc['name']} attached[/]")
        self.doc = None
        console.print()
        answer = Answer()
        t0 = time.time()
        status = console.status(f"[{BRONZE}]Working…[/]", spinner="dots", spinner_style=BRONZE)
        status.start()
        try:
            with httpx.stream("POST", f"{API}/app/agent", json=body, headers=headers,
                              timeout=httpx.Timeout(30, read=300)) as r:
                if r.status_code != 200:
                    r.read()
                    try:
                        detail = r.json().get("detail")
                    except ValueError:
                        detail = None
                    raise RuntimeError(detail if isinstance(detail, str)
                                       else f"Something went wrong ({r.status_code}).")
                for line in r.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    ev = json.loads(line[6:])
                    kind = ev.get("type")
                    status.update(f"[{BRONZE}]Working… {int(time.time() - t0)}s[/]")
                    if kind == "session":
                        self.sid = ev["id"]
                    elif kind == "text":
                        answer.feed(ev["text"])
                    elif kind == "tool_start":
                        answer.flush()
                        name = ev.get("name", "")
                        console.print(Text.assemble(("⏺ ", BRONZE), (NAMES.get(name, name), "bold"),
                                                    ("  " + _args(name, ev.get("input")), "dim")))
                        status.update(f"[{BRONZE}]{NAMES.get(name, name)}…[/]")
                    elif kind == "tool_end":
                        srcs = ev.get("sources") or []
                        for s in srcs:
                            self.sources[s["id"]] = s
                        flagged = [s for s in srcs if s.get("serious")]
                        console.print(Text.assemble(("  ⎿ ", "dim"), (ev.get("label") or "done", "dim")))
                        for s in flagged:
                            console.print(Text.assemble(
                                ("    ", ""), (s["id"], "bold red"),
                                (f"  {str(s.get('integrity', '')).upper()}", "red")))
                        console.print()
                    elif kind == "error":
                        answer.flush()
                        console.print(f"[red]{ev.get('message', 'Error')}[/]")
        except KeyboardInterrupt:
            status.stop()
            answer.flush()
            console.print("[dim]Stopped.[/]\n")
            return
        except (httpx.HTTPError, RuntimeError) as e:
            status.stop()
            answer.flush()
            msg = str(e) if isinstance(e, RuntimeError) else "Could not reach Zetesis. Check your connection."
            console.print(f"[red]{msg}[/]\n")
            return
        status.stop()
        answer.flush()
        console.print(f"[dim]{int(time.time() - t0)}s · /sources lists every source · "
                      "the decision remains with you[/]\n")

    def list_sources(self):
        if not self.sources:
            console.print("[dim]No sources retrieved yet.[/]\n")
            return
        for s in self.sources.values():
            flag = f"  [red]{str(s.get('integrity')).upper()}[/]" if s.get("serious") else ""
            url = s.get("url") or ""
            idt = f"[link={url}]{s['id']}[/link]" if url else s["id"]
            console.print(f"  [bold {TEAL}]{idt}[/] [dim]{s.get('year') or ''}[/] "
                          f"{_clean(s.get('title'))}{flag}")
        console.print()

    def attach(self, path):
        try:
            self.doc = read_document(path)
        except Exception as e:  # noqa: BLE001  any read failure is shown, not raised
            console.print(f"[red]{e}[/]\n")
            return False
        console.print(f"  [{TEAL}]📄 {self.doc['name']}[/] [dim]· {len(self.doc['text']):,} "
                      "characters, sent with your next message[/]\n")
        return True


def _read_input():
    """One message. Lines that arrive together, as in a paste, become one message."""
    first = input("› ")
    lines = [first]
    while select.select([sys.stdin], [], [], 0.03)[0]:
        nxt = sys.stdin.readline()
        if not nxt:
            break
        lines.append(nxt.rstrip("\n"))
    return "\n".join(lines).strip()


def _as_path(s):
    s = s.strip().strip("'\"").replace("\\ ", " ")
    if "\n" in s or len(s) > 500:
        return None
    p = Path(s).expanduser()
    return p if p.suffix.lower() in (".pdf", ".docx", ".pptx", ".txt", ".md") and p.is_file() else None


def main():
    try:
        import readline  # noqa: F401  arrow keys and history in input()
    except ImportError:
        pass
    console.clear()
    welcome()
    chat = Chat()
    while True:
        try:
            msg = _read_input()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/]")
            return
        if not msg:
            continue
        cmd, _, rest = msg.partition(" ")
        if cmd in ("/exit", "/quit"):
            console.print("[dim]Goodbye.[/]")
            return
        if cmd == "/help":
            console.print(HELP + "\n")
        elif cmd == "/new":
            chat = Chat()
            console.clear()
            welcome()
        elif cmd == "/sources":
            chat.list_sources()
        elif cmd == "/web":
            webbrowser.open(f"{API}/app")
            console.print(f"[dim]Opened {API}/app[/]\n")
        elif cmd == "/attach":
            if not rest.strip():
                console.print("[dim]Usage: /attach <path>[/]\n")
            else:
                chat.attach(rest)
        elif cmd.startswith("/"):
            console.print(f"[dim]Unknown command {cmd}. /help lists them.[/]\n")
        elif _as_path(msg):
            if chat.attach(str(_as_path(msg))):
                chat.turn("Assess the central hypothesis of the attached document.")
        else:
            chat.turn(msg)


if __name__ == "__main__":
    main()
