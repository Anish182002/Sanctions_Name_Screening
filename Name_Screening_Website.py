import os

# Ensure all dependencies are installed in Streamlit Cloud
os.system("pip install -r requirements.txt")

import streamlit as st
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

# Name Normalization with Multiple Aliases Handling
def normalize_name(name):
    if not isinstance(name, str):
        return ['']
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('utf-8')
    aliases = re.split(r'\s*[@|/|\|]\s*', name)
    return [re.sub(r'\b(?:Mr|Mrs|Ms|Dr|Prof)\.\s', '', alias).strip().lower() for alias in aliases]

# Fetch Names from Website
def fetch_names_from_website(url):
    response = requests.get(url, verify=False)
    if 'xml' in response.headers.get('Content-Type', ''):
        tree = ET.fromstring(response.content)
        return pd.Series([elem.text for elem in tree.iter() if elem.text]).dropna()
    else:
        soup = BeautifulSoup(response.text, 'html.parser')
        return pd.Series([tag.get_text(strip=True) for tag in soup.find_all('p')]).dropna()

# Hybrid Matching
def hybrid_match(name1_list, name2_list):
    return max(
        (fuzz.ratio(n1, n2) * 0.4 + jellyfish.jaro_winkler_similarity(n1, n2) * 100 * 0.5 + (
            10 if jellyfish.soundex(n1) == jellyfish.soundex(n2) else 0))
        for n1 in name1_list for n2 in name2_list
    )

# Perform Screening
def perform_screening(names_list, customers, threshold=55):
    results = [
        {'Customer': c, 'Matched Name': n, 'Score': hybrid_match(normalize_name(c), normalize_name(n))}
        for c in customers.dropna()
        for n in names_list.dropna()
        if hybrid_match(normalize_name(c), normalize_name(n)) >= threshold
    ]
    return pd.DataFrame(results).sort_values(by='Score', ascending=False) if results else pd.DataFrame()

# Streamlit Web App
st.title('Sanctions Name Screening System')
source_option = st.radio("Choose Screening Type:", ('From Another Workbook', 'From XML or HTML Website'))
file = st.file_uploader("Upload Customer Workbook (Excel or CSV)", type=["xlsx", "csv"])

if source_option == 'From Another Workbook':
    compare_file = st.file_uploader("Upload Comparison Workbook (Excel or CSV)", type=["xlsx", "csv"])
elif source_option == 'From XML or HTML Website':
    website_url = st.text_input("Enter Website URL for Screening")

output_format = st.radio("Choose Output Format:", ('xlsx', 'csv'))

if st.button('Run Screening') and file:
    if file.name.endswith('.xlsx'):
        customers = pd.concat(pd.read_excel(file, sheet_name=None, engine='openpyxl').values()).stack().astype(str).dropna()
    else:
        customers = pd.read_csv(file).stack().astype(str).dropna()

    if source_option == 'From Another Workbook' and compare_file:
        if compare_file.name.endswith('.xlsx'):
            comparison_names = pd.concat(
                pd.read_excel(compare_file, sheet_name=None, engine='openpyxl').values()).stack().astype(str).dropna()
        else:
            comparison_names = pd.read_csv(compare_file).stack().astype(str).dropna()
    elif source_option == 'From XML or HTML Website' and website_url:
        comparison_names = fetch_names_from_website(website_url)
    else:
        st.warning('No source selected or invalid input.')
        comparison_names = pd.Series([])

    results = perform_screening(comparison_names, customers)
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

