import streamlit as st
import feedparser
import os
import requests
import json
import base64
import time
from groq import Groq
import google.generativeai as genai

# 1. Veilig inladen van secrets
try:
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    GITHUB_REPO = st.secrets["GITHUB_REPO"]
except Exception:
    st.error("⚠️ Configuratie niet compleet.")
    st.stop()

# 2. Clients
groq_client = Groq(api_key=GROQ_API_KEY)
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-3-flash-preview')

# 3. GitHub Sync (Altijd de nieuwste versie ophalen voor het schrijven)
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
    payload = {"message": "MAX VOLUME UPDATE", "content": content_b64, "sha": sha}
    resp = requests.put(url, json=payload, headers=headers)
    return resp.status_code in [200, 201]

# --- UI ---
st.set_page_config(page_title="Mij Gedacht AI - MAX", layout="centered")

if os.path.exists("logo.png"): st.image("logo.png", width=250)
elif os.path.exists("foto.png"): st.image("foto.png", width=250)

st.title("🎙️ Mij Gedacht AI (Full Capacity)")

db, current_sha = get_latest_github_state()

query = st.text_input("Doorzoek het volledige archief:", placeholder="Vraag iets heel specifieks...")
if query and db:
    with st.spinner("Maximale analyse van het archief..."):
        # We gebruiken nu 200.000 karakters context voor de zoekopdracht
        context = "\n\n".join([f"AFLEVERING: {k}\nINHOUD: {v['summary']}" for k, v in db.items()])
        try:
            prompt = f"Je bent de ultieme Mij Gedacht expert. Antwoord zeer uitgebreid, met humor en in sappig Vlaams. Gebruik ALLE details uit de context: \n\n{context[:200000]}\n\nVRAAG: {query}"
            res = gemini_model.generate_content(prompt)
            st.info(res.text)
        except:
            st.error("Quota bereikt. Google heeft even rust nodig.")

with st.sidebar:
    st.header("🚀 Power Beheer")
    if st.button("🔥 START MAX VOLUME SCAN"):
        feed = feedparser.parse("https://feeds.soundcloud.com/users/soundcloud:users:191935492/sounds.rss")
        new_entries = [e for e in feed.entries if e.title not in db]
        
        if new_entries:
            entry = new_entries[0]
            with st.status(f"Bezig met Deep Scan: {entry.title}"):
                # We gaan naar de absolute grens van Groq (24.9MB)
                r = requests.get(entry.enclosures[0].href, stream=True)
                audio_file = "max_temp.mp3"
                with open(audio_file, "wb") as f:
                    size = 0
                    for chunk in r.iter_content(chunk_size=131072):
                        f.write(chunk)
                        size += len(chunk)
                        if size > 24.9 * 1024 * 1024: break
                
                try:
                    with open(audio_file, "rb") as f:
                        ts = groq_client.audio.transcriptions.create(
                            file=(audio_file, f), model="whisper-large-v3-turbo", response_format="text", language="nl"
                        )
                    
                    # Gemini krijgt nu tot 500.000 karakters (vrijwel de hele transcriptie)
                    # We dwingen een 'verslag' af ipv een samenvatting
                    res = gemini_model.generate_content(
                        f"Schrijf een extreem uitgebreid verslag van deze podcast in sappig Vlaams. "
                        f"Noteer elke grap, elk verhaal, elke vernoemde persoon en elke anekdote tot in het kleinste detail. "
                        f"Maak er een tekst van minstens 2000 woorden van: {ts[:500000]}"
                    )
                    
                    db[entry.title] = {"summary": res.text, "date": entry.published}
                    
                    # Opnieuw SHA ophalen net voor schrijven om errors te voorkomen
                    _, latest_sha = get_latest_github_state()
                    if save_to_github_max(db, latest_sha):
                        st.success("✅ MAX VOLUME SCAN OPGESLAGEN!")
                        if os.path.exists(audio_file): os.remove(audio_file)
                        time.sleep(1)
                        st.rerun()
                except Exception as e:
                    st.error(f"Fout: {e}")
