"""Connettore MCP per la ricerca in tempo reale su IL CASO.it.

Avvio remoto (connettore personalizzato di Claude):
    python server.py                       # http://0.0.0.0:8000/mcp
Avvio locale (Claude Desktop):
    MCP_TRANSPORT=stdio python server.py
Prova da riga di comando, senza Claude:
    python server.py --probe "misure protettive concordato minore"
"""
import argparse
import asyncio
import json
import os
import re
import time
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP

import config

INSTRUCTIONS = (
    "Accesso in tempo reale a IL CASO.it, rivista di giurisprudenza italiana "
    "(crisi d'impresa e insolvenza, sovraindebitamento, diritto bancario e "
    "finanziario, esecuzione forzata, condominio e locazioni, famiglia, "
    "societario, lavoro, civile e procedura civile). Usa gli strumenti quando "
    "l'utente chiede orientamenti giurisprudenziali, sentenze di merito o di "
    "legittimità, o commenti dottrinali su questi temi. Cita sempre titolo, "
    "estremi e URL. Le massime e i sunti non sostituiscono il testo integrale: "
    "invita a verificarlo sulla fonte. Parte dei contenuti è riservata agli "
    "abbonati Premium."
)

mcp = FastMCP(
    "ilcaso",
    instructions=INSTRUCTIONS,
    host=os.getenv("HOST", "0.0.0.0"),
    port=int(os.getenv("PORT", "8000")),
    # Consiglio: imposta MCP_PATH a un percorso segreto, es. /k3j9x-mcp
    streamable_http_path=os.getenv("MCP_PATH", "/mcp"),
)

# ---------------------------------------------------------------- HTTP layer
_client = httpx.AsyncClient(
    headers={"User-Agent": config.USER_AGENT, "Accept-Language": "it-IT,it;q=0.9"},
    timeout=config.TIMEOUT,
    follow_redirects=True,
)
_lock = asyncio.Lock()
_last_request = 0.0
_cache: dict[str, tuple[float, str]] = {}
_robots: robotparser.RobotFileParser | None = None


async def _allowed(url: str) -> bool:
    """Rispetta robots.txt del sito."""
    global _robots
    if _robots is None:
        rp = robotparser.RobotFileParser()
        try:
            r = await _client.get(urljoin(config.BASE, "/robots.txt"))
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except httpx.HTTPError:
            rp.parse([])
        _robots = rp
    return _robots.can_fetch(config.USER_AGENT, url)


async def fetch(url: str, params: dict | None = None) -> str:
    """GET generico per le pagine di ilcaso.it (non per la ricerca)."""
    global _last_request
    key = url + "?" + json.dumps(params or {}, sort_keys=True)
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < config.CACHE_TTL:
        return hit[1]
    if not await _allowed(url):
        raise PermissionError(f"robots.txt del sito non consente l'accesso a {url}")
    async with _lock:
        wait = config.MIN_INTERVAL - (time.monotonic() - _last_request)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            r = await _client.get(url, params=params)
        finally:
            _last_request = time.monotonic()
    r.raise_for_status()
    _cache[key] = (time.monotonic(), r.text)
    return r.text


def _unwrap_ddg(url: str) -> str:
    """DuckDuckGo avvolge i link esterni in redirect (//duckduckgo.com/l/?uddg=...).
    Estrae l'URL reale."""
    from urllib.parse import parse_qs, unquote

    if "duckduckgo.com/l/" in url:
        full = url if url.startswith("http") else "https:" + url
        qs = parse_qs(urlparse(full).query)
        real = qs.get("uddg", [None])[0]
        if real:
            return unquote(real)
    return url


