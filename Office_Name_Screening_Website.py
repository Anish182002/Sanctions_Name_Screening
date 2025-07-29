import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
import unicodedata
import re
from rapidfuzz import fuzz

# Extract names from UN consolidated sanctions list XML
@st.cache_data
def get_sanctioned_names():
    url = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"
    response = requests.get(url)
    root = ET.fromstring(response.content)

    namespaces = {'ns': 'http://www.un.org/sanctions/1.0'}
    names = set()

    for individual in root.findall(".//INDIVIDUAL"):
        first_name = individual.findtext("FIRST_NAME")
        second_name = individual.findtext("SECOND_NAME")
        third_name = individual.findtext("THIRD_NAME")
        fourth_name = individual.findtext("FOURTH_NAME")

        full_name = " ".join(filter(None, [first_name, second_name, third_name, fourth_name]))
        if full_name:
            names.add(normalize_name(full_name))

    for entity in root.findall(".//ENTITY"):
        entity_name = entity.findtext("NAME")
        if entity_name:
            names.add(normalize_name(entity_name))

    return list(names)

# Normalize names: remove accents, special chars, lowercase
def normalize_name(name):
    name = unicodedata.normalize('NFKD', name)
    name = name.encode('ascii', 'ignore').decode('utf-8')
    name = re.sub(r'[^a-zA-Z0-9\s]', '', name)
    return name.lower().strip()

# Perform fuzzy matching
def match_names(customers, sanctions, threshold=85):
    matches = []

    for customer in customers:
        customer_norm = normalize_name(customer)
        for sanction in sanctions:
            score = fuzz.token_set_ratio(customer_norm, sanction)
            if score >= threshold:
                matches.append({
                    'Customer Name': customer,
                    'Sanctioned Name': sanction,
                    'Similarity Score': score
                })

    return pd.DataFrame(matches)

# Main Streamlit UI
def main():
    st.title("UN Sanctions Name Screening")

    st.markdown("Upload an Excel file (`.xlsx`) containing customer names in a column named **`Name`**.")

    uploaded_file = st.file_uploader("Upload customer Excel file", type=['xlsx'])

    if uploaded_file:
        try:
            df = pd.read_excel(uploaded_file, engine='openpyxl')

            if 'Name' not in df.columns:
                st.error("Excel file must contain a column named 'Name'")
                return

            customer_names = df['Name'].dropna().tolist()
            sanctioned_names = get_sanctioned_names()

            st.info("Performing name screening... Please wait.")
            result_df = match_names(customer_names, sanctioned_names)

            if not result_df.empty:
                st.success(f"Found {len(result_df)} potential match(es).")
                st.dataframe(result_df.sort_values(by="Similarity Score", ascending=False))
                csv = result_df.to_csv(index=False).encode('utf-8')
                st.download_button("Download results as CSV", csv, "matches.csv", "text/csv")
            else:
                st.success("No matches found.")

        except Exception as e:
            st.error(f"Failed to read file: {e}")
    else:
        st.warning("Please upload a customer Excel file to proceed.")

if __name__ == "__main__":
    main()
