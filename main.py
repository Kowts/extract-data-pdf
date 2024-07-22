import os
import pdfplumber
import pandas as pd
import re
import mysql.connector
from pprint import pprint
from dotenv import load_dotenv

load_dotenv()

def extract_name_and_date(text):
    """
    Extract the name and date from a given text using regular expression.

    Args:
    text (str): The input text containing the name and date.

    Returns:
    tuple: A tuple containing the name and the extracted date in the format DD-MM-YYYY if found, otherwise (text, None).
    """
    date_pattern = r'\d{2}-\d{2}-\d{4}'
    match = re.search(date_pattern, text)
    if match:
        date = match.group()
        name = text.replace(date, '').strip()
        return name, date
    return text, None

def extract_concelho_and_posto(page_text):
    """
    Extract 'Concelho' and 'Posto' values from the page text.

    Args:
    page_text (str): The text from which to extract the values.

    Returns:
    tuple: A tuple containing the extracted 'Concelho' and 'Posto' values.
    """
    concelho_pattern = r'Concelho\s*:\s*([\w\sçÇáéíóúàèìòùãõâêîôûäëïöüÄËÏÖÜñÑ]+)\s*Posto\s*:\s*([\w\sçÇáéíóúàèìòùãõâêîôûäëïöüÄËÏÖÜñÑ-]+)'
    match = re.search(concelho_pattern, page_text, re.UNICODE)

    if match:
        concelho = match.group(1).strip()
        posto = match.group(2).strip().rstrip('N').strip()

        return concelho, posto

    return None, None

def determine_type(file_name):
    """
    Determine the type based on the file name.

    Args:
    file_name (str): The name of the file.

    Returns:
    str: The determined type ('nacionais' or 'estrangeiros').
    """
    if 'naciona' in file_name.lower():
        return 'nacionais'
    elif 'estrangeiro' in file_name.lower():  # This will match both 'estrangeiro' and 'estrangeiros'
        return 'estrangeiros'
    else:
        return 'unknown'

def extract_tables_from_pdf(pdf_path):
    """
    Extract tables from a PDF and process the data to extract relevant fields.

    Args:
    pdf_path (str): The path to the PDF file.

    Returns:
    tuple: A tuple containing the extracted data, 'Concelho', and 'Posto' values.
    """
    data = []
    concelho = None
    posto = None
    file_type = determine_type(pdf_path)

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            print(f"Extracting data from page {i + 1}/{len(pdf.pages)} of {pdf_path}")
            if not concelho or not posto:
                page_text = page.extract_text()
                concelho, posto = extract_concelho_and_posto(page_text)
                print(f"Extracted Concelho: {concelho}, Posto: {posto}")

            tables = page.extract_tables()
            print(f"Found {len(tables)} tables on page {i + 1}")

            for table in tables:
                for row in table:
                    if row[0] == 'NOME COMPLETO FILIAÇÃO DATA NASC.º':
                        continue  # Skip header row

                    cells = row[0].split('\n')

                    if len(cells) < 2:
                        continue  # Skip rows that don't have at least name and one parent

                    # Extract name
                    parent_1, date_in_parent_1 = extract_name_and_date(cells[0].strip())  # Swap: this is actually "Nome Completo"

                    # Initialize parents and date of birth
                    nome_completo = ""
                    parent_2 = ""
                    data_nascimento = date_in_parent_1 or ""

                    # Extract parents and date of birth from remaining cells
                    for cell in cells[1:]:
                        cell = cell.strip()
                        name, date = extract_name_and_date(cell)
                        if date:
                            data_nascimento = date
                            nome_completo = name
                        else:
                            parent_2 = name

                    # Correct the fields if there's only one parent and a date
                    if not nome_completo:
                        nome_completo = parent_1
                        parent_1 = parent_2
                        parent_2 = ""

                    # Create a dictionary for each row
                    row_dict = {
                        "Nome Completo": nome_completo,
                        "Parent 1": parent_1,
                        "Parent 2": parent_2,
                        "Data de Nascimento": data_nascimento,
                        "Concelho": concelho,
                        "Posto": posto,
                        "Type": file_type,
                        "File Name": os.path.basename(pdf_path)
                    }
                    data.append(row_dict)

    return data, concelho, posto

