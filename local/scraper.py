import os
import re
import requests
from bs4 import BeautifulSoup
import pdfplumber
from openai import OpenAI

# ---- SETTINGS ----

BASE_URL = "https://admin.sixiemehomme.io"

COOKIES = {
    'PHPSESSID': 'c4295b58af93d547d68f04adcfdc6350'
}

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

RAW_CVS_FOLDER = "raw_cvs"
TXT_CVS_FOLDER = "txt_cvs"

OPENAI_API_KEY = "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"  # ← remplace ici avec ta vraie clé

os.makedirs(RAW_CVS_FOLDER, exist_ok=True)
os.makedirs(TXT_CVS_FOLDER, exist_ok=True)

# ---- STEP 0: Clean folders ----

def clear_folders():
    print("🧹 Nettoyage des dossiers raw_cvs et txt_cvs...")
    for folder in [RAW_CVS_FOLDER, TXT_CVS_FOLDER]:
        for filename in os.listdir(folder):
            file_path = os.path.join(folder, filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"⚠️ Impossible de supprimer {file_path}: {e}")
    print("✅ Dossiers nettoyés.\n")

# ---- HELPERS ----

def sanitize_filename(name):
    return re.sub(r'[^a-zA-Z0-9_\- ]', '', name).strip().replace(' ', '_')

def clean_text_to_single_paragraph(text):
    lines = text.splitlines()
    cleaned_lines = []
    for line in lines:
        line = line.strip()
        if line:
            line = re.sub(r'\s+', ' ', line)
            cleaned_lines.append(line)
    return ' '.join(cleaned_lines)

# ---- STEP 1: Scrape and save mission description ----

def scrape_mission_description(url, output_file="mission.txt"):
    print(f"🌐 Fetching mission description from: {url}")
    response = requests.get(url, cookies=COOKIES, headers=HEADERS)
    if response.status_code != 200:
        print(f"❌ Error fetching {url}: HTTP {response.status_code}")
        return False

    soup = BeautifulSoup(response.text, 'html.parser')
    raw_text = soup.get_text(separator='\n')
    cleaned_text = clean_text_to_single_paragraph(raw_text)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(cleaned_text)
    print(f"✅ Mission description saved and cleaned to {output_file}")
    return True

# ---- STEP 2: Extract candidate profile links ----

def get_candidates_from_mission_page(mission_url):
    print(f"🌐 Fetching mission page: {mission_url}")
    resp = requests.get(mission_url, cookies=COOKIES, headers=HEADERS)
    if resp.status_code != 200:
        print(f"❌ Error fetching mission page: {resp.status_code}")
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')
    mission_app_section = soup.find(id='mission-application')
    if not mission_app_section:
        print("❌ Couldn't find #mission-application (not logged in or wrong page?)")
        return []

    card_body = mission_app_section.find('div', class_='card-body')
    if not card_body:
        print("❌ Couldn't find .card-body inside #mission-application!")
        return []

    application_rows = card_body.find_all('div', class_='application-row')
    candidates = []
    for row in application_rows:
        a_tag = row.find('a', class_='user-email')
        name_tag = row.find('p', class_='user-name')
        if a_tag and name_tag:
            profile_href = a_tag.get('href')
            candidate_name = name_tag.text.strip()
            if profile_href and candidate_name:
                if profile_href.startswith('/'):
                    profile_link = BASE_URL + profile_href
                else:
                    profile_link = profile_href
                print(f"✅ Found candidate: {candidate_name}")
                candidates.append((candidate_name, profile_link))
    print(f"✅ TOTAL candidates found: {len(candidates)}")
    return candidates

# ---- STEP 3: From profile page, find CV PDF ----

def get_cv_link_from_profile(profile_url):
    print(f"  → Fetching profile page: {profile_url}")
    resp = requests.get(profile_url, cookies=COOKIES, headers=HEADERS)
    if resp.status_code != 200:
        print(f"  ❌ Error fetching profile page: {resp.status_code}")
        return None

    soup = BeautifulSoup(resp.text, 'html.parser')
    pdf_link_tag = soup.find('a', href=lambda href: href and href.lower().endswith('.pdf'))
    if pdf_link_tag:
        pdf_href = pdf_link_tag['href']
        if pdf_href.startswith('/'):
            pdf_url = BASE_URL + pdf_href
        else:
            pdf_url = pdf_href
        print(f"  ✅ Found CV PDF link: {pdf_url}")
        return pdf_url
    print(f"  ⚠️ No PDF link found on profile page.")
    return None

