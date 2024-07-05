import os
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
import traceback
import ast
import openai
import csv
import aiohttp
import asyncio
import re
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

app = Flask(__name__)
CORS(app)

subscription_key = '071893d9ac3041b8abd6cb79e76c3517'
endpoint = 'https://findataextract.cognitiveservices.azure.com/'
ocr_url = f"{endpoint}/vision/v3.1/read/analyze"
client = openai.AzureOpenAI(
    azure_endpoint="https://finkdataopenai.openai.azure.com/",
    api_key='d57b4f240c6f4c12bb8d316469e45f69',
    api_version="2024-02-15-preview"
)

def extract_text_fromfile(file_contents):
    headers = {
        'Content-Type': 'application/octet-stream',
        'Ocp-Apim-Subscription-Key': subscription_key
    }
    params = {
        'language': 'en',
        'detectOrientation': 'true',
        'mode': 'Printed',
        'model': 'prebuilt-receipt'
    }
    try:
        response = requests.post(ocr_url, headers=headers, params=params, data=file_contents)
        response.raise_for_status()
        if response.status_code == 202:
            operation_url = response.headers["Operation-Location"]
            while True:
                response_status = requests.get(operation_url, headers=headers)
                status = response_status.json()
                if status['status'] == 'succeeded':
                    break
            extracted_text = ''
            for result in status['analyzeResult']['readResults']:
                for line in result['lines']:
                    extracted_text += line['text'] + " "
            return extracted_text
        else:
            return None
    except requests.exceptions.RequestException as e:
        print("Error:", e)
        return None

def query_api(prompt):
    try:
        completion = client.chat.completions.create(
            model="gpt-35-turbo",
            messages=prompt,
            temperature=0.7,
            max_tokens=800,
            top_p=0.95,
            frequency_penalty=0,
            presence_penalty=0,
            stop=None
        )
        return completion.choices[0].message.content
    except Exception as e:
        print("Error querying API:", e)
        return None
    
def create_csv(data_dict, invoice_file_name, custom_mappings):
    columns = [
        "original_filename",
        "shipto_address",
        "buyer_address",
        "po_number",
        "subtax_amount",
        "seller_address",
        "seller_name",
        "buyer_name",
        "seller_phone",
        "buyer_vat_number",
        "invoice_date",
        "client_id",
        "total_tax_amount",
        "total_tax_%",
        "subtotal",
        "payment_due_date",
        "invoice_amount",
        "subtax_name",
        "seller_vat_number",
        "payto_name",
        "total_due_amount",
        "invoice_number",
        "subtax_%",
        "seller_email",
        "shipto_name"
    ]
    file_exists = os.path.isfile(invoice_file_name)
    # print(invoice_file_name)
    with open(invoice_file_name, 'a', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=columns)
        if not file_exists:
            writer.writeheader()  #
        row = {}
        # row['original_filename'] = file_name
        # Iterate over each column name
        for column in columns:
            # Check if there's a custom mapping for this column
            if column in custom_mappings:
                key = custom_mappings[column]
                # If the key exists in the dictionary, assign its value to the column in the row dictionary
                if key in data_dict:
                    row[column] = data_dict[key]
                else:
                    row[column] = ''  # If key not found, insert empty string
            else:
                row[column] = ''  # If no custom mapping, insert empty string
        # Write the row to CSV
        writer.writerow(row)
        

