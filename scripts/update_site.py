"""Update the Publications and Presentations lists in index.html.

Publications : fetched from PubMed. Settings in pubs_config.json
               (query, me = name in bold, exclude / include = PMIDs).
Presentations: read from presentations.csv. PDFs go in the slides/ folder.

Usage:
  python3 scripts/update_site.py                  # normal run
  python3 scripts/update_site.py --from-json F    # publications from a saved esummary-style JSON
"""
import csv
import html
import json
import pathlib
import sys
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
CONFIG = ROOT / "pubs_config.json"
PRES_CSV = ROOT / "presentations.csv"
EU = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
e = html.escape


def replace_block(page, name, content):
    start, end = f"<!-- {name}:START -->", f"<!-- {name}:END -->"
    head, rest = page.split(start, 1)
    _, tail = rest.split(end, 1)
    return f"{head}{start}\n{content}\n  {end}{tail}"


# ---------- Publications (PubMed) ----------
def get_json(endpoint, params):
    params = {**params, "db": "pubmed", "retmode": "json", "tool": "personal_homepage"}
    url = EU + endpoint + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def fetch_pubs(cfg):
    found = get_json("esearch.fcgi", {"term": cfg["query"], "retmax": 500})["esearchresult"]["idlist"]
    ids = [i for i in dict.fromkeys(found + cfg.get("include", [])) if i not in cfg.get("exclude", [])]
    if not ids:
        return []
    time.sleep(0.5)  # NCBI asks for <= 3 requests per second
    res = get_json("esummary.fcgi", {"id": ",".join(ids)})["result"]
    return [res[u] for u in res["uids"] if "error" not in res[u]]


def render_pubs(recs, me):
    recs = sorted(recs, key=lambda r: r.get("sortpubdate", ""), reverse=True)
    items = []
    for r in recs:
        authors = ", ".join(
            f"<b>{e(a['name'])}</b>" if a["name"] == me else e(a["name"]) for a in r.get("authors", [])
        )
        year = r.get("pubdate", "")[:4]
        vol = f";{e(r['volume'])}" if r.get("volume") else ""
        if vol and r.get("issue"):
            vol += f"({e(r['issue'])})"
        pages = f":{e(r['pages'])}" if r.get("pages") else ""
        doi = next((x["value"] for x in r.get("articleids", []) if x.get("idtype") == "doi"), None)
        links = f'<a href="https://pubmed.ncbi.nlm.nih.gov/{r["uid"]}/">PubMed</a>'
        if doi:
            links += f' · <a href="https://doi.org/{e(doi)}">doi</a>'
        title = e(r.get("title", "")).rstrip()
        if not title.endswith((".", "?", "!", "]")):
            title += "."
        items.append(f"  <li>{authors}. {title} <i>{e(r.get('source', ''))}</i>. {year}{vol}{pages}. {links}</li>")
    return "\n".join(items)


# ---------- Presentations (CSV) ----------
def render_pres():
    if not PRES_CSV.exists():
        return "  <li>Coming soon.</li>"
    with PRES_CSV.open(encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("date") or "").strip() and (r.get("title") or "").strip()]
    if not rows:
        return "  <li>Coming soon.</li>"
    rows.sort(key=lambda r: r["date"].strip(), reverse=True)
    items = []
    for r in rows:
        year = r["date"].strip()[:4]
        meeting = ", ".join(x.strip() for x in (r.get("meeting", ""), r.get("place", "")) if x and x.strip())
        text = f'{e(r["title"].strip())}.' + (f" {e(meeting)}." if meeting else "")
        link = ""
        pdf = (r.get("file") or "").strip()
        if pdf:
            if (ROOT / "slides" / pdf).exists():
                link = f' <a href="slides/{urllib.parse.quote(pdf)}">Slides (PDF)</a>'
            else:
                print(f"Warning: slides/{pdf} not found; listed without a link.")
        items.append(f'  <li><span class="year">{e(year)}</span> {text}{link}</li>')
    return "\n".join(items)


def main():
    page = INDEX.read_text(encoding="utf-8")
    new_page = replace_block(page, "PRES", render_pres())

    try:
        cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
        if len(sys.argv) == 3 and sys.argv[1] == "--from-json":
            recs = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))
        else:
            recs = fetch_pubs(cfg)
        if recs:
            new_page = replace_block(new_page, "PUBS", render_pubs(recs, cfg["me"]))
            print(f"Publications: {len(recs)} articles.")
        else:
            print("Publications: nothing retrieved; list left unchanged.")
    except Exception as err:  # PubMed down etc. -> keep the current list
        print(f"Publications: PubMed error ({err}); list left unchanged.")

    if new_page != page:
        INDEX.write_text(new_page, encoding="utf-8")
        print("index.html updated.")
    else:
        print("No change.")


if __name__ == "__main__":
    main()
