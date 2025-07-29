import os
import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
import concurrent.futures
import numpy as np
import fitz  # PyMuPDF
from rapidfuzz import fuzz
import jellyfish
import unicodedata
import re
from bs4 import BeautifulSoup
import urllib3
import io
import re
import unicodedata

def clean_name(name):
    name = unicodedata.normalize("NFKD", name)        # Normalize unicode
    name = re.sub(r'^\d+\.', '', name)                # Remove leading numbers like "4."
    name = re.sub(r'[^\w\s]', '', name)               # Remove punctuation
    name = re.sub(r'\s+', ' ', name)                  # Replace multiple spaces with single space
    return name.strip().lower()

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_WEBSITES = [
    "https://scsanctions.un.org/resources/xml/en/consolidated.xml",
    "https://www.mha.gov.in/en/banned-organisations",
    "https://www.mha.gov.in/en/page/individual-terrorists-under-uapa",
    "https://www.mha.gov.in/en/commoncontent/unlawful-associations-under-section-3-of-unlawful-activities-prevention-act-1967"
]

# Variant Map for alternate spellings
VARIANT_MAP = {
    "daud": "dawood",
    "mohammed": "muhammad",
    "yusuf": "yousuf",
    "mohamad": "muhammad",
    "sayed": "syed"
}

# Normalize name for matching
# Normalize and tokenize name
def normalize_name(name):
    if not isinstance(name, str):
        return []
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('utf-8')
    name = re.sub(r'\b(?:Mr|Mrs|Ms|Dr|Prof)\.?\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'[^\w\s]', '', name)
    return name.lower().strip().split()


# Fetch and split names from websites
@st.cache_data
def fetch_names_from_website(url):
    try:
        response = requests.get(url, verify=False, timeout=10)
        if 'xml' in response.headers.get('Content-Type', ''):
            tree = ET.fromstring(response.content)
            return pd.Series([elem.text for elem in tree.iter() if elem.text]).dropna()
        else:
            soup = BeautifulSoup(response.text, 'html.parser')
            raw_text = [tag.get_text(strip=True) for tag in soup.find_all('p')]
            split_names = []
            for para in raw_text:
                parts = re.split(r'\s*[@|/|,]\s*', para)
                split_names.extend([p.strip() for p in parts if p.strip()])
            return pd.Series(split_names).dropna()
    except Exception as e:
        st.warning(f"Error fetching from {url}: {e}")
        return pd.Series([])

# Fetch names from all default websites
@st.cache_data
def fetch_all_default_names():
    all_names = pd.Series([])
    for url in DEFAULT_WEBSITES:
        names = fetch_names_from_website(url)
        all_names = pd.concat([all_names, names], ignore_index=True)
    return all_names.dropna()

# Extract text from PDF
def extract_text_from_pdf(file):
    doc = fitz.open(stream=file.read(), filetype="pdf")
    text = "\n".join(page.get_text("text") for page in doc)
    return pd.Series(re.findall(r'\b[A-Za-z]+(?: [A-Za-z]+)*\b', text)).dropna()

# Advanced hybrid match using token-wise phonetic + fuzzy + Jaro-Winkler
def hybrid_match(name1_tokens, name2_tokens):
    if not name1_tokens or not name2_tokens:
        return 0

    scores = []
    for t1 in name1_tokens:
        best_score = 0
        for t2 in name2_tokens:
            # Basic scores
            fuzz_score = fuzz.ratio(t1, t2)
            jaro_score = jellyfish.jaro_winkler_similarity(t1, t2) * 100
            soundex_score = 20 if jellyfish.soundex(t1) == jellyfish.soundex(t2) else 0

            # Weighted average
            token_score = (fuzz_score * 0.3 + jaro_score * 0.5 + soundex_score)
            best_score = max(best_score, token_score)
        scores.append(best_score)

    # Final score is average of best scores for each token in name1
    return sum(scores) / len(scores)


# Parallel name screening
def parallel_screening(names_list, customers, threshold=55):
    results = []
    
    def process_chunk(chunk):
        return [
            {'Customer': c, 'Matched Name': n, 'Score': hybrid_match(normalize_name(c), normalize_name(n))}
            for c in chunk for n in names_list if hybrid_match(normalize_name(c), normalize_name(n)) >= threshold
        ]
    
    customer_chunks = np.array_split(customers, os.cpu_count())
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [executor.submit(process_chunk, chunk) for chunk in customer_chunks]
        for future in concurrent.futures.as_completed(futures):
            results.extend(future.result())
    
    return pd.DataFrame(results).sort_values(by='Score', ascending=False) if results else pd.DataFrame()

# Streamlit App
st.title('Sanctions Name Screening System')
source_option = st.radio("Choose Screening Type:", ('Default List (All Websites)', 'Custom Website', 'From Another File'))
file = st.file_uploader("Upload Customer File (Excel, CSV, PDF)", type=["xlsx", "csv", "pdf"])

if source_option == 'Custom Website':
    website_url = st.text_input("Enter Website URL for Screening")
elif source_option == 'From Another File':
    compare_file = st.file_uploader("Upload Comparison File (Excel, CSV, PDF)", type=["xlsx", "csv", "pdf"])

output_format = st.radio("Choose Output Format:", ('xlsx', 'csv'))
threshold = st.slider("Set Match Threshold (higher = stricter)", min_value=0, max_value=100, value=60)

if st.button('Run Screening') and file:
    if file.name.endswith('.xlsx'):
        customers = pd.concat(pd.read_excel(file, sheet_name=None, engine='openpyxl').values()).stack().astype(str).dropna()
    elif file.name.endswith('.csv'):
        customers = pd.read_csv(file).stack().astype(str).dropna()
    else:
        customers = extract_text_from_pdf(file)

    if source_option == 'Default List (All Websites)':
        comparison_names = fetch_all_default_names()
    elif source_option == 'Custom Website' and website_url:
        comparison_names = fetch_names_from_website(website_url)
    elif source_option == 'From Another File' and compare_file:
        if compare_file.name.endswith('.xlsx'):
            comparison_names = pd.concat(pd.read_excel(compare_file, sheet_name=None, engine='openpyxl').values()).stack().astype(str).dropna()
        elif compare_file.name.endswith('.csv'):
            comparison_names = pd.read_csv(compare_file).stack().astype(str).dropna()
        else:
            comparison_names = extract_text_from_pdf(compare_file)
    else:
        st.warning('No source selected or invalid input.')
        comparison_names = pd.Series([])

    results = parallel_screening(comparison_names, customers, threshold=threshold)
    if not results.empty:
        st.success('Screening Completed! Download results below:')
        st.dataframe(results)

        if output_format == 'xlsx':
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                results.to_excel(writer, index=False)
            output.seek(0)
            st.download_button("Download Results", data=output, file_name="screening_results.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else:
            output = io.StringIO()
            results.to_csv(output, index=False)
            st.download_button("Download Results", data=output.getvalue(), file_name="screening_results.csv", mime="text/csv")
    else:
        st.warning('No matches found. Check input data or URL.')
