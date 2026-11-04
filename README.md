# Lazio Gazzetta AI Automation

Un controllo automatico ogni due ore sul canale [Paolo Colantoni - Dentro la Lazio](https://www.youtube.com/@PaoloColantoni). Quando esce un video nuovo, il programma recupera la trascrizione e usa l'API Gemini di Google per scrivere un riassunto giornalistico sportivo originale, con ritmo e struttura ispirati alla Gazzetta dello Sport. Salva ogni articolo come file Markdown nella cartella `articoli/` della repository.

```text
Canale YouTube → GitHub Actions ogni 2 ore → trascrizione → Gemini → articoli/*.md
```

Il workflow viene eseguito sui server di GitHub: il computer può restare spento. Per avviarlo non servono plugin, controllo browser o Codex CLI.

## Attivazione su GitHub

1. Carica il progetto sul branch predefinito di una repository GitHub. Per usare gratuitamente i runner standard senza consumare la quota delle repository private, usa una repository pubblica.
2. In **Settings → Secrets and variables → Actions → Secrets**, crea il secret **`GEMINI_API_KEY`** con la tua chiave Google di un progetto nel piano gratuito. Il canale è già configurato.
3. Consenti al workflow di scrivere nella repository in **Settings → Actions → General → Workflow permissions**, nel rispetto delle regole del tuo account e del branch.
4. Vai in **Actions → Automazione Articoli Lazio → Run workflow**. Puoi selezionare `dry_run` per provare il controllo senza usare quota Gemini.

Da quel momento GitHub controlla automaticamente il canale ogni due ore e committa articoli e stato. Il cron è `17 */2 * * *`, cioè al minuto 17 degli orari UTC pari. La pianificazione deve trovarsi sul branch predefinito; GitHub può ritardare gli avvii.

Se il branch impone pull request obbligatorie, occorre adattare il salvataggio a un flusso con PR. Il workflow attuale esegue commit diretti.

## Gratuità e quote

I runner standard di GitHub Actions sono gratuiti nelle repository pubbliche; per quelle private valgono le risorse incluse e le condizioni del piano. Non vengono caricati artifact di Actions: gli articoli sono normali file Git. [Condizioni GitHub](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

Il modello predefinito è **`gemini-3.8-flash`**, che risulta incluso nel Free Tier della Gemini API alla verifica del 4 novembre 2026. Il precedente 2.5 Flash della specifica è deprecato. Il modello si può cambiare con `GEMINI_MODEL`; non vengono selezionati automaticamente modelli alternativi. [Prezzi e modelli Google](https://ai.google.dev/gemini-api/docs/pricing).

La gratuità dipende dal piano del progetto associato alla chiave, dalla disponibilità del modello e dalle quote Google. Il codice non attiva billing, abbonamenti o passaggi a piani a pagamento e non può verificare o modificare il piano di fatturazione della chiave. Usa una chiave di un progetto Free Tier per restare nel piano gratuito. Se Google risponde con quota esaurita (HTTP 429), l'esecuzione interrompe le chiamate Gemini e riprova al controllo successivo. Non sono richiesti servizi di trascrizione a pagamento.

## Come vengono scritti gli articoli

- Si leggono tutti i video recenti presenti nel feed. Quelli già elaborati vengono saltati; per esecuzione si tentano al massimo tre generazioni, dai video più vecchi ancora da elaborare.
- Gemini riceve la trascrizione, insieme a istruzioni per titolo incisivo, occhiello, catenaccio, sottotitoli e circa 400–650 parole quando la fonte lo consente.
- L'articolo deve sintetizzare ciò che viene detto, attribuire opinioni e indiscrezioni a Colantoni e non inventare risultati, nomi, numeri o citazioni.
- L'articolo è originale e non viene presentato come un contenuto ufficiale della Gazzetta dello Sport.
- Ogni file include data, modello, video sorgente, link alla fonte e `status: draft`. Le bozze vanno controllate prima di un'eventuale pubblicazione.
- Se mancano i sottotitoli, il video resta in attesa e non blocca gli altri. Non si genera un articolo dal solo titolo.
- Se YouTube blocca l'IP del runner durante il recupero dei sottotitoli, il programma può inviare a Gemini l'URL del video pubblico perché ne analizzi il parlato. I metadati distinguono `transcript` da `youtube_video`. Questa funzione Google è in anteprima e soggetta a quote, disponibilità e possibili modifiche; non ne viene garantito il successo. [Input YouTube per Gemini](https://ai.google.dev/gemini-api/docs/video-understanding#youtube).
- Errori parziali non cancellano gli articoli riusciti. Articoli e stato vengono salvati con sostituzione atomica; dopo un'interruzione si recuperano i file già presenti senza rigenerarli.

Alla prima esecuzione si considerano anche i video già presenti nel feed, entro il limite di generazione. Non viene scaricato lo storico completo: i video che escono dalla finestra del feed non sono recuperabili da questo controllo.

## File prodotti

```text
articoli/
└── ID_VIDEO_titolo-del-video.md
processed_videos.txt                ID dei video già trasformati in articoli
```

Gli articoli vengono salvati nella repository GitHub. Per ritrovarli anche nella copia locale del progetto esegui `git pull` dopo aver collegato la repository. Per rigenerare un articolo elimina sia il suo file `.md` sia l'ID da `processed_videos.txt`.

## Configurazione

In GitHub aggiungi le personalizzazioni in **Settings → Secrets and variables → Actions → Variables**. Le chiavi e gli eventuali URL con credenziali vanno in **Secrets**.

| Variabile | Default | Significato |
| --- | --- | --- |
| `GEMINI_API_KEY` | — | Secret necessario per generare articoli |
| `YOUTUBE_CHANNEL_ID` | `UCWOuIQE2PPdTDb_CEeaoqDA` | Canale di Paolo Colantoni |
| `YOUTUBE_FEED_URL` | Feed derivato dall'ID | Feed RSS completo, prevale sull'ID |
| `GEMINI_MODEL` | `gemini-3.8-flash` | Modello Google da usare |
| `MAX_VIDEOS_PER_RUN` | `3` | Massimo di generazioni tentate per controllo, da 1 a 50 |
| `TRANSCRIPT_LANGUAGES` | `it` | Lingue dei sottotitoli, in ordine di preferenza |
| `YOUTUBE_VIDEO_FALLBACK` | `true` | Prova il video pubblico con Gemini se YouTube blocca i sottotitoli |
| `YOUTUBE_PROXY_URL` | — | Secret opzionale per un proxy HTTP/HTTPS già disponibile; non è necessario al flusso normale |

## Esecuzione locale facoltativa

Richiede Python 3.12. Nell'ambiente di sviluppo già preparato basta usare `.venv/bin/python`.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
# Inserisci GEMINI_API_KEY in .env solo se vuoi generare in locale.
python app.py --dry-run
python app.py
```

`.env` è escluso da Git. Le variabili d'ambiente prevalgono sui valori di `.env`. Articoli e stato sono sempre relativi alla cartella di `app.py`. Evita esecuzioni locali contemporanee sulla stessa cartella; GitHub Actions serializza automaticamente i propri controlli.

## Verifica

```sh
python -m pip install -r requirements-dev.txt
ruff check .
ruff format --check .
python -m unittest discover -s tests -v
```

I test usano file temporanei e provider simulati: non consumano quota API. Coprono feed, deduplicazione, errori, sottotitoli assenti, input video alternativo, quote Gemini e recupero dopo interruzioni. Il workflow `Test` esegue questi controlli su push e pull request. La generazione reale richiede una chiave valida e va verificata anche sul runner GitHub.

La specifica iniziale resta in `progetto-antigravity.md`. L'implementazione usa l'[SDK Google GenAI mantenuto](https://ai.google.dev/gemini-api/docs/libraries) e l'API a istanze `YouTubeTranscriptApi().fetch(...)`.
