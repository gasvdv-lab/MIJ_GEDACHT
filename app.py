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
    st.error("⚠️ API sleutels of GitHub Secrets missen!")
    st.stop()

# 2. Clients initialiseren
groq_client = Groq(api_key=GROQ_API_KEY)
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-3-flash-preview')

# 3. GitHub Functies
def get_github_db():
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/database.json"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        content = base64.b64decode(data["content"]).decode("utf-8")
        return json.loads(content), data["sha"]
    return {}, None

def save_to_github(data, sha=None):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/database.json"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    payload = {
        "message": "Update podcast database",
        "content": base64.b64encode(json.dumps(data, indent=4).encode("utf-8")).decode("utf-8")
    }
    if sha: payload["sha"] = sha
    requests.put(url, json=payload, headers=headers)

# Layout
st.set_page_config(page_title="Mij Gedacht AI Zoekmachine", page_icon="🔍", layout="centered")
st.title("🔍 Mij Gedacht AI")
st.caption("Stel vragen over de podcast en ik zoek het op in het archief.")

db, current_sha = get_github_db()

# --- GOOGLE-ACHTIGE ZOEKFUNCTIE ---
query = st.text_input("Waar zoek je informatie over?", placeholder="Bijv: Wat zeiden ze over de dagschotel van Xavier?")

if query and db:
    with st.spinner("Het archief doorzoeken..."):
        # We maken een grote tekstblok van alle samenvattingen voor context
        context_text = "\n".join([f"Aflevering {k}: {v['summary']}" for k, v in db.items()])
        
        prompt = f"""
        Je bent de officiële Mij Gedacht AI-agent. Gebruik enkel de volgende context om de vraag te beantwoorden.
        Als de informatie niet in de context staat, zeg dan vriendelijk dat de podcasters dit (nog) niet besproken hebben in de geanalyseerde afleveringen.
        
        CONTEXT:
        {context_text[:15000]}
        
        VRAAG:
        {query}
        """
        
        try:
            response = gemini_model.generate_content(prompt)
            st.markdown("### 🤖 De Agent zegt:")
            st.write(response.text)
        except Exception as e:
            st.error(f"Fout bij beantwoorden: {e}")

st.divider()

# --- BEHEER SECTIE (In de zijbalk) ---
with st.sidebar:
    st.header("⚙️ Beheer")
    st.write(f"Archief grootte: {len(db)} afleveringen")
    
    if st.button("🔄 Scan nieuwe aflevering"):
        feed = feedparser.parse("https://feeds.soundcloud.com/users/soundcloud:users:191935492/sounds.rss")
        new_entries = [e for e in feed.entries if e.title not in db]
        
        if new_entries:
            entry = new_entries[0]
            with st.status(f"Analyseren: {entry.title}"):
                # Download & Transcribe (Zelfde logica als voorheen)
                audio_url = entry.enclosures[0].href
                r = requests.get(audio_url, stream=True)
                with open("temp.mp3", "wb") as f:
                    for chunk in r.iter_content(1024*1024):
                        f.write(chunk)
                        if os.path.getsize("temp.mp3") > 10*1024*1024: break
                
                with open("temp.mp3", "rb") as f:
                    ts = groq_client.audio.transcriptions.create(
                        file=("temp.mp3", f.read()),
                        model="whisper-large-v3-turbo",
                        response_format="text", language="nl"
                    )
                
                res = gemini_model.generate_content(f"Vat kort samen in het Vlaams: {ts[:8000]}")
                db[entry.title] = {"summary": res.text, "date": entry.published}
                save_to_github(db, current_sha)
                os.remove("temp.mp3")
                st.success("Opgeslagen!")
                st.rerun()
        else:
            st.success("Alles is bijgewerkt!")
