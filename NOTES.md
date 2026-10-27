# Notes

## How to run

1. Copy `cloud-flare.sh` to `cloud-flare.local.sh` and fill in your Cloudflare account ID and a Workers AI API token (permissions: *Workers AI – Read* and *Workers AI – Edit*). This file is git-ignored.
2. Run (Python 3, standard library only — nothing to install):

   ```
   python3 classify.py              # runs both sets
   python3 classify.py --only v1    # or just one set
   python3 classify.py --html-only  # rebuild the HTML pages from saved results
   ```

   | Set | Input | Model | Output |
   | --- | --- | --- | --- |
   | v1 | `comments.json` | `clef-flash` | `results.html`, `results.json` |
   | v2 | `comments-v2.json` | `clef` | `results-v2.html`, `results-v2.json` |

3. Open the HTML pages in a browser. Each comment is shown with Clef's label, its confidence and the probability split. You can filter by label, show only low-confidence answers, sort least-confident first, and search by text or `#id`.

My review of Clef's mistakes is in `MISTAKES.md` (v1) and `MISTAKES-v2.md` (v2).

## How the classifier works

One Clef request per comment. The request passes the comment text, its author and thread, and the course and assignment name, with instructions describing the forum and plain-English criteria for *acceptable*, *toxic* and *spam*. The criteria tell Clef that blunt criticism, frustration, sarcasm, Hinglish, undirected swearing, obvious exaggeration and quoting offensive text in order to discuss it (e.g. red-teaming prompts) are acceptable, and that toxicity means attacking a person or group.

## Tools and models used

- <!-- e.g. Claude (Opus) to read the task, write classify.py and this file -->
- Cloudflare Workers AI — Clef (`clef-flash` for v1, `clef` for v2)
- <!-- anything else you used -->

## What I felt about doing this

<!-- Write this yourself: a few honest lines. -->
