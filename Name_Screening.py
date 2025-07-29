import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
from rapidfuzz import fuzz
import unicodedata
import re

# Variant mapping
VARIANT_MAP = {
    "daud": "dawood",
    "mohammed": "muhammad",
    "yusuf": "yousuf",
    "mohamad": "muhammad",
    "sayed": "syed",
    "mohamad": "muhammad",
    "mohd": "muhammad",
    "moh": "muhammad",
    "ali": "alee",
    "husain": "hussain",
    "abdul": "abdool"
}

def normalize_name(name):
    # Lowercase, remove accents, non-alphanumeric, extra spaces
    name = name.lower()
    name = unicodedata.normalize('NFKD', name).encode('ASCII', 'ignore').decode()
    name = re.sub(r'[^a-zA-Z\s]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    # Apply variant mapping
    words = name.split()
    words = [VARIANT_MAP.get(word, word) for word in words]
    return ' '.join(words)

def fetch_un_sanctioned_names():
    url = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"
    response = requests.get(url)
    root = ET.fromstring(response.content)
    names = []
    for individual in root.findall(".//INDIVIDUAL"):
        full_name = ""
        for name_part in individual.findall("INDIVIDUAL_ALIAS/ALIAS_NAME"):
            full_name = name_part.text
            if full_name:
                names.append(normalize_name(full_name))
    return list(set(names))

def match_name(input_name, sanctioned_names, threshold):
    input_normalized = normalize_name(input_name)
    matches = []
    for sanctioned_name in sanctioned_names:
        score = fuzz.token_sort_ratio(input_normalized, sanctioned_name)
        if score >= threshold:
            matches.append((sanctioned_name, score))
    matches.sort(key=lambda x: x[1], reverse=True)
    return matches

# Streamlit UI
st.set_page_config(page_title="Sanctions Name Screening", layout="wide")
st.title("🕵️‍♂️ Sanctions Name Screening App")

uploaded_file = st.file_uploader("Upload Excel File (with a 'Name' column)", type=["xlsx"])
threshold = st.slider("Set Matching Threshold", min_value=50, max_value=100, value=85, step=1)

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    if "Name" not in df.columns:
        st.error("Excel file must contain a 'Name' column.")
    else:
        st.info("Fetching UN sanctioned names...")
        sanctioned_names = fetch_un_sanctioned_names()

        results = []
        for name in df["Name"]:
            matches = match_name(name, sanctioned_names, threshold)
            if matches:
                top_match = matches[0]
                results.append({
                    "Input Name": name,
                    "Matched Sanctioned Name": top_match[0],
                    "Match Score": top_match[1]
                })
            else:
                results.append({
                    "Input Name": name,
                    "Matched Sanctioned Name": "No match",
                    "Match Score": 0
                })

        result_df = pd.DataFrame(results)
        st.success("Matching complete.")
        st.dataframe(result_df)

        csv = result_df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download Results as CSV", data=csv, file_name="name_screening_results.csv", mime="text/csv")
