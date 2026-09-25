# Connettore MCP per IL CASO.it (ricerca in tempo reale)

Strumenti esposti a Claude: `cerca_giurisprudenza`, `cerca_articoli`,
`ultime_pubblicazioni`, `leggi_documento`.

## 1. Installazione
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt

## 2. Configura la ricerca (una volta sola)
Il sito usa una Google Custom Search Engine ristretta a ilcaso.it (si vede dal
link "Cerca ... su Google" in fondo ai risultati). Il connettore usa la stessa
CSE tramite l'API ufficiale, con `cx` già impostato in `config.py`. Serve solo
una chiave API tua:

1. Vai su https://console.cloud.google.com/, crea (o riusa) un progetto.
2. Menu -> **API e servizi** -> **Libreria** -> cerca "Custom Search API" ->
   **Abilita**.
3. **API e servizi** -> **Credenziali** -> **Crea credenziali** ->
   **Chiave API**. Copiala.
4. (Consigliato) Limita la chiave alla sola Custom Search API, dalla stessa
   pagina delle credenziali.
5. Imposta la variabile d'ambiente prima di avviare il server:

       export GOOGLE_CSE_KEY="la-tua-chiave"

6. Imposta anche un contatto reale in `USER_AGENT` (usato solo quando il
   connettore legge direttamente le pagine del sito, non per l'API Google).
7. Prova senza Claude:

       python server.py --probe "misure protettive concordato minore"

   Se vedi risultati con titolo e URL, è pronto.

**Limiti dell'API:** 100 richieste/giorno gratuite, poi a pagamento (Google
Cloud, voce "Custom Search API"). Se superi la quota il connettore restituisce
un errore leggibile invece di rompersi; valuta di alzare `CACHE_TTL` in
`config.py` per ridurre le chiamate ripetute sulle stesse ricerche.

## 3. Collegamento a Claude
**Remoto (web, mobile, desktop):** pubblica su un host HTTPS (Render, Fly.io,
Cloud Run...) con comando `python server.py` e variabili `PORT` e
`MCP_PATH=/un-percorso-segreto/mcp` (il server è altrimenti pubblico).
Poi: Impostazioni -> Connettori -> Aggiungi connettore personalizzato ->
URL `https://tuo-host/un-percorso-segreto/mcp`.

**Locale (solo Claude Desktop):** in `claude_desktop_config.json`:

    {"mcpServers": {"ilcaso": {
      "command": "/percorso/.venv/bin/python",
      "args": ["/percorso/server.py"],
      "env": {"MCP_TRANSPORT": "stdio"}}}}

## Note d'uso
- Rispetta robots.txt, limita a 1 richiesta ogni 1,5 s, cache di 15 minuti.
- Non aggira il login Premium: i contenuti riservati vengono solo segnalati.
- Restituisce titoli, estratti e link; il testo integrale si legge alla fonte.
- Verifica i termini d'uso e, per un uso stabile, scrivi alla direzione della
  rivista: potrebbero offrirti un feed o un accesso dedicato.
