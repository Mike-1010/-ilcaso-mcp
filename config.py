"""Configurazione del connettore IL CASO.it. Modifica qui, non in server.py."""
import os

BASE = "https://www.ilcaso.it"

# Identificati in modo onesto: imposta ILCASO_UA su Render con un contatto reale.
USER_AGENT = os.getenv(
    "ILCASO_UA", "ilcaso-mcp/0.2 (uso professionale personale; contatto: TUA_EMAIL)"
)

MIN_INTERVAL = 1.5   # secondi minimi tra due richieste al sito
CACHE_TTL = 900      # secondi di cache in memoria
TIMEOUT = 20

# --- Accesso Premium (opzionale) --------------------------------------------
# Variabile d'ambiente ILCASO_PREMIUM_TOKEN (mai nel codice).
PREMIUM_TOKEN = os.getenv("ILCASO_PREMIUM_TOKEN", "")
LOGIN_URL = f"{BASE}/home/login"
LOGIN_FIELD = "token_login"
PREMIUM_WALL_MARKER = "contenuto riservato ad utenti Premium"
# ---------------------------------------------------------------------------

# --- Ricerca ----------------------------------------------------------------
# v0.2 (09/10/2026): la ricerca via DuckDuckGo andava in timeout da Render
# (errore vuoto "Ricerca non riuscita: "). Ora la ricerca scorre gli ELENCHI
# UFFICIALI del sito (paginati, stesso dominio, robots.txt rispettato) e
# filtra i titoli in locale. Limite: copre le pubblicazioni recenti, non
# l'intero archivio (vedi nota restituita da ogni ricerca).
SEARCH_PAGES = int(os.getenv("ILCASO_SEARCH_PAGES", "5"))   # pagine di elenco per ricerca
SEARCH_PAGES_MAX = 10
# Elenco di default per le sentenze (il sito lo chiama "Tutte": include merito e legittimità).
SENTENZE_DEFAULT_SECTION = "Tutte"
# Fallback opzionale DuckDuckGo (disattivato: da Render non risponde).
USE_DDG_FALLBACK = os.getenv("ILCASO_USE_DDG", "0") == "1"
DDG_HTML_ENDPOINT = "https://html.duckduckgo.com/html/"
DDG_SITE_FILTER = "site:ilcaso.it"
DDG_TIMEOUT = 8
# ---------------------------------------------------------------------------

# Elenchi "ultime pubblicate" (verificati il 09/10/2026 dai link "segue ..." della home).
LISTING_URLS = {
    "merito": f"{BASE}/sezioni/merito/ultime_pubblicate",
    "legittimita": f"{BASE}/sezioni/Tutte/ultime_pubblicate",  # il sito non ha un elenco solo-legittimità
    "tutte": f"{BASE}/sezioni/Tutte/ultime_pubblicate",
    "articoli": f"{BASE}/articoli",
    "anteprime": f"{BASE}/linee_guida",
}
# Paginazione verificata: /sezioni/<Nome>/ultime_pubblicate/<N> e /articoli/tutti/<N>
SECTION_URL = BASE + "/sezioni/{name}"
SECTION_PAGE_URL = BASE + "/sezioni/{name}/ultime_pubblicate/{page}"
ARTICLES_PAGE_URL = BASE + "/articoli/tutti/{page}"
CITY_URL = BASE + "/citta_{name}"

CONTENT_SELECTORS = "article, main, #content, .content, .testo, .container"
