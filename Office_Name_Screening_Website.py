import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from rapidfuzz import fuzz
import jellyfish
import re
import unicodedata

# --- UN Sanctions Scraper ---
@st.cache_data
def fetch_un_sanctioned_names():
    url = "https://scsanctions.un.org/kho39en-all.html"
    response = requests.get(url)
    soup = BeautifulSoup(response.content, "lxml")

    paragraphs = soup.find_all("p")
    names = []

    for para in paragraphs:
        text = para.get_text(strip=True)
        matches = re.findall(r'^([A-Z][A-Z\s\-\,\.\(\)]+)', text)
        for match in matches:
            clean_name = normalize_text(match)
            names.append(clean_name)

    return list(set(names))  # Unique names only

# --- Normalize Text ---
def normalize_text(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8")
    return re.sub(r'\s+', ' ', text).strip().lower()

# --- Get Soundex Code ---
def soundex(name):
    return jellyfish.soundex(name)

# --- Matching Logic ---
def is_match(customer_name, sanctioned_name):
    norm_cust = normalize_text(customer_name)
    norm_san = normalize_text(sanctioned_name)

    # Soundex match
    if soundex(norm_cust) == soundex(norm_san):
        return True

    # Fuzzy match
    score = fuzz.ratio(norm_cust, norm_san)
    if score >= 85:
        return True

    return False

# --- Main App ---
def main():
    st.title("🔍 UN Sanctions Name Screening")

    # Load sanctioned names
    with st.spinner("Fetching UN Sanctions List..."):
        sanctioned_names = fetch_un_sanctioned_names()

    # Upload Excel file
    uploaded_file = st.file_uploader("Upload Customer Excel File", type=["xlsx"])
    if uploaded_file:
        df = pd.read_excel(uploaded_file, engine="openpyxl")
        st.success("File uploaded successfully!")

        # Show preview
        st.subheader("Customer Data Preview")
        st.dataframe(df.head())

        # Detect name column
        name_column = st.selectbox("Select the customer name column", df.columns)

        results = []
        for name in df[name_column].dropna():
            for sanctioned in sanctioned_names:
                if is_match(name, sanctioned):
                    results.append({
                        "Customer Name": name,
                        "Sanctioned Name": sanctioned
                    })
                    break  # Stop after first match

        if results:
            st.subheader("🚨 Matches Found")
            result_df = pd.DataFrame(results)
            st.dataframe(result_df)
        else:
            st.success("✅ No matches found!")

if __name__ == "__main__":
    main()
