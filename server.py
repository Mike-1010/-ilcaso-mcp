"""Connettore MCP per la ricerca in tempo reale su IL CASO.it (v0.2).

Avvio remoto (connettore personalizzato di Claude):
    python server.py                       # http://0.0.0.0:8000/mcp
Avvio locale (Claude Desktop):
    MCP_TRANSPORT=stdio python server.py
Prova da riga di comando, senza Claude:
    python server.py --probe "misure protettive concordato minore"

Novità v0.2: la ricerca scorre gli elenchi ufficiali paginati del sito
(niente più DuckDuckGo, che da Render andava in timeout) e i messaggi di
errore riportano sempre il tipo di eccezione (prima erano vuoti).
"""
import argparse
import asyncio
import json
import os
import re
import time
import unicodedata
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
    "abbonati Premium. NOTA: la ricerca copre le pubblicazioni recenti "
    "(elenchi del sito), non l'intero archivio: se non trova nulla, "
    "aumenta `pagine` o indica la materia."
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
_login_lock = asyncio.Lock()
_logged_in = False


def _err(e: BaseException) -> str:
    """Messaggio d'errore mai vuoto (le eccezioni di timeout hanno str() vuota)."""
    return f"{type(e).__name__}: {e}".rstrip(": ")


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


async def _do_login() -> bool:
    """Invia il token Premium al modulo di login del sito."""
    global _last_request
    async with _lock:
        wait = config.MIN_INTERVAL - (time.monotonic() - _last_request)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            r = await _client.post(
                config.LOGIN_URL, data={config.LOGIN_FIELD: config.PREMIUM_TOKEN}
            )
        finally:
            _last_request = time.monotonic()
    return r.status_code in (200, 303) and "premium" in _client.cookies


async def ensure_login() -> None:
    """Login una sola volta per sessione, se è configurato un token Premium."""
    global _logged_in
    if not config.PREMIUM_TOKEN or _logged_in:
        return
    async with _login_lock:
        if _logged_in:
            return
        try:
            _logged_in = await _do_login()
        except httpx.HTTPError:
            _logged_in = False


async def fetch(url: str, params: dict | None = None, _retried: bool = False) -> str:
    """GET generico per le pagine di ilcaso.it."""
    global _last_request, _logged_in
    await ensure_login()
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
    text = r.text
    if config.PREMIUM_TOKEN and not _retried and config.PREMIUM_WALL_MARKER in text:
        _logged_in = False
        await ensure_login()
        return await fetch(url, params, _retried=True)
    _cache[key] = (time.monotonic(), text)
    return text


# --------------------------------------------------- Fallback DuckDuckGo (opz.)
def _unwrap_ddg(url: str) -> str:
    from urllib.parse import parse_qs, unquote

    if "duckduckgo.com/l/" in url:
        full = url if url.startswith("http") else "https:" + url
        real = parse_qs(urlparse(full).query).get("uddg", [None])[0]
        if real:
            return unquote(real)
    return url


async def ddg_search(query: str) -> str:
    """Solo se ILCASO_USE_DDG=1. Timeout breve: da Render spesso non risponde."""
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
            r = await _client.get(
                config.DDG_HTML_ENDPOINT, params={"q": q}, timeout=config.DDG_TIMEOUT
            )
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


def _norm(s: str) -> str:
    """Minuscolo senza accenti, per confronti tolleranti."""
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).casefold()


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
        blob = _norm(f"{it['titolo']} {it.get('estratto') or ''}")
        if organo and _norm(organo) not in blob:
            return False
        if anno and str(anno) not in blob:
            return False
        return True

    return [i for i in items if ok(i)]


