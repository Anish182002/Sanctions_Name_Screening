from flask import Flask, request, render_template, jsonify
import pandas as pd
import requests
import xml.etree.ElementTree as ET
from rapidfuzz import fuzz
import jellyfish
import unicodedata
import re
from bs4 import BeautifulSoup
import urllib3
import io

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# -------------------- Normalize Names -------------------- #
def normalize_name(name):
    if not isinstance(name, str):
        return ['']
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('utf-8')
    aliases = re.split(r'\s*[@|/|\|]\s*', name)
    return [re.sub(r'\b(?:Mr|Mrs|Ms|Dr|Prof)\.\s*', '', alias).strip().lower() for alias in aliases]

# -------------------- Fetch Names From Website -------------------- #
def fetch_names_from_website(url):
    try:
        response = requests.get(url, verify=False, timeout=15)
        response.raise_for_status()
        if 'xml' in response.headers.get('Content-Type', ''):
            tree = ET.fromstring(response.content)
            return pd.Series([elem.text for elem in tree.iter() if elem.text]).dropna()
        else:
            soup = BeautifulSoup(response.text, 'html.parser')
            return pd.Series([tag.get_text(strip=True) for tag in soup.find_all(['p', 'li', 'span'])]).dropna()
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return pd.Series()

# -------------------- Improved Hybrid Match -------------------- #
def hybrid_match(name1_list, name2_list):
    max_score = 0
    for n1 in name1_list:
        for n2 in name2_list:
            fuzz_score = fuzz.ratio(n1, n2)
            jaro_score = jellyfish.jaro_winkler_similarity(n1, n2) * 100
            soundex_bonus = 20 if jellyfish.soundex(n1) == jellyfish.soundex(n2) else 0
            partial_bonus = 10 if n1 in n2 or n2 in n1 else 0

            total_score = fuzz_score * 0.4 + jaro_score * 0.5 + soundex_bonus + partial_bonus
            max_score = max(max_score, total_score)
    return max_score

# -------------------- Screening Logic -------------------- #
def perform_screening(names_list, customers, threshold=70):
    results = []
    for c in customers.dropna():
        c_norm = normalize_name(c)
        for n in names_list.dropna():
            n_norm = normalize_name(n)
            score = hybrid_match(c_norm, n_norm)
            if score >= threshold:
                results.append({'Customer': c, 'Matched Name': n, 'Score': round(score, 2)})
    return pd.DataFrame(results).sort_values(by='Score', ascending=False) if results else pd.DataFrame()

# -------------------- Routes -------------------- #
@app.route('/')
def index():
    return render_template('index.html')  # Make sure index.html exists in a 'templates' folder

@app.route('/screen', methods=['POST'])
def screen():
    file = request.files.get('file')
    website_url = request.form.get('website_url')

    default_websites = [
        "https://scsanctions.un.org/kho39en-all.html",
        "https://www.mha.gov.in/en/banned-organisations",
        "https://www.mha.gov.in/en/page/individual-terrorists-under-uapa",
        "https://www.mha.gov.in/en/commoncontent/unlawful-associations-under-section-3-of-unlawful-activities-prevention-act-1967"
    ]

    if not file:
        return jsonify({"error": "No file uploaded."}), 400

    # Read customer file
    try:
        if file.filename.endswith('.xlsx'):
            customers = pd.concat(pd.read_excel(file, sheet_name=None, engine='openpyxl').values()).stack().astype(str).dropna()
        else:
            customers = pd.read_csv(file).stack().astype(str).dropna()
    except Exception as e:
        return jsonify({"error": f"Failed to read file: {e}"}), 400

    # Fetch sanction list names
    if website_url:
        comparison_names = fetch_names_from_website(website_url)
    else:
        comparison_names = pd.concat([fetch_names_from_website(url) for url in default_websites])

    # Perform screening
    results = perform_screening(comparison_names, customers, threshold=70)
    return results.to_json(orient='records')

# -------------------- Run App -------------------- #
if __name__ == '__main__':
    app.run(debug=True)
