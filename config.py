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

# --- Accesso Premium (opzionale) --------------------------------------------
# Se imposti la variabile d'ambiente ILCASO_PREMIUM_TOKEN con il tuo token di
# 12 caratteri (quello ricevuto via email dopo l'abbonamento), il server fa
# login automaticamente e vede anche i contenuti riservati (Anteprime, Linee
# Guida, Massimari Ragionati). Senza questa variabile, il connettore funziona
# comunque, ma solo sui contenuti pubblici. NON scrivere il token qui nel
# codice: impostalo solo come variabile d'ambiente (locale o su Render).
PREMIUM_TOKEN = os.getenv("ILCASO_PREMIUM_TOKEN", "")
LOGIN_URL = f"{BASE}/home/login"
LOGIN_FIELD = "token_login"
PREMIUM_WALL_MARKER = "contenuto riservato ad utenti Premium"
# ---------------------------------------------------------------------------

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
