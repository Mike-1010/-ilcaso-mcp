# Connettore MCP per IL CASO.it (ricerca in tempo reale)

Strumenti esposti a Claude: `cerca_giurisprudenza`, `cerca_articoli`,
`ultime_pubblicazioni`, `leggi_documento`.

## 1. Installazione
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt

## 2. Ricerca (nessuna configurazione richiesta)
Il connettore interroga DuckDuckGo con `site:ilcaso.it <query>` e ne estrae i
risultati. Non serve nessuna chiave API, nessun account Google Cloud, nessuna
fatturazione: funziona subito dopo `pip install`.

(In precedenza avevamo provato la Google Custom Search JSON API, ma Google
l'ha chiusa ai nuovi clienti nel 2026 — i progetti creati oggi non ottengono
accesso, indipendentemente da come configuri chiave o fatturazione. Se in
futuro vuoi maggiore volume o affidabilità, un'alternativa a pagamento come
SerpApi o Bing Web Search offrirebbe risultati più stabili di DuckDuckGo, che
non ha una vera API pubblica e può limitare le richieste se troppo frequenti.)

Prova subito, senza Claude:

    python server.py --probe "misure protettive concordato minore"

Se vedi risultati con titolo e URL di ilcaso.it, è pronto.

Imposta anche un contatto reale in `USER_AGENT` (config.py), usato quando il
connettore legge le pagine del sito (non per DuckDuckGo).

## 3. Accesso Premium (opzionale)
Se hai un abbonamento Premium a IL CASO.it, il server può fare login da solo
usando il tuo token di 12 caratteri (quello ricevuto via email), e vedrà anche
i contenuti riservati (Anteprime, Linee Guida, Massimari Ragionati).

Imposta la variabile d'ambiente prima di avviare il server:

    export ILCASO_PREMIUM_TOKEN="il-tuo-token-di-12-caratteri"

Su Windows PowerShell: `$env:ILCASO_PREMIUM_TOKEN="..."`. Su Render: aggiungi
`ILCASO_PREMIUM_TOKEN` tra le Environment Variables del servizio, esattamente
come hai fatto per `MCP_PATH`.

Senza questa variabile, il connettore funziona comunque, ma solo sui
contenuti pubblici — nessuna differenza rispetto a prima.

**Attenzione**: il sito sembra limitare le sessioni Premium simultanee per
token ("Troppi dispositivi"). Se usi lo stesso token anche nel tuo browser
personale, potresti dover disconnetterti da un posto per far funzionare
l'altro. Il server ritenta il login una volta se rileva che la sessione è
scaduta o è stata respinta, ma non puoi avere lo stesso token attivo ovunque
contemporaneamente se il sito impone quel limite.

Non condividere né incollare il token in luoghi non privati: chiunque lo
conosca può usare il tuo abbonamento.

## 4. Collegamento a Claude
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
