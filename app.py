import os
import re
import requests
import pdfplumber
from flask import Flask, render_template, request, jsonify
from bs4 import BeautifulSoup
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# launch wifi server with: flask run --host=0.0.0.0
# launch local server with: python app.py

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

app = Flask(__name__)

# Your admin session cookie
PHPSESSID = 'c4295b58af93d547d68f04adcfdc6350'
BASE_URL = "https://admin.sixiemehomme.io"

COOKIES = {"PHPSESSID": PHPSESSID}
HEADERS = {"User-Agent": "Mozilla/5.0"}

# === Model list with prices ===
AVAILABLE_MODELS = [
    {"id": "gpt-4.1-nano", "label": "GPT-4.1 nano (~$0.10/1M in, ~$0.40/1M out)"},
    {"id": "gpt-4.1-mini", "label": "GPT-4.1 mini (~$0.40/1M in, ~$1.60/1M out)"},
    {"id": "gpt-3.5-turbo", "label": "GPT-3.5 Turbo (~$0.50/1K in, ~$1.50/1K out)"},
     {"id": "gpt-4.1", "label": "GPT-4.1 (~$2.00/1M in, ~$8.00/1M out)"},
    {"id": "gpt-4o", "label": "GPT-4o (~$5/1K in, ~$15/1K out)"},
    {"id": "gpt-4", "label": "GPT-4 (~$10/1K in, ~$30/1K out)"},
]

# === Helpers ===
def clean_text(text):
    lines = text.splitlines()
    cleaned_lines = [re.sub(r'\s+', ' ', line.strip()) for line in lines if line.strip()]
    return ' '.join(cleaned_lines)

def scrape_mission_description(url):
    resp = requests.get(url, cookies=COOKIES, headers=HEADERS)
    if resp.status_code != 200:
        raise Exception(f"Failed to fetch mission page: {resp.status_code}")
    soup = BeautifulSoup(resp.text, 'html.parser')
    return clean_text(soup.get_text(separator='\n'))

def get_cv_link_from_profile(profile_url):
    resp = requests.get(profile_url, cookies=COOKIES, headers=HEADERS)
    if resp.status_code != 200:
        raise Exception(f"Error fetching profile page: {resp.status_code}")
    soup = BeautifulSoup(resp.text, 'html.parser')
    pdf_link_tag = soup.find('a', href=lambda href: href and href.lower().endswith('.pdf'))
    if pdf_link_tag:
        href = pdf_link_tag['href']
        return BASE_URL + href if href.startswith('/') else href
    return None

def download_and_extract_pdf(pdf_url):
    resp = requests.get(pdf_url, cookies=COOKIES, headers=HEADERS)
    if resp.status_code != 200:
        return ""
    with open("temp_cv.pdf", "wb") as f:
        f.write(resp.content)
    text = ""
    with pdfplumber.open("temp_cv.pdf") as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return clean_text(text)

# === Routes ===
@app.route('/models')
def models():
    return jsonify(AVAILABLE_MODELS)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/evaluate', methods=['POST'])
def evaluate():
    data = request.json
    mission_url = data.get('mission_url', '').strip()
    candidate_url = data.get('candidate_url', '').strip()
    prompt_intro = data.get('prompt_intro', '').strip()
    selected_model = data.get('selected_model', '').strip()

    if not mission_url or not candidate_url or not prompt_intro or not selected_model:
        return jsonify({"error": "Tous les champs sont requis."}), 400

    try:
        mission_description = scrape_mission_description(mission_url)
        cv_pdf_link = get_cv_link_from_profile(candidate_url)
        if not cv_pdf_link:
            return jsonify({"error": "CV PDF introuvable pour ce candidat."})

        candidate_cv_text = download_and_extract_pdf(cv_pdf_link)
        if not candidate_cv_text:
            return jsonify({"error": "Impossible d'extraire le texte du CV."})

        final_prompt = f"""{prompt_intro}

Réponds en JSON avec la structure suivante :

{{
  "nom": "...",
  "score": 0-100,
  "justification": "...",
  "pros": ["..."],
  "cons": ["..."]
}}

Description du poste:
{mission_description}

CV du candidat:
{candidate_cv_text}
"""

        response = client.chat.completions.create(
            model=selected_model,
            messages=[
                {"role": "system", "content": "Tu es un assistant RH qui répond toujours en JSON valide."},
                {"role": "user", "content": final_prompt}
            ],
            temperature=0.2
        )
        result = response.choices[0].message.content.strip()
        return jsonify({"result": result})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