def extract_invoice_details(file_contents, main_with_filename):
    extracted_text = extract_text_fromfile(file_contents)
    if extracted_text:
        prompt = [
            {"role": "system", "content": f"Please find the Invoice number(s) or Bill number(s), shipto address give only address, Buyer address give only address both Seller address and Buyer address should be different, Po_number, Sub_tax Amount like cgst and sgst print only the amount in list without name, Sub_tax Name give only one name in list,Seller Address, Seller Name, Buyer Name, Seller Phone number, Buyer VAT number, Invoice Date not time, Total_tax Amount including all the taxes, Total_tax Percentage,Seller VAT number, Payto_Name, Total_Due Amount, Sub_tax Percentage give only the numbers, Payment_Due Date, Net_d,Seller Email address, Shipto Name from this text, If you can't find print only NA. Give the output in json format. Don't print any extra string or symbol than I asked for. Match th values with the given key 'original_filename','shipto_address','buyer_address','po_number','subtax_amount','seller_address','seller_name','buyer_name','seller_phone','buyer_vat_number','invoice_date','client_id','total_tax_amount','total_tax_%','subtotal','payment_due_date','invoice_amount','subtax_name','seller_vat_number','payto_name','total_due_amount','invoice_number','subtax_%','seller_email','shipto_name'. Don't change the key match the values with this keys. For a date change the format as 'dd-mm-yyy'"},
            {"role":"user","content":f"Extract details from this text"}
        ]
        prompt[1]["content"] += extracted_text
        api_response = query_api(prompt)
        if api_response:
            try:
                main = ast.literal_eval(api_response)
                main['original_filename'] = main_with_filename
                
                
                column_to_key_mapping = {
                    "original_filename": 'original_filename',
                    "shipto_address": 'shipto_address' ,
                    "buyer_address": 'buyer_address',
                    "po_number": 'po_number',
                    "subtax_amount": 'subtax_amount',
                    "seller_address": 'seller_address',
                    "seller_name": 'seller_name',
                    "buyer_name": 'buyer_name',
                    "seller_phone": 'seller_phone',
                    "buyer_vat_number": 'buyer_vat_number',
                    "invoice_date": 'invoice_date', 
                    "total_tax_amount": 'total_tax_amount',
                    "subtotal": 'subtotal',
                    "payment_due_date": 'payment_due_date',
                    "invoice_amount": 'invoice_amount',
                    "subtax_name": 'subtax_name',
                    "seller_vat_number":'seller_vat_number',
                    "payto_name": 'payto_name',
                    "total_due_amount":'total_due_amount',
                    "invoice_number": 'invoice_number',
                    "subtax_%": 'subtax_%',
                    "seller_email": 'seller_email',
                    "shipto_name": 'shipto_name',
                }

                # Create dictionary for invoice data
                invoice_data = {}
                for column, key in column_to_key_mapping.items():
                    invoice_data[column] = main.get(key, 'NA')

                return invoice_data

            except (SyntaxError, ValueError) as e:
                print("Error extracting invoice details:", e)
                return None
        else:
            print("Empty API response")
            return None
    else:
        print("Failed to extract text from file")
        return None

def process_uploaded_files(files):
    all_invoice_data = []
    for uploaded_file in files:
        if uploaded_file.filename.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg')):
            file_contents = uploaded_file.read()
            invoice_data = extract_invoice_details(file_contents, uploaded_file.filename)
            if invoice_data:
                # Iterate over the invoice data and take only the first value if it's a list
                for key, value in invoice_data.items():
                    if isinstance(value, list):
                        invoice_data[key] = value[0] if value else None
                all_invoice_data.append(invoice_data)
                # print(invoice_data)  # Print the invoice data
    return all_invoice_data  # Return the list of invoice data



@app.route('/downloadfile', methods=['POST', 'GET'])
def download_file():
    GOOGLE_DRIVE_CREDENTIALS_FILE = r'D:\invoice details\invoice_details\final\src\pdfconvertor-424707-469b51fe5c6a.json'
    # SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
    try:
        drive_link = request.args.get('drive_link')
        service = authenticate_google_drive(GOOGLE_DRIVE_CREDENTIALS_FILE)
        files = list_files_in_folder(service, drive_link)
        # extracted_details = []

        for file in files:
                if file['mimeType'] in ['application/pdf', 'image/jpeg', 'image/png', 'image/jpg']:
                    file_id = file['id']
                    
        
        # print(files)

        return jsonify({'success': True, 'data': files}), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