async def ddg_search(query: str, num: int = 10) -> str:
    """Interroga la pagina HTML pubblica di DuckDuckGo, con 'site:ilcaso.it'
    per restare sul dominio. Non richiede chiave API."""
    global _last_request
    q = f"{config.DDG_SITE_FILTER} {query}"
    key = f"ddg:{q}"
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < config.CACHE_TTL:
        return hit[1]
    async with _lock:
        wait = config.MIN_INTERVAL - (time.monotonic() - _last_request)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            r = await _client.get(config.DDG_HTML_ENDPOINT, params={"q": q})
        finally:
            _last_request = time.monotonic()
    r.raise_for_status()
    _cache[key] = (time.monotonic(), r.text)
    return r.text


# ------------------------------------------------------------------- Parsing
KINDS = {
    "sentenza": re.compile(r"/sentenze/[^/?#]+/\d+"),
    "articolo": re.compile(r"/articolo/\d+"),
    "anteprima": re.compile(r"/linea_guida/\d+"),
}
DATE_RE = re.compile(r"pubb\.\s*(\d{1,2}\s+[A-Za-zàèéìòù]+\s+\d{4})")


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _classify(url: str) -> str | None:
    for kind, pat in KINDS.items():
        if pat.search(urlparse(url).path):
            return kind
    return None


def extract_results(html: str, base: str, kinds: set[str] | None = None) -> list[dict]:
    """Estrae i link a documenti dalla pagina, senza dipendere da selettori CSS."""
    soup = BeautifulSoup(html, "html.parser")
    seen, out = set(), []
    for a in soup.find_all("a", href=True):
        url = _unwrap_ddg(a["href"])
        url = urljoin(base, url)
        if urlparse(url).netloc and not urlparse(url).netloc.endswith("ilcaso.it"):
            continue
        kind = _classify(url)
        if not kind or (kinds and kind not in kinds):
            continue
        key = url.split("?")[0]
        container = a.find_parent(["li", "div", "tr", "article", "p"]) or a.parent
        ctx = _clean(container.get_text(" ")) if container else ""
        title = _clean(a.get_text(" "))
        if len(title) < 15:  # link tipo "Leggi." -> usa il contesto
            title = ctx[:250]
        if len(title) < 15 or key in seen:
            continue
        seen.add(key)
        date = DATE_RE.search(ctx)
        snippet = ctx.replace(title, "")
        snippet = DATE_RE.sub("", snippet).replace("Leggi.", "")
        snippet = _clean(snippet)[:300]
        out.append(
            {
                "tipo": kind,
                "titolo": title,
                "url": url,
                "pubblicato": date.group(1) if date else None,
                "estratto": snippet or None,
            }
        )
    return out


def _filter(items, organo=None, anno=None, kinds=None):
    def ok(it):
        if kinds and it.get("tipo") not in kinds:
            return False
        blob = f"{it['titolo']} {it.get('estratto') or ''}".lower()
        if organo and organo.lower() not in blob:
            return False
        if anno and str(anno) not in blob:
            return False
        return True

    return [i for i in items if ok(i)]


async def _search(query: str, kinds: set[str], organo, anno, n: int) -> dict:
    try:
        html = await ddg_search(query, num=n)
    except httpx.HTTPError as e:
        return {"errore": f"Ricerca non riuscita: {e}", "risultati": []}
    raw = extract_results(html, config.DDG_HTML_ENDPOINT, kinds=None)
    items = _filter(raw, organo, anno, kinds)[:n]
    res = {"fonte": "IL CASO.it (via DuckDuckGo)", "query": query, "risultati": items}
    if not items:
        res["nota"] = "Nessun risultato. Prova termini più generici, sinonimi o meno filtri."
    return res


# --------------------------------------------------------------------- Tools
@mcp.tool()
async def cerca_giurisprudenza(
    query: str, organo: str | None = None, anno: int | None = None, max_risultati: int = 10
) -> dict:
    """Cerca sentenze e ordinanze su IL CASO.it (Cassazione, Sezioni Unite,
    Tribunali, Corti d'appello) in materia di crisi d'impresa, insolvenza,
    concordato, composizione negoziata, sovraindebitamento, diritto bancario,
    esecuzione forzata, condominio e locazioni, famiglia, societario, lavoro.
    Usalo quando serve un orientamento giurisprudenziale italiano.
    `organo` filtra per testo (es. "Cassazione", "Tribunale Milano");
    `anno` filtra per anno della decisione o della pubblicazione."""
    return await _search(query, {"sentenza", "anteprima"}, organo, anno, min(max_risultati, 25))


