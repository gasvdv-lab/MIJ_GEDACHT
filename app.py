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
    st.error("⚠️ Configuratie-fout in Secrets.")
    st.stop()

# 2. Clients
groq_client = Groq(api_key=GROQ_API_KEY)
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-3-flash-preview')

# 3. GitHub Sync
def get_latest_github_state():
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/database.json"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        return json.loads(base64.b64decode(data["content"]).decode("utf-8")), data["sha"]
    return {}, None

def save_to_github_max(data, sha):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/database.json"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    content_b64 = base64.b64encode(json.dumps(data, indent=4).encode("utf-8")).decode("utf-8")
    payload = {"message": "MAX VOLUME DEEP SCAN", "content": content_b64, "sha": sha}
    resp = requests.put(url, json=payload, headers=headers)
    return resp.status_code in [200, 201]

def add_log(msg):
    """Hulpfunctie voor tijdstempels in de log."""
    ts = datetime.now().strftime("%H:%M:%S")
    if 'scan_logs' not in st.session_state:
        st.session_state.scan_logs = []
    st.session_state.scan_logs.append(f"[{ts}] {msg}")

# --- UI ---
st.set_page_config(page_title="Mij Gedacht AI - MAX", layout="centered")

if os.path.exists("logo.png"): st.image("logo.png", width=250)
elif os.path.exists("foto.png"): st.image("foto.png", width=250)

st.title("🎙️ Mij Gedacht AI (Full Capacity)")

db, current_sha = get_latest_github_state()

query = st.text_input("Vraag de conciërge iets:", placeholder="Stel een héél specifieke vraag...")
if query and db:
    with st.spinner("Het archief wordt doorzocht..."):
        context = "\n\n".join([f"AFLEVERING: {k}\nVERSLAG: {v['summary']}" for k, v in db.items()])
        try:
            prompt = f"Je bent de ultieme Mij Gedacht expert. Antwoord in sappig Vlaams. Gebruik elk detail uit deze context: \n\n{context[:250000]}\n\nVRAAG: {query}"
            res = gemini_model.generate_content(prompt)
            st.info(res.text)
        except:
            st.error("Google quota bereikt.")

with st.sidebar:
    st.header("🚀 Power Beheer")
    st.write(f"Items in archief: {len(db)}")
    
    if st.button("🔥 START DIEPE SCAN (MAX VOLUME)"):
        st.session_state.scan_logs = []
        add_log("Initialiseren van scan...")
        
        feed = feedparser.parse("https://feeds.soundcloud.com/users/soundcloud:users:191935492/sounds.rss")
        new_entries = [e for e in feed.entries if e.title not in db]
        
        if new_entries:
            entry = new_entries[0]
            log_placeholder = st.empty()
            
            with st.status(f"Bezig met Deep Scan: {entry.title}") as status:
                # FASE 1: DOWNLOAD
                add_log(f"Start download van {entry.title}...")
                r = requests.get(entry.enclosures[0].href, stream=True)
                audio_file = "max_temp.mp3"
                with open(audio_file, "wb") as f:
                    size = 0
                    for chunk in r.iter_content(chunk_size=131072):
                        f.write(chunk)
                        size += len(chunk)
                        if size > 24.8 * 1024 * 1024: 
                            add_log(f"Limiet bereikt: {size/1024/1024:.2f} MB gedownload.")
                            break
                
                # FASE 2: GROQ
                add_log("Bestand verzenden naar Groq (Whisper-v3)...")
                try:
                    with open(audio_file, "rb") as f:
                        ts = groq_client.audio.transcriptions.create(
                            file=(audio_file, f), model="whisper-large-v3-turbo", response_format="text", language="nl"
                        )
                    
                    if len(ts) < 100:
                        add_log("FOUT: Transcriptie is te kort.")
                        st.stop()
                    add_log(f"Transcriptie geslaagd ({len(ts)} tekens).")

                    # FASE 3: GEMINI
                    add_log("Tekst analyseren met Gemini (Deep Summary)...")
                    res = gemini_model.generate_content(
                        f"Schrijf een extreem lang, gedetailleerd verslag in sappig Vlaams. "
                        f"Noteer élke grap, naam en anekdote. Minimaal 2500 woorden. "
                        f"Transcriptie: {ts[:500000]}"
                    )
                    
                    if len(res.text) < 500:
                        add_log("FOUT: Gemini output is te beperkt.")
                        st.stop()
                    add_log(f"Analyse voltooid ({len(res.text)} tekens).")

                    # FASE 4: GITHUB
                    add_log("Resultaten synchroniseren met GitHub...")
                    db[entry.title] = {"summary": res.text, "date": entry.published}
                    _, latest_sha = get_latest_github_state()
                    
                    if save_to_github_max(db, latest_sha):
                        add_log("✅ Alles succesvol opgeslagen!")
                        status.update(label="Deep Scan Voltooid!", state="complete")
                        if os.path.exists(audio_file): os.remove(audio_file)
                        time.sleep(2)
                        st.rerun()
                    else:
                        add_log("FOUT: GitHub opslag mislukt.")
                except Exception as e:
                    add_log(f"ERROR: {str(e)}")
                    st.error(f"Fout: {e}")
        else:
            add_log("Geen nieuwe afleveringen gevonden.")

    # Toon de logs in de zijbalk
    if 'scan_logs' in st.session_state:
        st.divider()
        st.subheader("Systeem Log")
        for log in reversed(st.session_state.scan_logs):
            st.caption(log)
