import requests
import xml.etree.ElementTree as ET
import pandas as pd
import unicodedata
import re
from rapidfuzz import fuzz
import jellyfish

# ----------- SETTINGS -----------
UN_XML_URL = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"
CUSTOMER_FILE = "customers.xlsx"  # Your Excel input file

FUZZY_THRESHOLD = 85  # Adjust this for fuzzy score sensitivity
# --------------------------------

def normalize_name(name):
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("utf-8")
    name = name.lower()
    name = re.sub(r'[^\w\s]', '', name)
    return name.strip()

def fetch_sanctioned_names_from_un():
    response = requests.get(UN_XML_URL)
    root = ET.fromstring(response.content)

    namespaces = {'': 'http://www.un.org/sanctions/1.0'}
    sanctioned_names = []

    for individual in root.findall('.//INDIVIDUAL'):
        names = []
        for name_elem in individual.findall('INDIVIDUAL_ALIAS'):
            alias = name_elem.find('ALIAS_NAME')
            if alias is not None and alias.text:
                names.append(alias.text.strip())
        for name_elem in individual.findall('INDIVIDUAL_NAME'):
            if name_elem.text:
                names.append(name_elem.text.strip())
        sanctioned_names.extend(names)

    return list(set(sanctioned_names))

def load_customer_names(excel_file):
    df = pd.read_excel(excel_file, engine='openpyxl')
    customer_names = df.iloc[:, 0].dropna().tolist()
    return customer_names

def get_soundex(name):
    return jellyfish.soundex(name)

def match_names(customer_names, sanctioned_names):
    matches = []

    for customer in customer_names:
        normalized_customer = normalize_name(customer)
        soundex_customer = get_soundex(normalized_customer)

        for sanctioned in sanctioned_names:
            normalized_sanctioned = normalize_name(sanctioned)
            fuzzy_score = fuzz.token_set_ratio(normalized_customer, normalized_sanctioned)

            soundex_sanctioned = get_soundex(normalized_sanctioned)
            is_soundex_match = soundex_customer == soundex_sanctioned

            if fuzzy_score >= FUZZY_THRESHOLD or is_soundex_match:
                matches.append({
                    "Customer Name": customer,
                    "Sanctioned Name": sanctioned,
                    "Fuzzy Score": fuzzy_score,
                    "Soundex Match": is_soundex_match,
                    "Match Method": "Soundex" if is_soundex_match else "Fuzzy"
                })

    return matches

def main():
    print("Fetching UN sanctioned names...")
    sanctioned_names = fetch_sanctioned_names_from_un()

    print("Reading customer data from Excel...")
    customer_names = load_customer_names(CUSTOMER_FILE)

    print("Performing name screening...")
    results = match_names(customer_names, sanctioned_names)

    if results:
        result_df = pd.DataFrame(results)
        print("\nMatches found:\n")
        print(result_df.to_string(index=False))
        result_df.to_excel("screening_results.xlsx", index=False)
        print("\nResults saved to 'screening_results.xlsx'")
    else:
        print("No matches found.")

if __name__ == "__main__":
    main()
