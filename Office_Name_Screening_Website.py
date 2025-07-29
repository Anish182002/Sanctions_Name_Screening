import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
from rapidfuzz import fuzz
import unicodedata
import re

# ------------------------- Utility Functions -------------------------

def normalize_name(name):
    name = unicodedata.normalize("NFKD", name)
    name = re.sub(r'[^\w\s]', '', name)
    name = name.lower().strip()
    return name

def fetch_sanctioned_names():
    url = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"
    response = requests.get(url)
    response.raise_for_status()
    root = ET.fromstring(response.content)

    names = []
    for individual in root.findall(".//INDIVIDUAL"):
        full_name = individual.findtext("INDIVIDUAL_NAME")
        if full_name:
            names.append(normalize_name(full_name))

    for entity in root.findall(".//ENTITY"):
        entity_name = entity.findtext("ENTITY_NAME")
        if entity_name:
            names.append(normalize_name(entity_name))

    return names

def match_names(customer_names, sanctioned_names, threshold=85):
    matches = []
    for cust in customer_names:
        cust_norm = normalize_name(cust)
        for sanc in sanctioned_names:
            score = fuzz.token_sort_ratio(cust_norm, sanc)
            if score >= threshold:
                matches.append((cust, sanc, score))
    return matches

def load_customer_names(uploaded_file):
    try:
        df = pd.read_excel(uploaded_file, engine='openpyxl')
        name_columns = [col for col in df.columns if 'name' in col.lower()]
        if not name_columns:
            st.warning("No column with 'name' found in the uploaded Excel file.")
            return []
        return df[name_columns[0]].dropna().astype(str).tolist()
    except Exception as e:
        st.error(f"Failed to read uploaded Excel file: {e}")
        return []

# ------------------------- Streamlit UI -------------------------

def main():
    st.set_page_config(page_title="UN Sanctions Name Screening", layout="centered")
    st.title("🔍 UN Sanctions Name Screening App")

    st.markdown("Upload an Excel file (`.xlsx`) with customer names to check against the UN consolidated sanctions list.")

    uploaded_file = st.file_uploader("Upload your customer Excel file", type=["xlsx"])

    if uploaded_file:
        with st.spinner("Loading sanctioned names from UN list..."):
            sanctioned_names = fetch_sanctioned_names()

        with st.spinner("Reading customer names..."):
            customer_names = load_customer_names(uploaded_file)

        if customer_names:
            st.success(f"✅ Found {len(customer_names)} customer names in uploaded file.")
            with st.spinner("Performing name screening..."):
                matches = match_names(customer_names, sanctioned_names, threshold=85)

            if matches:
                st.error(f"⚠️ {len(matches)} potential match(es) found!")
                result_df = pd.DataFrame(matches, columns=["Customer Name", "Matched Sanction Name", "Match Score"])
                st.dataframe(result_df)

                csv = result_df.to_csv(index=False).encode("utf-8")
                st.download_button("⬇ Download Matches as CSV", csv, "sanctions_matches.csv", "text/csv")
            else:
                st.success("🎉 No matches found. All customers cleared.")
        else:
            st.warning("⚠️ No valid customer names found in the uploaded file.")

if __name__ == "__main__":
    main()
