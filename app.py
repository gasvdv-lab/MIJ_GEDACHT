import streamlit as st
import feedparser
import os
import requests
import json
import base64
import time
from datetime import datetime
from groq import Groq
import google.generativeai as genai

# 1. Veilig inladen van secrets
try:
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    GITHUB_REPO = st.secrets["GITHUB_REPO"]
except Exception:
    st.error("⚠️ Configuratie-fout in Secrets. Controleer je instellingen in het Streamlit dashboard.")
    st.stop()

# 2. Clients & Model Auto-Select
groq_client = Groq(api_key=GROQ_API_KEY)
genai.configure(api_key=GEMINI_API_KEY)

def get_best_model():
    """Zoekt dynamisch naar het beste beschikbare model om 404's te vermijden."""
    try:
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        # Prioriteit lijst
        for preference in ['models/gemini-1.5-flash-latest', 'models/gemini-1.5-flash', 'models/gemini-pro']:
            if preference in available_models:
                return preference
        return available_models[0] if available_models else 'gemini-pro'
    except Exception:
        return 'gemini-1.5-flash' # Fallback naar meest waarschijnlijke

model_name = get_best_model()
gemini_model = genai.GenerativeModel(model_name)

# 3. GitHub Sync met Conflict Handling
def get_latest_github_state():
    repo = GITHUB_REPO.strip()
    url = f"https://api.github.com/repos/{repo}/contents/database.json"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Cache-Control": "no-cache"
    }
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            content = base64.b64decode(data["content"]).decode("utf-8")
            return json.loads(content), data["sha"]
    except Exception:
        pass
    return {}, None

def save_to_github_max(data):
    """Slaat data op en probeert bij een conflict (409) opnieuw met de nieuwste SHA."""
    repo = GITHUB_REPO.strip()
    url = f"https://api.github.com/repos/{repo}/contents/database.json"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # 1. Haal verse SHA op
    current_state = requests.get(url, headers=headers)
    sha = current_state.json().get("sha") if current_state.status_code == 200 else None
    
    content_json = json.dumps(data, indent=4)
    content_b64 = base64.b64encode(content_json.encode("utf-8")).decode("utf-8")
    
    payload = {
        "message": f"Deep Scan Update: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "content": content_b64,
        "sha": sha
    }
    
    resp = requests.put(url, json=payload, headers=headers)
    
    # 2. Conflict handling (als iemand anders net heeft geüpdatet)
    if resp.status_code == 409:
        add_log("⚠️ Conflict gedetecteerd, opnieuw proberen...")
        return save_to_github_max(data) 
        
    if resp.status_code not in [200, 201]:
        st.session_state.last_error = f"GitHub Error {resp.status_code}: {resp.text}"
        return False
    return True

def add_log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    if 'scan_logs' not in st.session_state:
        st.session_state.scan_logs = []
    st.session_state.scan_logs.append(f"[{ts}] {msg}")

# --- UI ---
st.set_page_config(page_title="Mij Gedacht AI - MAX", layout="centered")

if 'db' not in st.session_state:
    st.session_state.db, _ = get_latest_github_state()

st.title("🎙️ Mij Gedacht AI (Deep Scan)")
st.caption(f"Actief model: {model_name}")

query = st.text_input("Vraag de conciërge iets:", placeholder="Stel een vraag...")
if query and st.session_state.db:
    with st.spinner("Zoeken..."):
        # Context management: We nemen de meest recente verslagen eerst
        context_items = []
        current_length = 0
        for k, v in reversed(list(st.session_state.db.items())):
            entry_text = f"AFLEVERING: {k}\nVERSLAG: {v['summary']}\n\n"
            if current_length + len(entry_text) < 400000: # Veiligheidsmarge
                context_items.append(entry_text)
                current_length += len(entry_text)
        
        context = "".join(context_items)
        try:
            res = gemini_model.generate_content(f"Antwoord in sappig Vlaams: {query}\n\nContext:\n{context}")
            st.info(res.text)
        except Exception as e:
            st.error(f"Gemini Error: {e}")

with st.sidebar:
    st.header("🚀 Beheer")
    if st.button("🔥 START DIEPE SCAN"):
        st.session_state.scan_logs = []
        feed = feedparser.parse("https://feeds.soundcloud.com/users/soundcloud:users:191935492/sounds.rss")
        
        db = st.session_state.db
        new_entries = [e for e in feed.entries if e.title not in db]
        
        if new_entries:
            entry = new_entries[0]
            with st.status(f"Scan: {entry.title}") as status:
                add_log(f"Start download van {entry.title}...")
                try:
                    r = requests.get(entry.enclosures[0].href, stream=True, timeout=30)
                    r.raise_for_status()
                    audio_file = "temp.mp3"
                    with open(audio_file, "wb") as f:
                        size = 0
                        for chunk in r.iter_content(chunk_size=131072):
                            f.write(chunk)
                            size += len(chunk)
                            if size > 24.8 * 1024 * 1024: break
                    
                    if size < 1000: # Te klein om audio te zijn
                        raise ValueError("Download lijkt mislukt of bestand is leeg.")
                except Exception as e:
                    add_log(f"Download Error: {e}")
                    status.update(label="Download mislukt", state="error")
                    st.stop()
                
                try:
                    add_log("Verzenden naar Groq (Whisper)...")
                    with open(audio_file, "rb") as f:
                        ts = groq_client.audio.transcriptions.create(
                            file=(audio_file, f), 
                            model="whisper-large-v3-turbo", 
                            response_format="text", 
                            language="nl"
                        )
                    
                    add_log(f"Gemini analyseert {len(ts)} tekens...")
                    # Beperk transcript voor Gemini als het extreem lang is
                    res = gemini_model.generate_content(
                        f"Schrijf een extreem uitgebreid verslag van deze podcast in sappig Vlaams: {ts[:300000]}"
                    )
                    
                    add_log("Synchroniseren met GitHub...")
                    db[entry.title] = {"summary": res.text, "date": entry.published}
                    
                    if save_to_github_max(db):
                        st.session_state.db = db
                        add_log("✅ Succesvol opgeslagen!")
                        status.update(label="Voltooid!", state="complete")
                        if os.path.exists(audio_file): os.remove(audio_file)
                        time.sleep(1)
                        st.rerun()
                    else:
                        add_log(f"❌ Opslag mislukt: {st.session_state.get('last_error', 'Onbekende fout')}")
                except Exception as e:
                    add_log(f"Verwerkingsfout: {e}")
        else:
            st.info("Geen nieuwe afleveringen.")

    if 'scan_logs' in st.session_state:
        st.divider()
        for log in reversed(st.session_state.scan_logs):
            st.caption(log)
