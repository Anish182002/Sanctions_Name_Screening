import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
from rapidfuzz import fuzz
import re
import unicodedata

# --------- Functions ---------

@st.cache_data
def fetch_un_sanctions_names():
    url = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"
    response = requests.get(url)
    root = ET.fromstring(response.content)
    names = []
    for individual in root.findall(".//INDIVIDUAL"):
        for name in individual.findall("INDIVIDUAL_ALIAS"):
            alias_name = name.findtext("ALIAS_NAME")
            if alias_name:
                names.append(alias_name.strip())
        name = individual.findtext("INDIVIDUAL_NAME")
        if name:
            names.append(name.strip())
    return list(set(names))  # remove duplicates

def normalize_name(name):
    name = name.lower()
    name = unicodedata.normalize("NFKD", name)
    name = re.sub(r"[^a-z\s]", "", name)
    return name.strip()

def match_names(customer_names, sanctions_names, threshold=85):
    matches = []
    for customer in customer_names:
        customer_clean = normalize_name(customer)
        for sanction in sanctions_names:
            sanction_clean = normalize_name(sanction)
            score = fuzz.token_sort_ratio(customer_clean, sanction_clean)
            if score >= threshold:
                matches.append({
                    "Customer Name": customer,
                    "Sanctioned Name": sanction,
                    "Score": score
                })
    return pd.DataFrame(matches)

def extract_customer_names(uploaded_file):
    df = pd.read_excel(uploaded_file, engine='openpyxl')
    name_columns = [col for col in df.columns if "name" in col.lower()]
    all_names = []
    for col in name_columns:
        all_names.extend(df[col].dropna().astype(str).tolist())
    return all_names

# --------- Streamlit UI ---------

st.title("🚨 UN Sanctions Name Screening")

uploaded_file = st.file_uploader("Upload Excel file with customer names", type=["xlsx"])

if uploaded_file:
    with st.spinner("Loading UN Sanctions list..."):
        sanctions_names = fetch_un_sanctions_names()
    with st.spinner("Reading customer names..."):
        customer_names = extract_customer_names(uploaded_file)
    st.success(f"Found {len(customer_names)} customer names.")

    if st.button("Run Name Screening"):
        with st.spinner("Running fuzzy matching..."):
            results_df = match_names(customer_names, sanctions_names)
        if not results_df.empty:
            st.warning("⚠️ Potential Matches Found!")
            st.dataframe(results_df)
            csv = results_df.to_csv(index=False).encode('utf-8')
            st.download_button("Download Matches as CSV", csv, "matches.csv", "text/csv")
        else:
            st.success("✅ No matches found.")

else:
    st.info("Please upload an Excel file containing customer names.")
