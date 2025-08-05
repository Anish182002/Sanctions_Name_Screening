import pandas as pd
import requests
import xml.etree.ElementTree as ET
import re
import unicodedata
from rapidfuzz import fuzz
import jellyfish
import streamlit as st
from bs4 import BeautifulSoup

# ----------------------------
# Name Preprocessing
# ----------------------------
def preprocess_name(name):
    name = unicodedata.normalize('NFKD', name)
    name = re.sub(r'[^a-zA-Z\s]', '', name)
    name = re.sub(r'\s+', ' ', name).strip().lower()
    return name

# ----------------------------
# Fetch UN Sanctions Names
# ----------------------------
@st.cache_data
def get_un_sanctions():
    url = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        namespaces = {'ns': 'urn:un:sc:consolidated:v1'}
        names = []
        for individual in root.findall(".//ns:INDIVIDUAL", namespaces):
            for name_part in individual.findall(".//ns:INDIVIDUAL_NAME", namespaces):
                full_name = name_part.findtext("ns:NAME", default="", namespaces=namespaces)
                if full_name:
                    names.append(preprocess_name(full_name))
                    break
        return list(set(names))
    except Exception as e:
        st.warning(f"UN sanctions list could not be loaded: {e}")
        return []

# ----------------------------
# Fetch MHA Banned Organisations
# ----------------------------
@st.cache_data
def get_mha_banned_organisations():
    url = "https://www.mha.gov.in/en/banned-organisations"
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.content, 'lxml')
        banned_names = []
        table = soup.find('table')
        if table:
            rows = table.find_all('tr')[1:]  # Skip header
            for row in rows:
                cols = row.find_all('td')
                if cols:
                    name = cols[0].text.strip()
                    banned_names.append(preprocess_name(name))
        return list(set(banned_names))
    except Exception as e:
        st.warning(f"Banned organisations list could not be loaded: {e}")
        return []

# ----------------------------
# Fetch MHA Individual Terrorists
# ----------------------------
@st.cache_data
def get_mha_individual_terrorists():
    url = "https://www.mha.gov.in/en/page/individual-terrorists-under-uapa"
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.content, 'lxml')
        terrorists = []
        table = soup.find('table')
        if table:
            rows = table.find_all('tr')[1:]
            for row in rows:
                cols = row.find_all('td')
                if cols:
                    name = cols[0].text.strip()
                    terrorists.append(preprocess_name(name))
        return list(set(terrorists))
    except Exception as e:
        st.warning(f"Individual terrorists list could not be loaded: {e}")
        return []

# ----------------------------
# Fetch MHA Unlawful Associations
# ----------------------------
@st.cache_data
def get_mha_unlawful_associations():
    url = "https://www.mha.gov.in/en/commoncontent/unlawful-associations-under-section-3-of-unlawful-activities-prevention-act-1967"
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.content, 'lxml')
        associations = []
        table = soup.find('table')
        if table:
            rows = table.find_all('tr')[1:]
            for row in rows:
                cols = row.find_all('td')
                if cols:
                    name = cols[0].text.strip()
                    associations.append(preprocess_name(name))
        return list(set(associations))
    except Exception as e:
        st.warning(f"Unlawful associations list could not be loaded: {e}")
        return []

# ----------------------------
# Match Scoring
# ----------------------------
def calculate_score(customer_name, sanctioned_name):
    tsr = fuzz.token_sort_ratio(customer_name, sanctioned_name)
    pr = fuzz.partial_ratio(customer_name, sanctioned_name)
    jw = jellyfish.jaro_winkler_similarity(customer_name, sanctioned_name) * 100
    final_score = 0.4 * tsr + 0.3 * pr + 0.3 * jw
    return round(final_score, 2)

# ----------------------------
# Perform Matching
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
# Streamlit App
# ----------------------------
def main():
    st.title("🚨 Name Screening Tool - UN & MHA Sanctions")
    threshold = st.slider("Set Match Threshold (%)", 50, 100, 85, step=1)
    uploaded_file = st.file_uploader("Upload Customer Excel File", type=["xlsx"])

    if uploaded_file:
        try:
            customers_df = pd.read_excel(uploaded_file)
            if 'Customer' not in customers_df.columns:
                st.error("The Excel file must contain a 'Customer' column.")
                return

            with st.spinner("Fetching all sanctions data..."):
                un_names = get_un_sanctions()
                org_names = get_mha_banned_organisations()
                ind_names = get_mha_individual_terrorists()
                assoc_names = get_mha_unlawful_associations()

                all_sanctioned = list(set(un_names + org_names + ind_names + assoc_names))

            with st.spinner("Matching customers..."):
                result_df = match_customers(customers_df, all_sanctioned, threshold)

            st.success(f"Found {len(result_df)} matches above threshold.")
            st.dataframe(result_df)

            st.download_button("📥 Download Results", data=result_df.to_excel(index=False), file_name="matches.xlsx")

        except Exception as e:
            st.error(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
