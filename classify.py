#!/usr/bin/env python3
"""Classify forum comments as acceptable / toxic / spam with Cloudflare's Clef,
then write an HTML page so a human can check Clef's work quickly.

Two runs, as the task asks:
    v1: comments.json    with clef-flash -> results.json,    results.html
    v2: comments-v2.json with clef       -> results-v2.json, results-v2.html

Usage:
    python3 classify.py                  # run v1 and v2
    python3 classify.py --only v2        # run just one of them
    python3 classify.py --html-only      # rebuild the HTML pages from saved results

Standard library only. Credentials are read from cloud-flare.local.sh (never committed).
"""
import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
CREDS_FILE = HERE / "cloud-flare.local.sh"

RUNS = {
    "v1": {"input": "comments.json", "model": "clef-flash",
           "json": "results.json", "html": "results.html"},
    "v2": {"input": "comments-v2.json", "model": "clef",
           "json": "results-v2.json", "html": "results-v2.html"},
}

LABELS = ["acceptable", "toxic", "spam"]

INSTRUCTIONS = (
    "`comment` was posted by `author` in the `thread` thread of a student discussion forum "
    "for `course`, a college course on using AI tools such as ChatGPT, Claude, Gemini and "
    "Codex. The current assignment is `assignment`. Moderators want to keep the forum "
    "useful and respectful. Decide whether "
    "the comment should stay up as it is (acceptable), be removed for being abusive "
    "(toxic), or be removed as unwanted promotion or junk (spam). Judge what the comment "
    "does, not its tone alone: students are often informal, frustrated, sarcastic or use "
    "Hinglish, and that is fine. Criticism of the course, the tools, the workload or the "
    "teaching is acceptable, even when blunt. Quoting or describing offensive, biased or "
    "manipulative text in order to discuss it (for example prompts or chatbot replies "
    "from testing an AI) is acceptable; so is obvious exaggeration about one's own "
    "frustration that threatens no one."
)

CRITERIA = {
    "acceptable": (
        "A genuine contribution from a student: a question, answer, update, opinion, joke, "
        "complaint or criticism, including blunt or frustrated ones and mild swearing that "
        "is not aimed at a person. Sharing one's own project or a relevant resource for the "
        "course is acceptable."
    ),
    "toxic": (
        "Attacks or demeans a person or group: insults, name-calling, mockery of someone's "
        "ability or background, harassment, threats, slurs, sexual remarks, or telling "
        "someone to leave or harm themselves. Profanity directed at a classmate, TA or "
        "instructor counts."
    ),
    "spam": (
        "Unwanted promotion or junk rather than participation: ads, selling assignments or "
        "'guaranteed marks' services, paid courses, referral or crypto links, phishing, "
        "requests to contact someone on WhatsApp/Telegram for business, or meaningless "
        "repeated text. Offering to do others' graded work for money counts."
    ),
}


def load_credentials():
    if not CREDS_FILE.exists():
        sys.exit(f"Missing {CREDS_FILE.name}. Copy cloud-flare.sh to it and fill in your "
                 "Cloudflare account ID and API token.")
    creds = dict(re.findall(r'export (\w+)="([^"]*)"', CREDS_FILE.read_text()))
    try:
        return creds["CLOUDFLARE_ACCOUNT_ID"], creds["CLOUDFLARE_API_TOKEN"]
    except KeyError as missing:
        sys.exit(f"{CREDS_FILE.name} is missing {missing}.")


def classify_one(item, context, account, token, model, retries=5):
    payload = {
        "state": {
            "comment": item["comment"],
            "author": item.get("author", ""),
            "thread": item.get("thread", ""),
            **context,
        },
        "questions": {
            "moderation": {
                "type": "choice",
                "instructions": INSTRUCTIONS,
                "criteria": CRITERIA,
            }
        },
    }
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/cloudflare/{model}"
    body = json.dumps(payload).encode("utf-8")
    for attempt in range(retries):
        request = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = json.load(response)
        except urllib.error.HTTPError as err:
            if err.code in (401, 403):
                sys.exit(f"HTTP {err.code}: check the account ID and token in {CREDS_FILE.name}.")
            if err.code == 429 or err.code >= 500:
                time.sleep(2 ** attempt)
                continue
            raise
        except urllib.error.URLError:
            time.sleep(2 ** attempt)
            continue
        if not data.get("success"):
            raise RuntimeError(f"Comment {item['id']}: {data.get('errors')}")
        answer = data["result"]["answers"]["moderation"]
        return {
            **item,
            "label": answer["choice"],
            "confidence": answer.get("confidence"),
            "probabilities": answer.get("probabilities", {}),
            "model": data["result"].get("model", model),
        }
    raise RuntimeError(f"Comment {item['id']}: gave up after {retries} attempts.")


