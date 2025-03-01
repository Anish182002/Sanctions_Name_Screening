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

def normalize_name(name):
    if not isinstance(name, str):
        return ['']
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('utf-8')
    aliases = re.split(r'\s*[@|/|\|]\s*', name)
    return [re.sub(r'\b(?:Mr|Mrs|Ms|Dr|Prof)\.\s', '', alias).strip().lower() for alias in aliases]

def fetch_names_from_website(url):
    response = requests.get(url, verify=False)
    if 'xml' in response.headers.get('Content-Type', ''):
        tree = ET.fromstring(response.content)
        return pd.Series([elem.text for elem in tree.iter() if elem.text]).dropna()
    else:
        soup = BeautifulSoup(response.text, 'html.parser')
        return pd.Series([tag.get_text(strip=True) for tag in soup.find_all('p')]).dropna()

def hybrid_match(name1_list, name2_list):
    return max(
        (fuzz.ratio(n1, n2) * 0.4 + jellyfish.jaro_winkler_similarity(n1, n2) * 100 * 0.5 + (
            10 if jellyfish.soundex(n1) == jellyfish.soundex(n2) else 0))
        for n1 in name1_list for n2 in name2_list
    )

def perform_screening(names_list, customers, threshold=55):
    results = [
        {'Customer': c, 'Matched Name': n, 'Score': hybrid_match(normalize_name(c), normalize_name(n))}
        for c in customers.dropna()
        for n in names_list.dropna()
        if hybrid_match(normalize_name(c), normalize_name(n)) >= threshold
    ]
    return pd.DataFrame(results).sort_values(by='Score', ascending=False) if results else pd.DataFrame()

@app.route('/')
def index():
    return render_template('index.html')

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

    if file.filename.endswith('.xlsx'):
        customers = pd.concat(pd.read_excel(file, sheet_name=None, engine='openpyxl').values()).stack().astype(str).dropna()
    else:
        customers = pd.read_csv(file).stack().astype(str).dropna()

    if website_url:
        comparison_names = fetch_names_from_website(website_url)
    else:
        comparison_names = pd.concat([fetch_names_from_website(url) for url in default_websites])

    results = perform_screening(comparison_names, customers)
    return results.to_json(orient='records')

if __name__ == '__main__':
    app.run(debug=True)