def create_database_and_table(cursor, db_name, table_name):
    """
    Create the database and table if they don't exist.

    Args:
    cursor (mysql.connector.cursor.MySQLCursor): The MySQL cursor.
    db_name (str): The name of the database.
    table_name (str): The name of the table.
    """
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db_name}")
    cursor.execute(f"USE {db_name}")
    create_table_query = f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        id INT AUTO_INCREMENT PRIMARY KEY,
        nome_completo VARCHAR(255),
        parent_1 VARCHAR(255),
        parent_2 VARCHAR(255),
        data_nascimento VARCHAR(255),
        concelho VARCHAR(255),
        posto VARCHAR(255),
        type VARCHAR(255),
        file_name VARCHAR(255)
    )
    """
    cursor.execute(create_table_query)

def insert_data_into_mysql(data, db_config, table_name):
    """
    Insert extracted data into a MySQL database table.

    Args:
    data (list): The extracted data to be inserted.
    db_config (dict): The database configuration containing host, user, password, and database name.
    table_name (str): The name of the table.
    """
    conn = mysql.connector.connect(
        host=db_config['host'],
        user=db_config['user'],
        password=db_config['password']
    )
    cursor = conn.cursor()

    create_database_and_table(cursor, db_config['database'], table_name)

    insert_query = f"""
    INSERT INTO {table_name} (nome_completo, parent_1, parent_2, data_nascimento, concelho, posto, type, file_name)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """

    for row in data:
        cursor.execute(insert_query, (
            row["Nome Completo"],
            row["Parent 1"],
            row["Parent 2"],
            row["Data de Nascimento"],
            row["Concelho"],
            row["Posto"],
            row["Type"],
            row["File Name"]
        ))

    conn.commit()
    cursor.close()
    conn.close()

def find_pdf_files(root_folder):
    """
    Recursively find all PDF files in a folder and its subfolders, ignoring files with specified keywords.

    Args:
    root_folder (str): The root folder to start the search.

    Returns:
    list: A list of paths to PDF files.
    """
    pdf_files = []
    ignore_keywords = ['Provisório', 'Eliminados', 'Elimnado', 'Eliminado', 'Termo']

    for dirpath, _, filenames in os.walk(root_folder):
        for filename in filenames:
            if filename.lower().endswith('.pdf') and not any(keyword.lower() in filename.lower() for keyword in ignore_keywords):
                pdf_files.append(os.path.join(dirpath, filename))

    return pdf_files

def main():
    # Configuration for the database
    db_config = {
        'host': os.getenv('DB_HOST'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD'),
        'database': os.getenv('DB_NAME')
    }
    table_name = 'cidadaos'

    # Prompt the user for the root folder to start the search for PDF files
    root_folder = input("Insira a pasta raiz dos PDF: ")

    # Find all relevant PDF files
    pdf_files = find_pdf_files(root_folder)

    # Option to save data to Excel
    save_to_excel = input("Extrair dados para excel? (sim/não): ").strip().lower() == 'sim'

    for pdf_path in pdf_files:
        # Extract data from each PDF
        data, concelho, posto = extract_tables_from_pdf(pdf_path)

        # Print extracted data for verification
        print(f"Total extracted entries from {pdf_path}: {len(data)}")
        for entry in data[:10]:  # Print the first 10 entries for verification
            print(entry)

        # Insert data into MySQL
        insert_data_into_mysql(data, db_config, table_name)

        # Print the extracted 'Concelho' and 'Posto' for verification
        print(f"Concelho: {concelho}")
        print(f"Posto: {posto}")

        # Save data to Excel file
        if save_to_excel and data:
            df = pd.DataFrame(data)
            output_file_path = f'{os.path.splitext(pdf_path)[0]}.xlsx'
            df.to_excel(output_file_path, index=False)
            print(f'Data extracted and saved to {output_file_path}')
        else:
            print(f"No data extracted from {pdf_path}.")

if __name__ == "__main__":
    main()
