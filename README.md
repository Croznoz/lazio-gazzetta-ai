# Lazio Gazzetta AI Automation

Un controllo automatico ogni due ore sul canale [Paolo Colantoni - Dentro la Lazio](https://www.youtube.com/@PaoloColantoni). Quando esce un video nuovo, il programma recupera la trascrizione e usa l'API Gemini di Google per scrivere un riassunto giornalistico sportivo originale, con ritmo e struttura ispirati alla Gazzetta dello Sport. Salva ogni articolo come file di testo semplice (`.txt`) nella cartella `articoli/` della repository.

```text
Canale YouTube → GitHub Actions ogni 2 ore → trascrizione → Gemini → articoli/*.txt
```

Il workflow viene eseguito sui server di GitHub: il computer può restare spento. Per avviarlo non servono plugin, controllo browser o Codex CLI.

## Attivazione su GitHub

1. Carica il progetto sul branch predefinito di una repository GitHub. Per usare gratuitamente i runner standard senza consumare la quota delle repository private, usa una repository pubblica.
2. In **Settings → Secrets and variables → Actions → Secrets**, crea il secret **`GEMINI_API_KEY`** con la tua chiave Google di un progetto nel piano gratuito. Il canale è già configurato.
3. Consenti al workflow di scrivere nella repository in **Settings → Actions → General → Workflow permissions**, nel rispetto delle regole del tuo account e del branch.
4. Vai in **Actions → Automazione Articoli Lazio → Run workflow**. Puoi selezionare `dry_run` per provare il controllo senza usare quota Gemini e scegliere `max_videos` per limitare le generazioni manuali. `video_date` accetta `today` (predefinito, oggi in Italia), una data `AAAA-MM-GG` oppure `all` per includere gli arretrati.

Da quel momento GitHub controlla automaticamente il canale ogni due ore e committa articoli, indice e stato. Il controllo pianificato usa `all` e dà precedenza ai video più recenti, così gli arretrati non consumano la quota prima delle notizie del giorno e un video serale non viene perso al cambio di data. Il cron è `17 */2 * * *`, cioè al minuto 17 degli orari UTC pari. La pianificazione deve trovarsi sul branch predefinito; GitHub può ritardare gli avvii.

Se il branch impone pull request obbligatorie, occorre adattare il salvataggio a un flusso con PR. Il workflow attuale esegue commit diretti.

## Gratuità e quote

I runner standard di GitHub Actions sono gratuiti nelle repository pubbliche; per quelle private valgono le risorse incluse e le condizioni del piano. Gli articoli sono normali file Git. Solo se il salvataggio su GitHub fallisce, il workflow conserva una copia di recupero come artifact per sette giorni. [Condizioni GitHub](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

Il modello predefinito è **`gemini-3.5-flash-lite`**, incluso nel Free Tier della Gemini API alla verifica del 4 novembre 2026 e verificato con una generazione reale da video YouTube. Il modello si può cambiare con `GEMINI_MODEL`; non vengono selezionati automaticamente modelli alternativi. [Prezzi e modelli Google](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.5-flash-lite).

La gratuità dipende dal piano del progetto associato alla chiave, dalla disponibilità del modello e dalle quote Google. Il codice non attiva billing, abbonamenti o passaggi a piani a pagamento e non può verificare o modificare il piano di fatturazione della chiave. Usa una chiave di un progetto Free Tier per restare nel piano gratuito. Se Google risponde con quota esaurita (HTTP 429), l'esecuzione interrompe le chiamate Gemini e riprova al controllo successivo. Non sono richiesti servizi di trascrizione a pagamento.

## Come vengono scritti gli articoli

- Si leggono i video recenti presenti nel feed. In locale e nelle esecuzioni manuali si selezionano per default quelli pubblicati oggi nel fuso `Europe/Rome`, anche durante l’ora legale. Il controllo pianificato considera tutto il feed, dai più recenti. Quelli già elaborati con un articolo presente vengono saltati; per esecuzione si tentano al massimo tre generazioni. Gli articoli cancellati vengono recuperati anche se il relativo ID è ancora nello stato.
- Gemini riceve la trascrizione, insieme a istruzioni per titolo incisivo, sommario e paragrafi ben costruiti e circa 400–650 parole quando la fonte lo consente.
- L'articolo deve sintetizzare ciò che viene detto, mantenere al condizionale le notizie non confermate, distinguere analisi e fatti e non inventare risultati, nomi, numeri o citazioni.
- L'articolo è originale e non viene presentato come un contenuto ufficiale della Gazzetta dello Sport.
- Ogni file contiene esclusivamente titolo, sommario e corpo dell'articolo in testo semplice. Non include nomi del canale o dell'autore, riferimenti a YouTube, link, firme, metadati, formattazione Markdown o note finali. Il testo va controllato prima di un'eventuale pubblicazione.
- Se mancano i sottotitoli, si prova il video pubblico direttamente con Gemini. Con `YOUTUBE_VIDEO_FALLBACK=false` il video resta in attesa. Non si genera un articolo dal solo titolo.
- Se YouTube blocca l'IP del runner durante il recupero dei sottotitoli, il programma può inviare a Gemini l'URL del video pubblico perché ne analizzi il parlato. Questa funzione Google è in anteprima e soggetta a quote, disponibilità e possibili modifiche; non ne viene garantito il successo. [Input YouTube per Gemini](https://ai.google.dev/gemini-api/docs/video-understanding#youtube).
- L'analisi del video diretto usa l'API **Interactions**, con input YouTube nativo, ragionamento `low` e `store=false`. Il testo dei sottotitoli continua a usare `generateContent`. Si accettano soltanto risposte complete contenenti un articolo; gli errori API mantengono il codice HTTP nei log e i video falliti restano da elaborare. Gli inizi delle generazioni sono distanziati di almeno 60 secondi per ridurre gli errori di frequenza. Ogni video ha un singolo tentativo API con timeout di tre minuti: eventuali errori verranno ritentati al controllo successivo, senza moltiplicare le chiamate dentro l'SDK.
- Errori parziali non cancellano gli articoli riusciti. Articoli, indice e stato vengono salvati con sostituzione atomica; il nome è riservato nell’indice prima di scrivere il testo, così dopo un’interruzione si recuperano i file già presenti senza rigenerarli. Il riepilogo di Actions mostra data selezionata, articoli creati, errori e video ancora da elaborare.

Il testo generato viene validato prima del salvataggio: nomi del canale e dell'autore, riferimenti al contenuto sorgente e URL fanno rifiutare l'articolo. Il relativo ID rimane da elaborare, così un output non conforme non viene archiviato come riuscito. I quattro articoli iniziali sono stati rielaborati nel nuovo formato; gli ID già elaborati sono conservati.

Con `--date all` e nel controllo pianificato si considerano anche i video già presenti nel feed, entro il limite di generazione e dando precedenza ai più recenti. Non viene scaricato lo storico completo: i video che escono dalla finestra del feed non sono recuperabili da questo controllo.

## File prodotti

```text
articoli/
├── 0001-2026-11-04-20-40-22.txt
├── 0002-2026-11-04-20-40-22.txt
└── indice.json                    Collegamento tra video, file e date
processed_videos.txt                ID dei video già trasformati in articoli
```

I nomi hanno il formato `PROGRESSIVO-AAAA-MM-GG-HH-MM-SS.txt`: il progressivo cresce globalmente e data e orario indicano la creazione dell’articolo in Italia. Per i file precedenti la migrazione usa la data di prima aggiunta in Git (oppure la data del file se non versionato). `indice.json` conserva separatamente ID e metadati, senza inserirli nel testo. La rinomina con `python app.py --rename-articles` non richiede rete né chiavi e non cambia il contenuto degli articoli.

Gli articoli vengono salvati nella repository GitHub. Per ritrovarli anche nella copia locale del progetto esegui `git pull` dopo aver collegato la repository. Per rigenerare un articolo elimina sia il suo file `.txt` sia l'ID da `processed_videos.txt`.

## Configurazione

In GitHub aggiungi le personalizzazioni in **Settings → Secrets and variables → Actions → Variables**. Le chiavi e gli eventuali URL con credenziali vanno in **Secrets**.

| Variabile | Default | Significato |
| --- | --- | --- |
| `GEMINI_API_KEY` | — | Secret necessario per generare articoli |
| `YOUTUBE_CHANNEL_ID` | `UCWOuIQE2PPdTDb_CEeaoqDA` | Canale di Paolo Colantoni |
| `YOUTUBE_FEED_URL` | Feed derivato dall'ID | Feed RSS completo, prevale sull'ID |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | Modello Google da usare |
| `MAX_VIDEOS_PER_RUN` | `3` | Massimo di generazioni tentate per controllo, da 1 a 50 |
| `MIN_GENERATION_INTERVAL_SECONDS` | `60` | Intervallo minimo fra gli inizi delle generazioni, da 0 a 120 secondi |
| `TRANSCRIPT_LANGUAGES` | `it` | Lingue dei sottotitoli, in ordine di preferenza |
| `YOUTUBE_VIDEO_FALLBACK` | `true` | Prova il video pubblico con Gemini se i sottotitoli mancano o sono bloccati |
| `YOUTUBE_PROXY_URL` | — | Secret opzionale per un proxy HTTP/HTTPS già disponibile; non è necessario al flusso normale |

## Esecuzione locale facoltativa

Richiede Python 3.12. Nell'ambiente di sviluppo già preparato basta usare `.venv/bin/python`.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
# Inserisci GEMINI_API_KEY in .env solo se vuoi generare in locale.
python app.py --dry-run                 # video di oggi, nessuna generazione
python app.py                           # genera per i video di oggi
python app.py --date 2026-11-05          # giorno specifico in Italia
python app.py --date all                 # tutto il feed, recenti prima
python app.py --rename-articles          # migrazione dei nomi precedenti
```

`.env` è escluso da Git. Le variabili d'ambiente prevalgono sui valori di `.env`. Articoli e stato sono sempre relativi alla cartella di `app.py`. Evita esecuzioni locali contemporanee sulla stessa cartella; GitHub Actions serializza automaticamente i propri controlli.

## Verifica

```sh
python -m pip install -r requirements-dev.txt
ruff check .
ruff format --check .
python -m unittest discover -s tests -v
```

I test usano file temporanei e provider simulati: non consumano quota API. Coprono feed, filtro data e fuso italiano, precedenza ai video recenti, progressivi, migrazione e integrità dell’indice, deduplicazione, articoli cancellati, errori, sottotitoli assenti, input video alternativo, intervallo fra richieste, quote Gemini, riepilogo Actions, formato .txt, assenza di riferimenti alla sorgente e recupero dopo interruzioni. Il workflow `Test` esegue questi controlli su push e pull request. La generazione reale richiede una chiave valida e va verificata anche sul runner GitHub.

La specifica iniziale resta in `progetto-antigravity.md`. L'implementazione usa l'[SDK Google GenAI mantenuto](https://ai.google.dev/gemini-api/docs/libraries) e l'API a istanze `YouTubeTranscriptApi().fetch(...)`.
