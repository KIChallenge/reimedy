"""Lädt die Formular-PDFs (lotse_zeigen=true) in den Cache forms/cache/<sha256>.pdf.

Quelle: links/formulare_live.jsonl (kanonisch). Live-URL zuerst, sonst lokale Kopie (_Source, nur Fallback).
≤1 Request/s pro Host, generischer User-Agent. Cache ist gitignored und reproduzierbar.
uv run --with httpx knowledge/build/forms/fetch_pdfs.py
"""
from __future__ import annotations
import asyncio, hashlib, json, sys, time
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
LIVE = HERE.parent / "links" / "formulare_live.jsonl"
CACHE = HERE / "cache"
SRC_ROOTS = [HERE.parents[2], Path("/Users/arne/_Coding/_reimedy_svhack")]
UA = "SV-Lotse-Hackathon/0.1"


def rows():
    for l in LIVE.open():
        r = json.loads(l)
        if r.get("lotse_zeigen"):
            yield r


async def main():
    import httpx
    CACHE.mkdir(exist_ok=True)
    todo: dict[str, list] = {}
    out = {}
    for r in rows():
        u = r.get("url_pdf") or r.get("url")
        sha = r.get("sha256")
        if sha and (CACHE / f"{sha}.pdf").exists():
            out[r["formular_id"]] = {"sha256": sha, "quelle": "cache"}
            continue
        if not u or r.get("url_status") == "online":
            # lokale Kopie?
            lp = r.get("local_pdf")
            if lp:
                for root in SRC_ROOTS:
                    p = root / lp
                    if p.is_file():
                        b = p.read_bytes(); s = hashlib.sha256(b).hexdigest()
                        (CACHE / f"{s}.pdf").write_bytes(b)
                        out[r["formular_id"]] = {"sha256": s, "quelle": "lokal"}
                        break
            continue
        todo.setdefault(urlparse(u).netloc, []).append((r, u))

    async def host_worker(client, items):
        for r, u in items:
            t = time.monotonic()
            try:
                resp = await client.get(u)
                b = resp.content
                if resp.status_code == 200 and b[:5] == b"%PDF-":
                    s = hashlib.sha256(b).hexdigest()
                    (CACHE / f"{s}.pdf").write_bytes(b)
                    out[r["formular_id"]] = {"sha256": s, "quelle": "live", "url": str(resp.url)}
                else:
                    out[r["formular_id"]] = {"fehler": f"http {resp.status_code} {resp.headers.get('content-type')}"}
            except Exception as e:  # noqa
                out[r["formular_id"]] = {"fehler": repr(e)[:200]}
            await asyncio.sleep(max(0, 1.05 - (time.monotonic() - t)))

    async with httpx.AsyncClient(headers={"User-Agent": UA}, follow_redirects=True, timeout=60) as c:
        await asyncio.gather(*(host_worker(c, it) for it in todo.values()))
    # lokale Fallbacks für fehlgeschlagene
    for r in rows():
        fid = r["formular_id"]
        if fid in out and "sha256" in out[fid]:
            continue
        lp = r.get("local_pdf")
        for root in SRC_ROOTS:
            if lp and (root / lp).is_file():
                b = (root / lp).read_bytes(); s = hashlib.sha256(b).hexdigest()
                (CACHE / f"{s}.pdf").write_bytes(b)
                out[fid] = {"sha256": s, "quelle": "lokal"}
                break
    (CACHE / "fetch_index.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    ok = sum(1 for v in out.values() if "sha256" in v)
    print(f"{ok} PDFs im Cache, {len(out)-ok} Fehler", file=sys.stderr)

if __name__ == "__main__":
    asyncio.run(main())