def classify_all(comments_file, model, workers, account, token):
    data = json.loads((HERE / comments_file).read_text())
    comments = data["comments"]
    context = {"course": data.get("course", ""), "assignment": data.get("forum", "")}
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(classify_one, c, context, account, token, model) for c in comments]
        for n, future in enumerate(futures, 1):
            results.append(future.result())
            print(f"\r{n}/{len(comments)} classified", end="", flush=True)
    print()
    out = {key: value for key, value in data.items() if key != "comments"}
    out.update({"model": model, "results": sorted(results, key=lambda r: r["id"])})
    return out


def write_html(out, html_path):
    results = out["results"]
    counts = {label: sum(r["label"] == label for r in results) for label in LABELS}

    rows = []
    for r in results:
        probs = r.get("probabilities") or {}
        bar = "".join(
            f'<span class="seg {l}" style="width:{probs.get(l, 0) * 100:.1f}%" '
            f'title="{l} {probs.get(l, 0):.2f}"></span>'
            for l in LABELS
        )
        prob_text = " · ".join(f"{l[:3]} {probs.get(l, 0):.2f}" for l in LABELS)
        conf = r.get("confidence")
        conf_text = "—" if conf is None else f"{conf:.2f}"
        rows.append(
            f'<article class="card" data-label="{r["label"]}" data-conf="{conf if conf is not None else 1}" '
            f'data-id="{r["id"]}">'
            f'<div class="meta"><span class="id">#{r["id"]}</span>'
            f'<span class="tag {r["label"]}">{r["label"]}</span>'
            f'<span class="conf">confidence {conf_text}</span>'
            f'<span class="who">{html.escape(r.get("author", ""))} · {html.escape(r.get("thread", ""))}'
            f' · {html.escape(r.get("posted_at", ""))}</span></div>'
            f'<p class="text">{html.escape(r["comment"])}</p>'
            f'<div class="probs"><div class="bar">{bar}</div><span>{prob_text}</span></div>'
            f"</article>"
        )

    title = f"Clef moderation: {html.escape(out.get('source', ''))}"
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{ --bg:#f7f6f2; --card:#fff; --ink:#1d1d1b; --muted:#6b6a64; --line:#e4e2db;
  --ok:#2f7d4f; --tox:#c0392b; --spam:#b7791f; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#16161a; --card:#1f1f24; --ink:#ecebe6;
  --muted:#9a998f; --line:#2e2e35; --ok:#5cc88a; --tox:#ff7a6b; --spam:#f0b54a; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink);
  font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; }}
header {{ position:sticky; top:0; z-index:1; background:var(--bg); border-bottom:1px solid var(--line);
  padding:14px 16px; }}
h1 {{ font-size:18px; margin:0 0 4px; }}
.sub {{ color:var(--muted); font-size:13px; margin:0 0 10px; }}
.controls {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; }}
button {{ font:inherit; font-size:13px; border:1px solid var(--line); background:var(--card); color:var(--ink);
  border-radius:999px; padding:4px 12px; cursor:pointer; }}
button.on {{ background:var(--ink); color:var(--bg); border-color:var(--ink); }}
input {{ font:inherit; font-size:13px; padding:4px 10px; border-radius:999px; border:1px solid var(--line);
  background:var(--card); color:var(--ink); flex:1; min-width:140px; }}
main {{ max-width:860px; margin:0 auto; padding:12px 16px 40px; display:grid; gap:10px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-left:4px solid var(--line);
  border-radius:8px; padding:10px 14px; }}
