import logging
from flask import current_app, jsonify
import json
import requests
import re
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from pprint import pprint as pp
import os
from dotenv import load_dotenv
from larousse_api import larousse
from google.cloud import datastore

def is_duplicate_message(client, message_id):
    # Create a key for the message ID
    key = client.key("MessageID", message_id)
    entity = client.get(key)
    return entity is not None

def store_message_id(client, message_id):
    # Create a new entity to store the message ID
    key = client.key("MessageID", message_id)
    entity = datastore.Entity(key)
    entity.update({"processed": True})
    client.put(entity)

def log_http_response(response):
    logging.info(f"Status: {response.status_code}")
    logging.info(f"Content-type: {response.headers.get('content-type')}")
    logging.info(f"Body: {response.text}")

def get_text_message_input(recipient, text):
    return json.dumps(
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
    )

def send_message(data):
    headers = {
        "Content-type": "application/json",
        "Authorization": f"Bearer {current_app.config['ACCESS_TOKEN']}",
    }

    url = f"https://graph.facebook.com/{current_app.config['VERSION']}/{current_app.config['PHONE_NUMBER_ID']}/messages"

    try:
        response = requests.post(
            url, data=data, headers=headers, timeout=10
        )  # 10 seconds timeout as an example
        response.raise_for_status()  # Raises an HTTPError if the HTTP request returned an unsuccessful status code
    except requests.Timeout:
        logging.error("Timeout occurred while sending message")
        return jsonify({"status": "error", "message": "Request timed out"}), 408
    except (
        requests.RequestException
    ) as e:  # This will catch any general request exception
        logging.error(f"Request failed due to: {e}")
        return jsonify({"status": "error", "message": "Failed to send message"}), 500
    else:
        # Process the response as normal
        log_http_response(response)
        return response

def process_text_for_whatsapp(text):
    # Remove brackets
    pattern = r"\【.*?\】"
    # Substitute the pattern with an empty string
    text = re.sub(pattern, "", text).strip()

    # Pattern to find double asterisks including the word(s) in between
    pattern = r"\*\*(.*?)\*\*"

    # Replacement pattern with single asterisks
    replacement = r"*\1*"

    # Substitute occurrences of the pattern with the replacement
    whatsapp_style_text = re.sub(pattern, replacement, text)

    return whatsapp_style_text

def extract_word_and_category(text):
    match = re.search(r'\((\w+)\)', text)
    if match:
        cat = match.group(1)  
        word = re.sub(r'\s*\(\w+\)', '', text).strip() 
        return [word, cat]
    else:
        return [text, ""]

def lookup_en_def(full_word):
    
    error_message = None
    cat = None
    word_definition=None
    load_dotenv()
    api_key = os.getenv("DICT_LEARNER_KEY")
    word_and_cat = extract_word_and_category(full_word)
    word = word_and_cat[0]
    if len(word_and_cat[-1])>1:
        cat = word_and_cat[-1]

    url = f"https://www.dictionaryapi.com/api/v3/references/learners/json/{word}?key={api_key}"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        
        # If word not found

        if len(data)>0 and "fl" not in data[0]:
            # Use other dictionnary api
            second_api_key = os.getenv("DICT_DICT_KEY")
            
            url = f"https://www.dictionaryapi.com/api/v3/references/collegiate/json/{word}?key={second_api_key}"
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                if len(data)>0 and "fl" not in data[0]:
                    error_message = f"{word} not found in any dictionnary."
                    return word, cat, word_definition, error_message
                
        if cat is not None:
            i = 0
            found_cat = False
            while i<len(data):
                if "fl" in data[i] and data[i]["fl"]==cat:
                    found_cat = True
                    break
                i += 1
            if found_cat==True:
                if len(data[i]["shortdef"])>1:
                    word_definition = ''
                    for definition in data[i]["shortdef"]:
                        if len(word_definition)>0:
                            word_definition += f"\n"    
                        word_definition += f"•\u00A0 {definition}"
                    word_definition
                else:
                    word_definition = data[i]["shortdef"][0]
            else:
                word_definition = ''
                error_message = f"{word} is not a {cat}."
        else:
            if len(data) > 0 and "shortdef" and "fl"in data[0]:
                cat = data[0]["fl"]
                if len(data[0]["shortdef"])>1:
                    word_definition = ''
                    for definition in data[0]["shortdef"]:
                        if len(word_definition)>0:
                            word_definition += f"\n"    
                        word_definition += f"•\u00A0 {definition}"
                else:
                    try:
                        word_definition = data[0]["shortdef"][0]
                    except IndexError:
                        try:
                            second_api_key = os.getenv("DICT_DICT_KEY")
                            url = f"https://www.dictionaryapi.com/api/v3/references/collegiate/json/{word}?key={second_api_key}"
                            response = requests.get(url)
                            if response.status_code == 200:
                                data = response.json()
                                if "fl" in data[0] and "shortdef" in data[0]:
                                    cat = data[0]["fl"]
                                    if len(data[0]["shortdef"])>1:
                                        word_definition = ''
                                        for definition in data[0]["shortdef"]:
                                            if len(word_definition)>0:
                                                word_definition += f"\n"    
                                            word_definition += f"•\u00A0 {definition}"
                                    elif len(data[0]["shortdef"]) == 1 :
                                        word_definition = data[0]["shortdef"][0]
                                else:
                                    error_message = f"No definition found for the word '{word}'"
                            else:
                                error_message = f"Failed to use the API for the word '{word}'"

                        except:
                            error_message = f"No definition found for the word '{word}'"

            else:
                word_definition = ''
                error_message = f"No definition found for the word '{word}'"

    else:
        print(f"Failed to retrieve data: {response.status_code}")

    return word, cat, word_definition, error_message

