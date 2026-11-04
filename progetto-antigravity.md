# Specifica di Progetto per Google Antigravity

**Nome Progetto:** Lazio Gazzetta AI Automation  
**Obiettivo:** Pipeline automatica per monitorare il canale YouTube "Paolo Colantoni - Dentro la Lazio", estrarre la trascrizione di ogni nuovo video ed elaborare un articolo in stile *La Gazzetta dello Sport* tramite Gemini 2.5 Flash su GitHub Actions.

---

## 1. Architettura Tecnologica

- **Runtime:** Python 3.10+
- **Librerie Principali:** `feedparser`, `youtube-transcript-api`, `google-generativeai`
- **Orchestratore:** GitHub Actions (Cron schedule: ogni 2 ore)
- **Modello AI:** Gemini 2.5 Flash via Google AI Studio API
- **Destinazione Articoli:** Cartella `articoli/` nella repository (.md)

---

## 2. Struttura del Progetto

```text
.
├── .github/
│   └── workflows/
│       └── auto_article.yml
├── articoli/
├── app.py
├── processed_videos.txt
├── requirements.txt
└── README.md
```

---

## 3. File del Progetto

### File `requirements.txt`
```text
feedparser
youtube-transcript-api
google-generativeai
```

### File `app.py`
```python
import os
import re
import feedparser
from youtube_transcript_api import YouTubeTranscriptApi
import google.generativeai as genai

# Feed RSS del canale Paolo Colantoni - Dentro la Lazio
FEED_URL = "INSERISCI_URL_FEED_RSS_YOUTUBE_QUI"
PROCESSED_FILE = "processed_videos.txt"

def get_latest_video():
    feed = feedparser.parse(FEED_URL)
    if not feed.entries:
        print("Nessun video trovato nel feed.")
        return None, None
    latest = feed.entries[0]
    video_id = latest.yt_videoid if hasattr(latest, 'yt_videoid') else latest.id.split(':')[-1]
    title = latest.title
    return video_id, title

def is_processed(video_id):
    if not os.path.exists(PROCESSED_FILE):
        return False
    with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
        processed = f.read().splitlines()
    return video_id in processed

def mark_processed(video_id):
    with open(PROCESSED_FILE, "a", encoding="utf-8") as f:
        f.write(f"{video_id}\n")

def get_transcript(video_id):
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['it'])
        return " ".join([item['text'] for item in transcript_list])
    except Exception as e:
        print(f"Trascrizione non disponibile: {e}")
        return None

def generate_article(title, transcript):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY mancante nelle variabili d'ambiente!")
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    prompt = f"""
Sei un giornalista di punta de "La Gazzetta dello Sport", sponda biancoceleste.
Scrivi un articolo brillante, avvincente e tecnico basato sulla trascrizione di questo video di Paolo Colantoni.

Titolo Video: {title}
Trascrizione:
{transcript}

Linee guida:
- Titolo d'impatto tipico della Gazzetta dello Sport (con occhiello e catenaccio).
- Tono: appassionato, analitico e giornalistico.
- Struttura in paragrafi ben definiti e sottotitoli in grassetto.
- Formato di output: Markdown.
"""
    response = model.generate_content(prompt)
    return response.text

def main():
    video_id, title = get_latest_video()
    if not video_id:
        return

    print(f"Ultimo video: {title} ({video_id})")

    if is_processed(video_id):
        print("Video già trasformato in articolo. Nessun aggiornamento necessario.")
        return

    print("Nuovo video rilevato! Estraggo i sottotitoli...")
    transcript = get_transcript(video_id)
    if not transcript:
        return

    print("Generazione articolo in stile Gazzetta con Gemini AI...")
    article_md = generate_article(title, transcript)

    os.makedirs("articoli", exist_ok=True)
    safe_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')
    filename = f"articoli/{video_id}_{safe_title}.md"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(article_md)
    
    mark_processed(video_id)
    print(f"Articolo creato con successo: {filename}")

if __name__ == "__main__":
    main()
```

### File `.github/workflows/auto_article.yml`
```yaml
name: Automazione Articoli Lazio

on:
  schedule:
    - cron: '0 */2 * * *'  # Esegue ogni 2 ore
  workflow_dispatch:        # Permette avvio manuale

jobs:
  run-automation:
    runs-on: ubuntu-latest
    steps:
      - name: Scarica repository
        uses: actions/checkout@v4

      - name: Imposta Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Installa pacchetti
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Genera Articolo
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        run: python app.py

      - name: Salva i nuovi articoli su GitHub
        run: |
          git config --global user.name "github-actions-bot"
          git config --global user.email "bot@example.com"
          git add .
          git diff-index --quiet HEAD || git commit -m "Auto: generato nuovo articolo Gazzetta"
          git push
```

---

## 4. Istruzioni per l'Agente AI

1. Inizializzare la struttura delle cartelle nella repository.
2. Posizionare `requirements.txt`, `app.py` e `.github/workflows/auto_article.yml`.
3. Inserire nelle Secrets di GitHub (`GEMINI_API_KEY`) la chiave API di Google AI Studio.
4. Eseguire il workflow in background per salvare i file nella cartella `articoli/`.