.card[data-label=acceptable] {{ border-left-color:var(--ok); }}
.card[data-label=toxic] {{ border-left-color:var(--tox); }}
.card[data-label=spam] {{ border-left-color:var(--spam); }}
.card.unsure {{ outline:2px dashed var(--muted); outline-offset:-2px; }}
.meta {{ display:flex; flex-wrap:wrap; gap:8px; align-items:baseline; font-size:12px; color:var(--muted); }}
.id {{ font-weight:600; color:var(--ink); }}
.tag {{ font-weight:600; text-transform:uppercase; letter-spacing:.04em; }}
.tag.acceptable {{ color:var(--ok); }} .tag.toxic {{ color:var(--tox); }} .tag.spam {{ color:var(--spam); }}
.who {{ margin-left:auto; }}
.text {{ margin:6px 0 8px; white-space:pre-wrap; overflow-wrap:anywhere; }}
.probs {{ display:flex; gap:10px; align-items:center; font-size:11px; color:var(--muted); }}
.bar {{ display:flex; width:120px; height:6px; border-radius:3px; overflow:hidden; background:var(--line); flex:none; }}
.seg.acceptable {{ background:var(--ok); }} .seg.toxic {{ background:var(--tox); }} .seg.spam {{ background:var(--spam); }}
</style></head><body>
<header>
<h1>{title}</h1>
<p class="sub">{html.escape(out.get("course", ""))} — {html.escape(out.get("forum", ""))}<br>
Model: {html.escape(out.get("model", ""))} · {len(results)} comments ·
acceptable {counts["acceptable"]} · toxic {counts["toxic"]} · spam {counts["spam"]} ·
dashed outline = low confidence (&lt; 0.5)</p>
<div class="controls">
<button data-f="all" class="on">All</button>
<button data-f="acceptable">Acceptable</button>
<button data-f="toxic">Toxic</button>
<button data-f="spam">Spam</button>
<button data-f="unsure">Low confidence</button>
<button id="sort">Sort: by id</button>
<input id="q" type="search" placeholder="Search text or #id">
</div>
</header>
<main id="list">
{chr(10).join(rows)}
</main>
<script>
const list = document.getElementById('list');
const cards = [...list.children];
cards.forEach(c => {{ if (+c.dataset.conf < 0.5) c.classList.add('unsure'); }});
let filter = 'all', byConf = false;
function apply() {{
  const q = document.getElementById('q').value.trim().toLowerCase();
  const sorted = [...cards].sort((a, b) => byConf ? a.dataset.conf - b.dataset.conf : a.dataset.id - b.dataset.id);
  sorted.forEach(c => {{
    const okF = filter === 'all' || (filter === 'unsure' ? c.classList.contains('unsure') : c.dataset.label === filter);
    const okQ = !q || ('#' + c.dataset.id) === q || c.textContent.toLowerCase().includes(q);
    c.style.display = okF && okQ ? '' : 'none';
    list.appendChild(c);
  }});
}}
document.querySelectorAll('[data-f]').forEach(b => b.onclick = () => {{
  document.querySelectorAll('[data-f]').forEach(x => x.classList.remove('on'));
  b.classList.add('on'); filter = b.dataset.f; apply();
}});
document.getElementById('sort').onclick = e => {{
  byConf = !byConf; e.target.textContent = byConf ? 'Sort: least confident first' : 'Sort: by id'; apply();
}};
document.getElementById('q').oninput = apply;
</script>
</body></html>
"""
    html_path.write_text(page, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", choices=list(RUNS), help="run just v1 or v2 (default: both)")
    parser.add_argument("--workers", type=int, default=4, help="parallel requests (default 4)")
    parser.add_argument("--html-only", action="store_true", help="rebuild HTML from saved results JSON")
    args = parser.parse_args()

    names = [args.only] if args.only else list(RUNS)
    creds = None if args.html_only else load_credentials()
    for name in names:
        run = RUNS[name]
        json_path, html_path = HERE / run["json"], HERE / run["html"]
        if args.html_only:
            out = json.loads(json_path.read_text())
        else:
            print(f"{name}: {run['input']} with {run['model']}")
            out = classify_all(run["input"], run["model"], args.workers, *creds)
            out["source"] = run["input"]
            json_path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
        write_html(out, html_path)
        counts = {l: sum(r["label"] == l for r in out["results"]) for l in LABELS}
        print(f"{name}: wrote {json_path.name} and {html_path.name}: {counts}")


if __name__ == "__main__":
    main()