def _rank(items: list[dict], query: str) -> tuple[list[dict], bool]:
    """Ordina per numero di termini trovati. Restituisce (items, parziale):
    prima i documenti con TUTTI i termini; se non ce ne sono, quelli con
    almeno metà dei termini (parziale=True)."""
    tokens = [t for t in re.split(r"\W+", _norm(query)) if len(t) > 2]
    if not tokens:
        return items, False
    scored = []
    for it in items:
        blob = _norm(f"{it['titolo']} {it.get('estratto') or ''}")
        score = sum(1 for t in tokens if t in blob)
        scored.append((score, it))
    full = [it for s, it in scored if s == len(tokens)]
    if full:
        return full, False
    half = sorted(
        ((s, it) for s, it in scored if s >= max(1, -(-len(tokens) // 2))),
        key=lambda x: -x[0],
    )
    return [it for _, it in half], True


def _listing_urls(kinds: set[str], pagine: int, materia: str | None) -> list[str]:
    urls: list[str] = []
    if kinds & {"sentenza"}:
        name = (materia or config.SENTENZE_DEFAULT_SECTION).strip()
        urls.append(config.SECTION_URL.format(name=name) + "/ultime_pubblicate")
        urls += [config.SECTION_PAGE_URL.format(name=name, page=p) for p in range(2, pagine + 1)]
    if kinds & {"articolo"}:
        urls.append(config.LISTING_URLS["articoli"])
        urls += [config.ARTICLES_PAGE_URL.format(page=p) for p in range(2, pagine + 1)]
    if kinds & {"anteprima"}:
        urls.append(config.LISTING_URLS["anteprime"])
    return urls


async def _search(query: str, kinds: set[str], organo, anno, n: int,
                  pagine: int | None = None, materia: str | None = None) -> dict:
    pagine = max(1, min(pagine or config.SEARCH_PAGES, config.SEARCH_PAGES_MAX))
    raw: list[dict] = []
    errors: list[str] = []
    seen: set[str] = set()
    for url in _listing_urls(kinds, pagine, materia):
        try:
            html = await fetch(url)
        except (httpx.HTTPError, PermissionError) as e:
            errors.append(f"{url}: {_err(e)}")
            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 404:
                continue
            continue
        for it in extract_results(html, url, kinds=None):
            k = it["url"].split("?")[0]
            if k not in seen:
                seen.add(k)
                raw.append(it)
    filtered = _filter(raw, organo, anno, kinds)
    ranked, parziale = _rank(filtered, query)
    items = ranked[:n]

    if not items and config.USE_DDG_FALLBACK:
        try:
            html = await ddg_search(query)
            items = _filter(extract_results(html, config.DDG_HTML_ENDPOINT), organo, anno, kinds)[:n]
        except Exception as e:  # il fallback non deve mai rompere la ricerca
            errors.append(f"DuckDuckGo: {_err(e)}")

    res = {
        "fonte": "IL CASO.it (elenchi ufficiali del sito)",
        "query": query,
        "documenti_esaminati": len(raw),
        "risultati": items,
        "nota_copertura": (
            f"Ricerca sui titoli di {len(raw)} pubblicazioni recenti "
            f"({pagine} pagine di elenco): non copre l'intero archivio."
        ),
    }
    if parziale and items:
        res["nota"] = "Nessun documento contiene tutti i termini: mostrati quelli con almeno metà dei termini."
    if not items:
        res["nota"] = (
            "Nessun risultato nelle pubblicazioni recenti. Prova termini più generici, "
            "aumenta `pagine` (max 10) o indica `materia` (es. Bancario, Condominio, Lavoro)."
        )
    if errors:
        res["errori_parziali"] = errors[:5]
    return res


# --------------------------------------------------------------------- Tools
@mcp.tool()
async def cerca_giurisprudenza(
    query: str, organo: str | None = None, anno: int | None = None,
    max_risultati: int = 10, pagine: int = 5, materia: str | None = None,
) -> dict:
    """Cerca sentenze e ordinanze su IL CASO.it (Cassazione, Sezioni Unite,
    Tribunali, Corti d'appello) in materia di crisi d'impresa, insolvenza,
    concordato, composizione negoziata, sovraindebitamento, diritto bancario,
    esecuzione forzata, condominio e locazioni, famiglia, societario, lavoro.
    La ricerca scorre gli elenchi ufficiali delle pubblicazioni recenti e
    confronta i titoli (che contengono le massime): non copre l'intero
    archivio. `organo` filtra per testo (es. "Cassazione", "Tribunale Milano");
    `anno` filtra per anno; `pagine` (1-10) quante pagine di elenco scorrere;
    `materia` restringe a una sezione (es. "Bancario", "Condominio", "Lavoro",
    "EsecuzioneForzata", "ProcCivile", "Civile", "Leasing")."""
    return await _search(query, {"sentenza"}, organo, anno, min(max_risultati, 25), pagine, materia)


@mcp.tool()
async def cerca_articoli(query: str, max_risultati: int = 10, pagine: int = 5) -> dict:
    """Cerca articoli di dottrina e commenti su IL CASO.it (diritto della crisi,
    bancario, societario, processuale) tra quelli recenti. Usalo per
    approfondimenti dottrinali o note a sentenza, non per le decisioni.
    `pagine` (1-10) quante pagine dell'elenco articoli scorrere."""
    return await _search(query, {"articolo"}, None, None, min(max_risultati, 25), pagine)


@mcp.tool()
async def ultime_pubblicazioni(
    sezione: str = "merito", citta: str | None = None, max_risultati: int = 10, pagina: int = 1
) -> dict:
    """Elenca le ultime pubblicazioni di IL CASO.it. `sezione`: "merito",
    "legittimita" (decisioni della Cassazione estratte dall'elenco generale),
    "tutte", "articoli", "anteprime", oppure il nome di una materia
    (es. "Bancario", "Condominio", "Lavoro", "Societario", "Tributario",
    "EsecuzioneForzata", "ProcCivile"). Se indichi `citta` (es. "Milano")
    elenca le decisioni di quel foro. `pagina` (>=1) per scorrere l'elenco."""
    pagina = max(1, pagina)
    key = sezione.strip().lower()
    if citta:
        url = config.CITY_URL.format(name=citta.strip().title())
    elif key == "articoli":
        url = config.LISTING_URLS["articoli"] if pagina == 1 else config.ARTICLES_PAGE_URL.format(page=pagina)
    elif key == "anteprime":
        url = config.LISTING_URLS["anteprime"]
    else:
        name = {"legittimita": "Tutte", "tutte": "Tutte", "merito": "merito"}.get(key, sezione.strip())
        base = config.SECTION_URL.format(name=name) + "/ultime_pubblicate"
        url = base if pagina == 1 else f"{base}/{pagina}"
    try:
        html = await fetch(url)
    except (httpx.HTTPError, PermissionError) as e:
        return {"errore": f"Elenco non disponibile: {_err(e)}", "risultati": []}
    items = extract_results(html, url)
    if key == "legittimita":
        items = [i for i in items if "cassazione" in _norm(i["titolo"])]
    return {
        "fonte": "IL CASO.it",
        "elenco": url,
        "pagina": pagina,
        "risultati": items[: min(max_risultati, 25)],
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
        return {"errore": f"Documento non recuperabile: {_err(e)}"}
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "nav", "header", "footer", "form", "noscript", "aside"]):
        t.decompose()
    cands = soup.select(config.CONTENT_SELECTORS) or [soup.body or soup]
    best = max(cands, key=lambda t: len(t.get_text()))
    text = _clean(best.get_text(" "))
    # Il primo h1/h2 è spesso solo la rubrica ("Crisi d'Impresa e Insolvenza"):
    # il titolo vero segue la riga "Il Caso.it, Sez. Giurisprudenza, N - pubb. gg/mm/aaaa".
    m = re.search(r"pubb\.\s*\d{2}/\d{2}/\d{4}\s+(.{15,300}?)(?:\s{2,}|$)", text)
    title = _clean(m.group(1)) if m else _clean((soup.find("h1") or soup.find("h2") or soup.title or soup).get_text(" "))[:300]
    res = {
        "fonte": "IL CASO.it",
        "url": url,
        "titolo": title,
        "testo": text[:max_caratteri],
        "troncato": len(text) > max_caratteri,
    }
    if config.PREMIUM_WALL_MARKER in text or (
        len(text) < 400 and re.search(r"premium|login|accedi|abbonat", text, re.I)
    ):
        res["nota"] = (
            "Contenuto riservato agli abbonati Premium: non è stato sbloccato "
            "(token Premium mancante, scaduto, o sessione respinta per troppi "
            "dispositivi attivi)."
            if config.PREMIUM_TOKEN
            else "Contenuto riservato agli abbonati Premium."
        )
    return res


# ---------------------------------------------------------------------- Main
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", help="esegue una ricerca di prova e stampa il JSON")
    args = ap.parse_args()
    if args.probe:
        print(json.dumps(asyncio.run(_search(args.probe, {"sentenza", "articolo"}, None, None, 10)),
                         ensure_ascii=False, indent=2))
    else:
        mcp.run(transport=os.getenv("MCP_TRANSPORT", "streamable-http"))
