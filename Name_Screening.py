import pandas as pd
import requests
import xml.etree.ElementTree as ET
import re
import unicodedata
from rapidfuzz import fuzz
import jellyfish

# ----------------------------
# Step 1: Preprocessing Function
# ----------------------------
def preprocess_name(name):
    name = unicodedata.normalize('NFKD', name)
    name = re.sub(r'[^a-zA-Z\s]', '', name)
    name = re.sub(r'\s+', ' ', name).strip().lower()
    return name

# ----------------------------
# Step 2: Download Sanctions List from UN XML
# ----------------------------
def get_sanctioned_names():
    url = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"
    response = requests.get(url)
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
    return names

# ----------------------------
# Step 3: Load Customer Data from Excel
# ----------------------------
def load_customer_data(path):
    df = pd.read_excel(path)
    df['Customer'] = df['Customer'].astype(str).apply(preprocess_name)
    return df

# ----------------------------
# Step 4: Scoring Function (Weighted Hybrid)
# ----------------------------
def calculate_score(customer_name, sanctioned_name):
    tsr = fuzz.token_sort_ratio(customer_name, sanctioned_name)
    pr = fuzz.partial_ratio(customer_name, sanctioned_name)
    jw = jellyfish.jaro_winkler_similarity(customer_name, sanctioned_name) * 100

    final_score = 0.4 * tsr + 0.3 * pr + 0.3 * jw
    return round(final_score, 2)

# ----------------------------
# Step 5: Match Customers with Sanctioned List
# ----------------------------
def match_customers(customers_df, sanctioned_names, threshold=85):
    results = []

    for idx, customer in enumerate(customers_df['Customer']):
        best_match = None
        best_score = 0

        for sanctioned in sanctioned_names:
            score = calculate_score(customer, sanctioned)
            if score > best_score:
                best_score = score
                best_match = sanctioned

        if best_score >= threshold:
            results.append({
                'Customer': customer,
                'Matched Name': best_match,
                'Score': best_score,
                'Flagged': 1
            })
        else:
            results.append({
                'Customer': customer,
                'Matched Name': best_match,
                'Score': best_score,
                'Flagged': 0
            })

    return pd.DataFrame(results)

# ----------------------------
# Step 6: Run
# ----------------------------
if __name__ == '__main__':
    sanctioned_names = get_sanctioned_names()
    customers_df = load_customer_data('customers.xlsx')
    result_df = match_customers(customers_df, sanctioned_names, threshold=85)
    result_df.to_excel('name_screening_result.xlsx', index=False)
    print(result_df)
