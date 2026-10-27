# Notes

## How to run

1. Copy `cloud-flare.sh` to `cloud-flare.local.sh` and fill in your Cloudflare account ID and a Workers AI API token (permissions: *Workers AI – Read* and *Workers AI – Edit*). This file is git-ignored.
2. Run (Python 3, standard library only — nothing to install):

   ```
   python3 classify.py                    # larger `clef` model (default)
   python3 classify.py --model clef-flash # faster/cheaper model
   python3 classify.py --html-only        # rebuild report.html from saved results
   python3 classify.py --input comments-v2.json  # classify a different comments file
   ```

3. Open `report.html` in a browser. Each comment is shown with Clef's label, its confidence and the probability split. You can filter by label, show only low-confidence answers, sort least-confident first, and search by text or `#id`.

Raw results (label, confidence, probabilities for every comment) are saved in `results.json`.

## How the classifier works

One Clef request per comment. The request passes the comment text plus its author name and thread, with instructions describing the forum (a college course on building with AI tools) and plain-English criteria for *acceptable*, *toxic* and *spam*. The criteria deliberately tell Clef that blunt criticism, frustration, sarcasm, Hinglish and undirected swearing are acceptable, and that toxicity means attacking a person or group.

## Tools and models used

- <!-- e.g. Claude (Opus) to read the task, write classify.py and this file -->
- Cloudflare Workers AI — Clef (`clef` / `clef-flash`) for classification
- <!-- anything else you used -->

## What I felt about doing this

<!-- Write this yourself: a few honest lines. -->
