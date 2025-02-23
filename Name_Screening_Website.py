import os

# Ensure all dependencies are installed in Streamlit Cloud
os.system("pip install -r Requirements.txt")

import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from rapidfuzz import fuzz
import unicodedata
import jellyfish

# Streamlit UI
st.title("Sanctions Name Screening System")

# Function to fetch & parse UN sanctions list (XML)
@st.cache_data
def fetch_un_sanctions():
    url = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"
    response = requests.get(url)
    if response.status_code == 200:
        root = ET.fromstring(response.content)
        names = [entity.find("firstName").text + " " + entity.find("secondName").text
                 for entity in root.findall(".//individual") if entity.find("firstName") is not None]
        return names
    else:
        return []

# Function to fetch Indian MHA sanctions lists
@st.cache_data
def fetch_mha_sanctions():
    urls = [
        "https://www.mha.gov.in/en/banned-organisations",
        "https://www.mha.gov.in/en/page/individual-terrorists-under-uapa",
        "https://www.mha.gov.in/en/commoncontent/unlawful-associations-under-section-3-of-unlawful-activities-prevention-act-1967"
    ]
    sanctioned_names = []
    for url in urls:
        response = requests.get(url)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "lxml")
            sanctioned_names.extend([item.text.strip() for item in soup.find_all("li")])
    return sanctioned_names

# Function for fuzzy name matching
def match_names(customer_name, sanctioned_names):
    matches = []
    for sanctioned_name in sanctioned_names:
        score = fuzz.ratio(customer_name.lower(), sanctioned_name.lower())
        if score > 80:  # Threshold for a strong match
            matches.append((sanctioned_name, score))
    return sorted(matches, key=lambda x: x[1], reverse=True)

# Load customer data
uploaded_file = st.file_uploader("Upload Customer Excel File", type=["xlsx"])
if uploaded_file:
    df = pd.read_excel(uploaded_file, engine="openpyxl")
    sanctioned_list = fetch_un_sanctions() + fetch_mha_sanctions()

    if "Name" in df.columns:
        df["Matches"] = df["Name"].apply(lambda x: match_names(str(x), sanctioned_list))
        st.write("Screening Results:")
        st.dataframe(df)
    else:
        st.error("Column 'Name' not found in uploaded file.")