@mcp.tool()
async def cerca_articoli(query: str, max_risultati: int = 10) -> dict:
    """Cerca articoli di dottrina e commenti su IL CASO.it (diritto della crisi,
    bancario, societario, processuale). Usalo per approfondimenti dottrinali
    o note a sentenza, non per le decisioni."""
    return await _search(query, {"articolo"}, None, None, min(max_risultati, 25))


@mcp.tool()
async def ultime_pubblicazioni(
    sezione: str = "merito", citta: str | None = None, max_risultati: int = 10
) -> dict:
    """Elenca le ultime pubblicazioni di IL CASO.it. `sezione`: "merito",
    "legittimita", "articoli", "anteprime", oppure il nome di una materia
    (es. "Bancario", "Condominio", "Lavoro", "Societario", "Tributario",
    "EsecuzioneForzata", "ProcCivile"). Se indichi `citta` (es. "Milano")
    elenca le decisioni di quel foro."""
    if citta:
        url = config.CITY_URL.format(name=citta.strip().title())
    elif sezione in config.LISTING_URLS:
        url = config.LISTING_URLS[sezione]
    else:
        url = config.SECTION_URL.format(name=sezione.strip())
    try:
        html = await fetch(url)
    except (httpx.HTTPError, PermissionError) as e:
        return {"errore": f"Elenco non disponibile: {e}", "risultati": []}
    return {
        "fonte": "IL CASO.it",
        "elenco": url,
        "risultati": extract_results(html, url)[: min(max_risultati, 25)],
    }


@mcp.tool()
async def leggi_documento(url: str, max_caratteri: int = 8000) -> dict:
    """Recupera il testo di una sentenza, articolo o anteprima di IL CASO.it a
    partire dall'URL restituito dagli altri strumenti. Restituisce un estratto
    (max_caratteri, default 8000). Se il contenuto è riservato ai Premium lo
    segnala. Accetta solo URL del dominio ilcaso.it."""
    host = urlparse(url).netloc.lower()
    if urlparse(url).scheme not in ("http", "https") or not (
        host == "ilcaso.it" or host.endswith(".ilcaso.it")
    ):
        return {"errore": "Sono ammessi solo URL del dominio ilcaso.it"}
    try:
        html = await fetch(url)
    except (httpx.HTTPError, PermissionError) as e:
        return {"errore": f"Documento non recuperabile: {e}"}
    soup = BeautifulSoup(html, "html.parser")
    title = _clean((soup.find("h1") or soup.find("h2") or soup.title or soup).get_text(" "))[:300]
    for t in soup(["script", "style", "nav", "header", "footer", "form", "noscript", "aside"]):
        t.decompose()
    cands = soup.select(config.CONTENT_SELECTORS) or [soup.body or soup]
    best = max(cands, key=lambda t: len(t.get_text()))
    text = _clean(best.get_text(" "))
    res = {
        "fonte": "IL CASO.it",
        "url": url,
        "titolo": title,
        "testo": text[:max_caratteri],
        "troncato": len(text) > max_caratteri,
    }
    if len(text) < 400 and re.search(r"premium|login|accedi|abbonat", text, re.I):
        res["nota"] = "Contenuto probabilmente riservato agli abbonati Premium."
    return res


# ---------------------------------------------------------------------- Main
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", help="esegue una ricerca di prova e stampa il JSON")
    args = ap.parse_args()
    if args.probe:
        print(json.dumps(asyncio.run(_search(args.probe, set(KINDS), None, None, 10)),
                         ensure_ascii=False, indent=2))
    else:
        mcp.run(transport=os.getenv("MCP_TRANSPORT", "streamable-http"))