# ---- STEP 4: Download PDF ----

def download_pdf(name, pdf_url):
    filename = sanitize_filename(name) + ".pdf"
    path = os.path.join(RAW_CVS_FOLDER, filename)
    print(f"    ↓ Downloading PDF for {name}")
    resp = requests.get(pdf_url, cookies=COOKIES, headers=HEADERS)
    if resp.status_code == 200:
        with open(path, 'wb') as f:
            f.write(resp.content)
        print(f"    ✅ Saved PDF to {path}")
        return path
    else:
        print(f"    ❌ Failed to download PDF: {resp.status_code}")
        return None

# ---- STEP 5: Convert PDF to text ----

def pdf_to_text(pdf_path):
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text

# ---- MAIN WORKFLOW ----

def process_mission_page(mission_url):
    clear_folders()

    # 1. Get and save the mission description
    if not scrape_mission_description(mission_url):
        print("❌ Aborting: couldn't fetch mission description.")
        return

    # 2. Get candidates
    candidates = get_candidates_from_mission_page(mission_url)
    if not candidates:
        print("⚠️ No candidates found.")
        return

    # 3. Process each candidate
    for name, profile_link in candidates:
        print(f"\n=== Processing: {name} ===")
        cv_link = get_cv_link_from_profile(profile_link)
        if not cv_link:
            print(f"⚠️ Skipping {name}: no CV found.")
            continue

        pdf_path = download_pdf(name, cv_link)
        if not pdf_path:
            continue

        raw_text = pdf_to_text(pdf_path)
        if not raw_text.strip():
            print(f"⚠️ No text extracted from {name}'s PDF.")
            continue

        cleaned_text = clean_text_to_single_paragraph(raw_text)
        txt_filename = sanitize_filename(name) + ".txt"
        txt_path = os.path.join(TXT_CVS_FOLDER, txt_filename)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(cleaned_text)
        print(f"✅ Converted and saved {name}'s CV to {txt_path}")

    # 4. Call OpenAI on all collected CVs
    send_to_openai_and_save()

# ---- STEP 6: Send to OpenAI ----

def send_to_openai_and_save():
    print("\n=== 🟣 Préparation du prompt global pour OpenAI ===\n")

    # Lire la mission
    try:
        with open("mission.txt", encoding="utf-8") as f:
            mission_text = f.read()
    except FileNotFoundError:
        print("❌ ERREUR : mission.txt introuvable.")
        return

    # Lire tous les CVs
    all_cvs = []
    for txt_filename in os.listdir(TXT_CVS_FOLDER):
        if not txt_filename.lower().endswith(".txt"):
            continue
        cv_path = os.path.join(TXT_CVS_FOLDER, txt_filename)
        with open(cv_path, encoding="utf-8") as f:
            cv_text = f.read()
        candidate_name = os.path.splitext(txt_filename)[0].replace('_', ' ')
        all_cvs.append((candidate_name, cv_text))

    if not all_cvs:
        print("⚠️ Aucun CV trouvé pour générer le prompt.")
        return

    # Construire le prompt
    prompt_parts = [
        """Tu es un assistant de recrutement. Donne une évaluation pour chacun des candidats par rapport au poste décrit.

Réponds en JSON avec la structure suivante (liste d'objets) :

[
  {
    "nom": "...",
    "score": 0-100,
    "justification": "...",
    "pros": ["..."],
    "cons": ["..."]
  },
  ...
]

# Description du poste:
"""
    ]
    prompt_parts.append(mission_text)
    prompt_parts.append("\n# Candidats et leurs CVs:")

    for name, cv_text in all_cvs:
        prompt_parts.append(f"\n## Candidat: {name}\n{cv_text}")

    full_prompt = "\n".join(prompt_parts)

    print("✅ Prompt généré. Appel à l'API OpenAI en cours...")

    # Appel OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Tu es un assistant RH qui répond toujours en JSON valide."},
            {"role": "user", "content": full_prompt}
        ],
        temperature=0.2
    )

    answer = response.choices[0].message.content.strip()
    print("\n✅ Réponse reçue de l'API OpenAI.")

    # Sauvegarde
    with open("evaluation.json", "w", encoding="utf-8") as f:
        f.write(answer)
    print("\n✅ Résultat JSON sauvegardé dans 'evaluation.json'.")

# ---- MAIN ----

if __name__ == "__main__":
    mission_url = input("Enter the mission page URL: ").strip()
    process_mission_page(mission_url)
