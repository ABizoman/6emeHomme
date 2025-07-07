import os
import re
import requests
from bs4 import BeautifulSoup
import pdfplumber

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

os.makedirs(RAW_CVS_FOLDER, exist_ok=True)
os.makedirs(TXT_CVS_FOLDER, exist_ok=True)


# ---- HELPERS ----

def sanitize_filename(name):
    return re.sub(r'[^a-zA-Z0-9_\- ]', '', name).strip().replace(' ', '_')


def clean_text_to_single_paragraph(text):
    """
    Collapse messy multiline text into a single clean paragraph.
    """
    lines = text.splitlines()
    cleaned_lines = []

    for line in lines:
        line = line.strip()
        if line:
            # Collapse multiple spaces
            line = re.sub(r'\s+', ' ', line)
            cleaned_lines.append(line)

    return ' '.join(cleaned_lines)


def get_candidates_from_mission_page(mission_url):
    print(f"🌐 Fetching mission page: {mission_url}")
    resp = requests.get(mission_url, cookies=COOKIES, headers=HEADERS)
    if resp.status_code != 200:
        print(f"❌ Error fetching mission page: {resp.status_code}")
        return []

    soup = BeautifulSoup(resp.text, 'html.parser')

    mission_app_section = soup.find(id='mission-application')
    if not mission_app_section:
        print("❌ Couldn't find #mission-application section (maybe not logged in?)")
        return []

    card_body = mission_app_section.find('div', class_='card-body')
    if not card_body:
        print("❌ Couldn't find .card-body inside #mission-application!")
        return []

    # Real children only (avoid data-prototype junk)
    application_rows = []
    for child in card_body.find_all('div', recursive=False):
        if child.get('class') and 'application-row' in child['class']:
            application_rows.append(child)

    if not application_rows:
        # fallback
        application_rows = card_body.find_all('div', class_='application-row')

    candidates = []
    for row in application_rows:
        a_tag = row.find('a', class_='user-email')
        name_tag = row.find('p', class_='user-name')

        if a_tag and name_tag:
            profile_href = a_tag.get('href')
            candidate_name = name_tag.text.strip()

            if not profile_href or not candidate_name:
                continue

            if profile_href.startswith('/'):
                profile_link = BASE_URL + profile_href
            else:
                profile_link = profile_href

            print(f"✅ Found candidate: {candidate_name}")
            candidates.append((candidate_name, profile_link))

    print(f"✅ TOTAL candidates found: {len(candidates)}")
    return candidates


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


def pdf_to_text(pdf_path):
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text


def process_mission_page(mission_url):
    candidates = get_candidates_from_mission_page(mission_url)
    if not candidates:
        print("⚠️ No candidates found.")
        return

    for name, profile_link in candidates:
        print(f"\n=== Processing: {name} ===")

        # 1. Get CV PDF link
        cv_link = get_cv_link_from_profile(profile_link)
        if not cv_link:
            print(f"⚠️ Skipping {name}: no CV found.")
            continue

        # 2. Download PDF
        pdf_path = download_pdf(name, cv_link)
        if not pdf_path:
            continue

        # 3. Convert PDF to raw text
        raw_text = pdf_to_text(pdf_path)
        if not raw_text.strip():
            print(f"⚠️ No text extracted from {name}'s PDF.")
            continue

        # 4. Clean text to single paragraph
        cleaned_text = clean_text_to_single_paragraph(raw_text)

        # 5. Save cleaned text
        txt_filename = sanitize_filename(name) + ".txt"
        txt_path = os.path.join(TXT_CVS_FOLDER, txt_filename)
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(cleaned_text)
        print(f"✅ Converted and saved {name} to {txt_path}")


# ---- MAIN ----

if __name__ == "__main__":
    mission_url = input("Enter the mission page URL: ").strip()
    process_mission_page(mission_url)
