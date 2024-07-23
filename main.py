import os
import re
import logging
import pdfplumber
import pandas as pd
import mysql.connector
from tqdm import tqdm
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables from a .env file
load_dotenv()

# Set up logging with a unique file name based on timestamp
log_filename = f'logs/project_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
if not os.path.exists('logs'):
    os.makedirs('logs')

logging.basicConfig(
    filename=log_filename,
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def extract_name_and_date(text):
    """
    Extracts the name and date from the given text using regular expressions.

    Args:
        text (str): The input text containing the name and date.

    Returns:
        tuple: A tuple containing the name and date if found, otherwise (text, None).
    """
    try:
        date_pattern = r'\d{2}-\d{2}-\d{4}'
        match = re.search(date_pattern, text)
        if match:
            date = match.group()
            name = text.replace(date, '').strip()
            return name, date
        return text, None
    except Exception as e:
        logging.error(f"Error in extract_name_and_date: {e}")
        return text, None

def extract_concelho_and_posto(page_text):
    """
    Extracts the 'Concelho' and 'Posto' values from the page text.

    Args:
        page_text (str): The text from which to extract the values.

    Returns:
        tuple: A tuple containing the 'Concelho' and 'Posto' values if found, otherwise (None, None).
    """
    try:
        concelho_pattern = (
            r'Concelho\s*:\s*([\w\sçÇáéíóúàèìòùãõâêîôûäëïöüÄËÏÖÜñÑ]+)\s*'
            r'Posto\s*:\s*([\w\sçÇáéíóúàèìòùãõâêîôûäëïöüÄËÏÖÜñÑ-]+)'
        )
        match = re.search(concelho_pattern, page_text, re.UNICODE)

        if match:
            concelho = match.group(1).strip()
            posto = match.group(2).strip().rstrip('N').strip()
            return concelho, posto
        return None, None
    except Exception as e:
        logging.error(f"Error in extract_concelho_and_posto: {e}")
        return None, None

def determine_type(file_name):
    """
    Determines the type of document based on the file name.

    Args:
        file_name (str): The name of the file.

    Returns:
        str: The determined type ('nacionais' or 'estrangeiros') or 'unknown'.
    """
    try:
        if 'naciona' in file_name.lower():
            return 'nacionais'
        elif 'estrangeiro' in file_name.lower():
            return 'estrangeiros'
        return 'unknown'
    except Exception as e:
        logging.error(f"Error in determine_type: {e}")
        return 'unknown'

def extract_tables_from_pdf(pdf_path):
    """
    Extracts tables from a PDF file and processes the data.

    Args:
        pdf_path (str): The path to the PDF file.

    Returns:
        tuple: A tuple containing the extracted data, 'Concelho', and 'Posto' values.
    """
    data = []
    concelho, posto = None, None
    file_type = determine_type(pdf_path)

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                logging.info(f"Extracting data from page {i + 1}/{len(pdf.pages)} of {pdf_path}")
                if not concelho or not posto:
                    page_text = page.extract_text()
                    concelho, posto = extract_concelho_and_posto(page_text)
                    logging.info(f"Extracted Concelho: {concelho}, Posto: {posto}")

                tables = page.extract_tables()
                logging.info(f"Found {len(tables)} tables on page {i + 1}")

                for table in tables:
                    data.extend(process_table(table, concelho, posto, file_type, pdf_path))
    except Exception as e:
        logging.error(f"Error in extract_tables_from_pdf: {e}")

    return data, concelho, posto

def process_table(table, concelho, posto, file_type, pdf_path):
    """
    Processes a table extracted from a PDF file.

    Args:
        table (list): The table data.
        concelho (str): The 'Concelho' value.
        posto (str): The 'Posto' value.
        file_type (str): The type of document.
        pdf_path (str): The path to the PDF file.

    Returns:
        list: A list of dictionaries containing the processed data.
    """
    data = []
    try:
        for row in table:
            if row[0] == 'NOME COMPLETO FILIAÇÃO DATA NASC.º':
                continue  # Skip header row

            cells = row[0].split('\n')

            if len(cells) < 2:
                continue  # Skip rows that don't have at least name and one parent

            parent_1, date_in_parent_1 = extract_name_and_date(cells[0].strip())  # Swap: this is actually "Nome Completo"
            nome_completo, parent_2, data_nascimento = process_cells(cells, parent_1, date_in_parent_1)

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
    except Exception as e:
        logging.error(f"Error in process_table: {e}")

    return data

def process_cells(cells, parent_1, date_in_parent_1):
    """
    Processes individual cells in a table row.

    Args:
        cells (list): The list of cells in the row.
        parent_1 (str): The first parent name.
        date_in_parent_1 (str): The date found in the first parent cell.

    Returns:
        tuple: A tuple containing the full name, second parent name, and date of birth.
    """
    nome_completo = ""
    parent_2 = ""
    data_nascimento = date_in_parent_1 or ""

    try:
        for cell in cells[1:]:
            cell = cell.strip()
            name, date = extract_name_and_date(cell)
            if date:
                data_nascimento = date
                nome_completo = name
            else:
                parent_2 = name

        if not nome_completo:
            nome_completo = parent_1
            parent_1 = parent_2
            parent_2 = ""
    except Exception as e:
        logging.error(f"Error in process_cells: {e}")

    return nome_completo, parent_2, data_nascimento

def create_database_and_table(cursor, db_name, table_name):
    """
    Creates the database and table if they don't exist.

    Args:
        cursor (mysql.connector.cursor.MySQLCursor): The MySQL cursor.
        db_name (str): The name of the database.
        table_name (str): The name of the table.
    """
    try:
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
    except Exception as e:
        logging.error(f"Error in create_database_and_table: {e}")

def insert_data_into_mysql(data, db_config, table_name):
    """
    Inserts extracted data into a MySQL database table.

    Args:
        data (list): The extracted data to be inserted.
        db_config (dict): The database configuration containing host, user, password, and database name.
        table_name (str): The name of the table.
    """
    try:
        conn = mysql.connector.connect(
            host=db_config['host'],
            user=db_config['user'],
            password=db_config['password']
        )
        cursor = conn.cursor()

        create_database_and_table(cursor, db_config['database'], table_name)

        insert_query = f"""
        INSERT INTO {table_name} (
            nome_completo, parent_1, parent_2, data_nascimento, concelho, posto, type, file_name
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
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
    except Exception as e:
        logging.error(f"Error in insert_data_into_mysql: {e}")

def find_pdf_files(root_folder):
    """
    Recursively finds all PDF files in a folder and its subfolders, ignoring files with specified keywords.

    Args:
        root_folder (str): The root folder to start the search.

    Returns:
        list: A list of paths to PDF files.
    """
    pdf_files = []
    ignore_keywords = ['Provisório', 'Eliminados', 'Elimnado', 'Eliminado', 'Termo']

    try:
        for dirpath, _, filenames in os.walk(root_folder):
            for filename in filenames:
                if filename.lower().endswith('.pdf') and not any(keyword.lower() in filename.lower() for keyword in ignore_keywords):
                    pdf_files.append(os.path.join(dirpath, filename))
    except Exception as e:
        logging.error(f"Error in find_pdf_files: {e}")

    return pdf_files

def main():
    """
    Main function to process PDF files, extract data, and insert it into a MySQL database.
    """
    # Database configuration
    db_config = {
        'host': os.getenv('DB_HOST'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD'),
        'database': os.getenv('DB_NAME')
    }
    table_name = os.getenv('DB_TABLE')

    # Prompt the user for the root folder to start the search for PDF files
    root_folder = input("Insira a pasta raiz dos PDF: ")
    logging.info(f"Root folder set to {root_folder}")

    # Find all relevant PDF files
    pdf_files = find_pdf_files(root_folder)
    logging.info(f"Found {len(pdf_files)} PDF files to process")

    # Option to save data to Excel
    save_to_excel = input("Extrair dados para excel? (sim/não): ").strip().lower() == 'sim'

    # Process each PDF file
    for pdf_path in tqdm(pdf_files, desc="Processing PDFs", unit="file"):
        try:
            data, concelho, posto = extract_tables_from_pdf(pdf_path)
            logging.info(f"Total extracted entries from {pdf_path}: {len(data)}")
            insert_data_into_mysql(data, db_config, table_name)
            logging.info(f"Concelho: {concelho}, Posto: {posto}")

            # Save data to Excel file if the option is selected
            if save_to_excel and data:
                df = pd.DataFrame(data)
                output_file_path = f'{os.path.splitext(pdf_path)[0]}.xlsx'
                df.to_excel(output_file_path, index=False)
                logging.info(f'Data extracted and saved to {output_file_path}')
            else:
                logging.info(f"No data extracted from {pdf_path}.")
        except Exception as e:
            logging.error(f"Error processing {pdf_path}: {e}")

    # Indicate completion to the user
    print("✅ Processing complete, check the logs for more information.")
    logging.info("Processing complete!😀✌️")

if __name__ == "__main__":
    main()