def authenticate_google_drive(credentials_file):
    credentials = service_account.Credentials.from_service_account_file(
        credentials_file, scopes=SCOPES)
    service = build('drive', 'v3', credentials=credentials)
    return service


def list_files_in_folder(service, url):
    match = re.search(r'/folders/([\w-]+)', url)
    if match:
        folder_id = match.group(1)
        results = service.files().list(
            q=f"'{folder_id}' in parents",
            pageSize=10,
            fields="files(id, name, mimeType)").execute()
        files = results.get('files', [])
        # Filter only PDF and image files
        filtered_files = [f for f in files if f['mimeType'] in ['application/pdf', 'image/jpeg', 'image/png', 'image/jpg']]
        return filtered_files
    elif "/file/d/" in url:
        file_id = url.split('/')[-2]
        file_metadata = service.files().get(fileId=file_id, fields="name, mimeType").execute()
        if file_metadata['mimeType'] in ['application/pdf', 'image/jpeg', 'image/png', 'image/jpg']:
            return [{'id': file_id, 'name': file_metadata['name'], 'mimeType': file_metadata['mimeType']}]
        else:
            print("Unsupported file type:", file_metadata['mimeType'])
            return []
    else:
        print("Invalid Google Drive URL. Please provide a valid URL for a folder or a direct file link.")
        return []


@app.route('/uploadFiles', methods=['POST'])
def upload_files():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        uploaded_files = request.files.getlist('file')
        all_invoice_data = process_uploaded_files(uploaded_files)
        
        if all_invoice_data:
            # Combine all invoice data into a single dictionary
            combined_invoice_data = {}
            for invoice_data in all_invoice_data:
                combined_invoice_data.update(invoice_data)
            
            # Path to store the CSV file
            csv_file_path = 'output.csv'
            create_csv(invoice_data, csv_file_path, custom_mappings={
                    "original_filename": 'original_filename',
            "shipto_address": 'shipto_address' ,
            "buyer_address": 'buyer_address',
            "po_number": 'po_number',
            "subtax_amount": 'subtax_amount',
            "seller_address": 'seller_address',
            "seller_name": 'seller_name',
            "buyer_name": 'buyer_name',
            "seller_phone": 'seller_phone',
            "buyer_vat_number": 'buyer_vat_number',
            "invoice_date": 'invoice_date', 
            "total_tax_amount": 'total_tax_amount',
            "subtotal": 'subtotal',
            "payment_due_date": 'payment_due_date',
            "invoice_amount": 'invoice_amount',
            "subtax_name": 'subtax_name',
            "seller_vat_number":'seller_vat_number',
            "payto_name": 'payto_name',
            "total_due_amount":'total_due_amount',
            "invoice_number": 'invoice_number',
            "subtax_%": 'subtax_%',
            "seller_email": 'seller_email',
            "shipto_name": 'shipto_name',})  # You can define custom mappings if needed

            # No need to modify the format here, send the data directly
            return jsonify({'invoice_data': combined_invoice_data, 'csv_file_path': csv_file_path}), 200
        else:
            return jsonify({'error': 'Failed to process uploaded files'}), 500
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    

client = openai.AzureOpenAI(
    azure_endpoint="https://finkdataopenai.openai.azure.com/",
    api_key='d57b4f240c6f4c12bb8d316469e45f69',
    api_version="2024-02-15-preview"
)

def query_api(prompt):
    try:
        completion = client.chat.completions.create(
            model="gpt-35-turbo",
            messages=prompt,
            temperature=0.7,
            max_tokens=800,
            top_p=0.95,
            frequency_penalty=0,
            presence_penalty=0,
            stop=None
        )
        return completion.choices[0].message.content
    except Exception as e:
        print("Error querying API:", e)
        return None

