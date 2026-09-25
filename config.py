"""Configurazione del connettore IL CASO.it. Modifica qui, non in server.py."""
import os

BASE = "https://www.ilcaso.it"

# Identificati in modo onesto: metti un contatto reale.
USER_AGENT = os.getenv(
    "ILCASO_UA", "ilcaso-mcp/0.1 (uso professionale personale; contatto: TUA_EMAIL)"
)

MIN_INTERVAL = 1.5   # secondi minimi tra due richieste al sito
CACHE_TTL = 900      # secondi di cache in memoria
TIMEOUT = 20

# --- Ricerca: DuckDuckGo HTML (nessuna chiave richiesta) --------------------
# La Google Custom Search JSON API è chiusa ai nuovi clienti (Google, 2026),
# quindi interroghiamo DuckDuckGo con "site:ilcaso.it <query>" e riusiamo lo
# stesso parser HTML già scritto per il resto del sito. Nessun account,
# nessuna chiave, nessuna fatturazione richiesta.
DDG_HTML_ENDPOINT = "https://html.duckduckgo.com/html/"
DDG_SITE_FILTER = "site:ilcaso.it"
# ---------------------------------------------------------------------------

# Elenchi "ultime pubblicate" (pattern visti in homepage).
LISTING_URLS = {
    "merito": f"{BASE}/sezioni/merito/ultime_pubblicate",
    "legittimita": f"{BASE}/sezioni/Tutte/ultime_pubblicate",
    "articoli": f"{BASE}/articoli",
    "anteprime": f"{BASE}/linee_guida",
}
# Sezioni per materia: /sezioni/<Nome> (es. Bancario, Condominio, Lavoro...)
SECTION_URL = BASE + "/sezioni/{name}"
CITY_URL = BASE + "/citta_{name}"

# Contenitori candidati per il testo di un documento (si sceglie il più lungo).
CONTENT_SELECTORS = "article, main, #content, .content, .testo, .container"