def add_row_to_padme_vocab(language, word):
    
    error_status = False

    if language == "en":
        word, cat, word_definition, error_message = lookup_en_def(word)

    if error_message is not None:
        error_status = True
        return error_message, error_status

    elif cat is not None and word_definition is not None:

        scope = ["https://spreadsheets.google.com/feeds",'https://www.googleapis.com/auth/spreadsheets',"https://www.googleapis.com/auth/drive.file","https://www.googleapis.com/auth/drive"]
        creds_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
        creds_dict = json.loads(creds_json)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open_by_key('1CloiuVCnGD38rPQogj1eG_yHAcQ7uxuQ4ICD_CswHhw').sheet1
        num_rows = len(sheet.get_all_values())

        new_row = [language, word, cat, word_definition]

        sheet.insert_row(new_row, num_rows + 1)
        if word_definition[0]==f'•':
            message = f"*{word}*:\n {word_definition}"
        else:
            message = f"*{word}*: {word_definition}"
        
    else:
        message = "Retrieval failed."

    return message, error_status

def process_whatsapp_message(body):

    message = body["entry"][0]["changes"][0]["value"]["messages"][0]
    full_message_body = message["text"]["body"]
    service = full_message_body.split()[0].strip().lower()
    language = full_message_body.split()[1].lower()
    words = [word.strip() for word in full_message_body.split(' ',2)[-1].split(',')]
        
    if service == 'vocab':

        if language == 'en':
            for word in words:
                response_message, error_status = add_row_to_padme_vocab(language, word)
                if error_status:
                    response_message += f"\n\nNo action taken."
                else:
                    response_message += f"\n\n*{word}* added to database."
                data = get_text_message_input(current_app.config["RECIPIENT_WAID"], response_message)
                send_message(data)
        elif language == 'fr':
            for word in words:
                response_message = add_row_to_padme_vocab(language, word)
                response_message += f"\n\n*{word}* added to database."
                data = get_text_message_input(current_app.config["RECIPIENT_WAID"], response_message)
                send_message(data)
        elif language == 'ru':
            for word in words:
                response_message = add_row_to_padme_vocab(language, word)
                response_message += f"\n\n*{word}* added to database."
                data = get_text_message_input(current_app.config["RECIPIENT_WAID"], response_message)
                send_message(data)

    else:
        response_message = "Error - no action taken."
        data = get_text_message_input(current_app.config["RECIPIENT_WAID"], response_message)
        send_message(data)

def is_valid_whatsapp_message(body):
    """
    Check if the incoming webhook event has a valid WhatsApp message structure.
    """
    return (
        body.get("object")
        and body.get("entry")
        and body["entry"][0].get("changes")
        and body["entry"][0]["changes"][0].get("value")
        and body["entry"][0]["changes"][0]["value"].get("messages")
        and body["entry"][0]["changes"][0]["value"]["messages"][0]
    )
