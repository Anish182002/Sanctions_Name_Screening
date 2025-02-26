import os
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
import fitz  # PyMuPDF for PDF processing

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Name Normalization with Multiple Aliases Handling
def normalize_name(name):
    if not isinstance(name, str):
        return ['']
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode('utf-8')
    aliases = re.split(r'\s*[@|/|\|]\s*', name)
    return [re.sub(r'\b(?:Mr|Mrs|Ms|Dr|Prof)\.\s', '', alias).strip().lower() for alias in aliases]

# Fetch Names from a Website
def fetch_names_from_website(url):
    try:
        response = requests.get(url, verify=False, timeout=10)
        if 'xml' in response.headers.get('Content-Type', ''):
            tree = ET.fromstring(response.content)
            return pd.Series([elem.text for elem in tree.iter() if elem.text]).dropna()
        else:
            soup = BeautifulSoup(response.text, 'html.parser')
            return pd.Series([tag.get_text(strip=True) for tag in soup.find_all('p')]).dropna()
    except Exception as e:
        st.warning(f"Error fetching data from {url}: {str(e)}")
        return pd.Series([])

# Hybrid Matching Algorithm
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

# Extract Names from PDF (Instead of Full Text)
def extract_names_from_pdf(pdf_file):
    text = ""
    with fitz.open(pdf_file) as doc:
        for page in doc:
            text += page.get_text("text") + "\n"  # Extract text from each page

    # Regex to match names (Assuming "Firstname Lastname" format)
    potential_names = re.findall(r'\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)+\b', text)

    # Convert list to Pandas Series and remove duplicates
    return pd.Series(list(set(potential_names))).dropna()

# Streamlit Web App
st.title('Sanctions Name Screening System')

source_option = st.radio("Choose Screening Type:", ('From Another Workbook', 'From XML or HTML Website'))
file = st.file_uploader("Upload Customer Workbook (Excel, CSV, or PDF)", type=["xlsx", "csv", "pdf"])

# Predefined Websites for Screening
default_websites = [
    "https://scsanctions.un.org/resources/xml/en/consolidated.xml",
    "https://www.mha.gov.in/en/banned-organisations",
    "https://www.mha.gov.in/en/page/individual-terrorists-under-uapa",
    "https://www.mha.gov.in/en/commoncontent/unlawful-associations-under-section-3-of-unlawful-activities-prevention-act-1967"
]

if source_option == 'From XML or HTML Website':
    website_choice = st.radio("Choose Website Source:", ("Default List (All Websites)", "Custom URL"))

    if website_choice == "Custom URL":
        selected_url = st.text_input("Enter a Custom Website URL for Screening")

output_format = st.radio("Choose Output Format:", ('xlsx', 'csv'))

# Run Screening
if st.button('Run Screening') and file:
    if file.name.endswith('.xlsx'):
        customers = pd.concat(pd.read_excel(file, sheet_name=None, engine='openpyxl').values()).stack().astype(str).dropna()
    elif file.name.endswith('.csv'):
        customers = pd.read_csv(file).stack().astype(str).dropna()
    elif file.name.endswith('.pdf'):
        customers = extract_names_from_pdf(file)  # Extract only names from PDF
    else:
        st.warning("Unsupported file format.")
        customers = pd.Series([])

    if source_option == 'From Another Workbook':
        compare_file = st.file_uploader("Upload Comparison File (Excel, CSV, or PDF)", type=["xlsx", "csv", "pdf"])
        
        if compare_file:
            if compare_file.name.endswith('.xlsx'):
                comparison_names = pd.concat(pd.read_excel(compare_file, sheet_name=None, engine='openpyxl').values()).stack().astype(str).dropna()
            elif compare_file.name.endswith('.csv'):
                comparison_names = pd.read_csv(compare_file).stack().astype(str).dropna()
            elif compare_file.name.endswith('.pdf'):
                comparison_names = extract_names_from_pdf(compare_file)
            else:
                st.warning("Unsupported file format.")
                comparison_names = pd.Series([])
        else:
            st.warning('No comparison file uploaded.')
            comparison_names = pd.Series([])
    
    elif source_option == 'From XML or HTML Website':
        comparison_names = pd.Series([])
        if website_choice == "Default List (All Websites)":
            for url in default_websites:
                names = fetch_names_from_website(url)
                comparison_names = pd.concat([comparison_names, names]).dropna()
        elif website_choice == "Custom URL" and selected_url:
            comparison_names = fetch_names_from_website(selected_url)
        else:
            st.warning('No valid source selected.')
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

