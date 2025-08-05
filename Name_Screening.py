import pandas as pd
import requests
import xml.etree.ElementTree as ET
import re
import unicodedata
from rapidfuzz import fuzz
import jellyfish
import streamlit as st

# ----------------------------
# Preprocessing Function
# ----------------------------
def preprocess_name(name):
    name = unicodedata.normalize('NFKD', name)
    name = re.sub(r'[^a-zA-Z\s]', '', name)
    name = re.sub(r'\s+', ' ', name).strip().lower()
    return name

# ----------------------------
# Download Sanctions List from UN XML
# ----------------------------
@st.cache_data
def get_sanctioned_names():
    url = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        namespaces = {'ns': 'urn:un:sc:consolidated:v1'}

        names = []
        for individual in root.findall(".//ns:INDIVIDUAL", namespaces):
            full_name = ""
            for name_part in individual.findall(".//ns:INDIVIDUAL_NAME", namespaces):
                whole_name = name_part.findtext("ns:NAME", default="", namespaces=namespaces)
                if whole_name:
                    full_name = whole_name.strip()
                    break
            if full_name:
                names.append(preprocess_name(full_name))
        return list(set(names))
    except Exception as e:
        st.error(f"Failed to fetch sanctions list: {e}")
        return []

# ----------------------------
# Scoring Function (Weighted Hybrid)
# ----------------------------
def calculate_score(customer_name, sanctioned_name):
    tsr = fuzz.token_sort_ratio(customer_name, sanctioned_name)
    pr = fuzz.partial_ratio(customer_name, sanctioned_name)
    jw = jellyfish.jaro_winkler_similarity(customer_name, sanctioned_name) * 100
    final_score = 0.4 * tsr + 0.3 * pr + 0.3 * jw
    return round(final_score, 2)

# ----------------------------
# Matching Function
# ----------------------------
def match_customers(customers_df, sanctioned_names, threshold=85):
    results = []

    for _, row in customers_df.iterrows():
        original = row['Customer']
        customer = preprocess_name(original)

        best_match = None
        best_score = 0

        for sanctioned in sanctioned_names:
            score = calculate_score(customer, sanctioned)
            if score > best_score:
                best_score = score
                best_match = sanctioned

        if best_score >= threshold:
            results.append({
                'Original Name': original,
                'Matched Name': best_match,
                'Score': best_score,
                'Flagged': 1
            })

    return pd.DataFrame(results)

# ----------------------------
# Streamlit UI
# ----------------------------
def main():
    st.title("🔍 UN Sanctions Name Screening Tool")
    st.write("Upload your customer Excel file and set the similarity threshold.")

    # Threshold slider
    threshold = st.slider("Select Match Threshold (%)", min_value=50, max_value=100, value=85, step=1)

    # File uploader
    uploaded_file = st.file_uploader("Upload Customer Excel File", type=["xlsx"])

    if uploaded_file:
        try:
            customers_df = pd.read_excel(uploaded_file)
            if 'Customer' not in customers_df.columns:
                st.error("Excel must have a column named 'Customer'.")
                return

            st.success("File uploaded successfully.")
            with st.spinner("Fetching UN sanctions list..."):
                sanctioned_names = get_sanctioned_names()

            if not sanctioned_names:
                st.error("Could not retrieve sanctioned names.")
                return

            with st.spinner("Matching names..."):
                results_df = match_customers(customers_df, sanctioned_names, threshold)

            st.success(f"Matching complete. {len(results_df)} matches found.")
            st.dataframe(results_df)

            # Download link
            st.download_button("📥 Download Results", data=results_df.to_excel(index=False), file_name="sanctioned_matches.xlsx")

        except Exception as e:
            st.error(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
