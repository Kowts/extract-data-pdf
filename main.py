import pandas as pd
from PyPDF2 import PdfReader
import re

# Function to extract data from PDF
def extract_data_from_pdf(pdf_path):
    data = []
    reader = PdfReader(pdf_path)
    num_pages = len(reader.pages)

    for page in range(num_pages):
        print(f'Extracting data from page {page + 1}/{num_pages} of {pdf_path}')
        page_obj = reader.pages[page]
        text = page_obj.extract_text()

        # Extract the relevant lines containing names and dates
        matches = re.findall(r'([\w\s]+)\n([\w\s]+)\n([\w\s]+)\n([\d-]{10})', text)
        for match in matches:
            name = match[0].strip()
            date_of_birth = match[3].strip()
            data.append([name, date_of_birth])

    return data

# Extract data from both PDFs
data_estrangeiros = extract_data_from_pdf('SC_A_ESTRANGEIRO_2024.pdf')
print(data_estrangeiros)
print('---------------------------------------------------')
data_nacionais = extract_data_from_pdf('SC_A_NACIONAIS_2024.pdf')
print(data_nacionais)

# Combine data
combined_data = data_estrangeiros + data_nacionais

# Create a DataFrame
df = pd.DataFrame(combined_data, columns=['Nome', 'Data de Nascimento'])

# Save to Excel file
output_file_path = 'SC_A_ESTRANGEIRO_NACIONAIS_2024.xlsx'
df.to_excel(output_file_path, index=False)

print(f'Data extracted and saved to {output_file_path}')