def extract_text_from_url(file_url):
    subscription_key = '071893d9ac3041b8abd6cb79e76c3517'
    ocr_url = 'https://findataextract.cognitiveservices.azure.com/vision/v3.1/read/analyze'
    headers = {
        'Content-Type': 'application/json',
        'Ocp-Apim-Subscription-Key': subscription_key
    }
    params = {
        'language': 'en',
        'detectOrientation': 'true',
        'mode': 'Printed',
        'model': 'prebuilt-receipt'
    }
    json_payload = {
        'url': file_url
    }
    try:
        response = requests.post(ocr_url, headers=headers, params=params, json=json_payload)
        response.raise_for_status()
        if response.status_code == 202:
            operation_url = response.headers["Operation-Location"]
            while True:
                response_status = requests.get(operation_url, headers=headers)
                status = response_status.json()
                if status['status'] == 'succeeded':
                    break
            extracted_text = ''
            for result in status['analyzeResult']['readResults']:
                for line in result['lines']:
                    extracted_text += line['text'] + " "
            return extracted_text
        else:
            return None
    except requests.exceptions.RequestException as e:
        print("Error:", e)
        return None

def process_extracted_text(extracted_text, file_name):
    if extracted_text:
        prompt = [
            {"role": "system", "content": f"Please find the Invoice number(s) or Bill number(s), shipto address give only address, Buyer address give only address both Seller address and Buyer address should be different, Po_number, Sub_tax Amount like cgst and sgst print only the amount in list without name, Sub_tax Name give only one name in list,Seller Address, Seller Name, Buyer Name, Seller Phone number, Buyer VAT number, Invoice Date not time, Total_tax Amount including all the taxes, Total_tax Percentage,Seller VAT number, Payto_Name, Total_Due Amount, Sub_tax Percentage give only the numbers, Payment_Due Date, Net_d,Seller Email address, Shipto Name from this text, If you can't find print only NA. Give the output in json format. Don't print any extra string or symbol than I asked for. Match th values with the given key 'original_filename','shipto_address','buyer_address','po_number','subtax_amount','seller_address','seller_name','buyer_name','seller_phone','buyer_vat_number','invoice_date','client_id','total_tax_amount','total_tax_%','subtotal','payment_due_date','invoice_amount','subtax_name','seller_vat_number','payto_name','total_due_amount','invoice_number','subtax_%','seller_email','shipto_name'. Don't change the key match the values with this keys. For a date change the format as 'dd-mm-yyy'"},
            {"role":"user","content":f"Extract details from this text"}
        ]
        prompt[1]["content"] += extracted_text
        
        api_response = query_api(prompt)
        
        if api_response:
            try:
                main = ast.literal_eval(api_response)
                # Loop through the dictionary and if any value is a list, take the first element
                for key, value in main.items():
                    if isinstance(value, list):
                        main[key] = value[0]
                main['original_filename'] = file_name
                return main
            except Exception as e:
                print("Error extracting details:", e)
                return None

    return None

@app.route('/processExtractedText', methods=['POST'])
def process_extracted_text_endpoint():
    try:
        # Extract file data from the request
        file_data = request.json 
        print(file_data) # Assuming the file data is sent in JSON format
        
        if 'id' in file_data and 'mimeType' in file_data and 'name' in file_data:
            # Process a single file
            file_info = file_data
            if file_info['mimeType'] in ['application/pdf', 'image/jpeg', 'image/png', 'image/jpg']:
                file_id = file_info['id']
                file_name = file_info['name']
                download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
                
                # Extract text from the provided URL using OCR
                extracted_text = extract_text_from_url(download_url)
                
                if extracted_text:
                    # Process the extracted text
                    details = process_extracted_text(extracted_text, file_name)
                    
                    if details:
                        return jsonify({'success': True, 'extracted_details': details}), 200
                    else:
                        return jsonify({'error': 'Failed to extract details from file.'}), 500
                else:
                    return jsonify({'error': 'Failed to extract text from file.'}), 500
            else:
                return jsonify({'error': 'Unsupported file type.'}), 400
        else:
            return jsonify({'error': 'Invalid file data format.'}), 400

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

    
if __name__ == '__main__':
    app.run(debug=True)

    
