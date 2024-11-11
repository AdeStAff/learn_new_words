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
from google.cloud import datastore
from io import BytesIO 
from gtts import gTTS
from pydub import AudioSegment


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

def get_audio_message_input(recipient, audio_url):
    return json.dumps(
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "audio",
            "audio": {
                "link": audio_url  
            },
        }
    )

def upload_audio(file_obj):

    url = f"https://graph.facebook.com/{current_app.config['VERSION']}/{current_app.config['PHONE_NUMBER_ID']}/media"
    headers = {
        "Authorization": f"Bearer {current_app.config['ACCESS_TOKEN']}",
    }
    mime_type = 'audio/ogg; codecs=opus'
    if not mime_type:
        print("Could not determine MIME type. Please check the file path and extension.")
        return None

    # Construct payload with both files and data for multipart request
    files = {
        'file': ('audio.opus', file_obj, mime_type)
    }
    data = {
        "messaging_product": "whatsapp"
    }

    # Send the request as multipart/form-data
    response = requests.post(url, headers=headers, files=files, data=data)
    if response.status_code == 200:
        media_id = response.json().get('id')
        print("Media uploaded successfully, media ID:", media_id)
        return media_id
    else:
        print(f"Failed to upload media: {response.status_code} - {response.text}")
        return None

def generate_audio_file(lang, word):
    
    tts = gTTS(text=word, lang=lang)
    mp3_buffer = BytesIO()
    tts.write_to_fp(mp3_buffer)
    mp3_buffer.seek(0)  # Reset buffer position

    # Load the MP3 file from memory and convert to OPUS using pydub
    audio = AudioSegment.from_file(mp3_buffer, format="mp3")
    opus_buffer = BytesIO()
    audio.export(opus_buffer, format="opus")
    opus_buffer.seek(0)  # Reset buffer position

    return opus_buffer

def send_audio_message(recipient, lang, word):

    audio_file = generate_audio_file(lang, word)
    media_id = upload_audio(audio_file)
    if media_id is None:
        error_message = "Media_ID not found"
        data = get_text_message_input(current_app.config["RECIPIENT_WAID"], error_message)
        return send_message(error_message)
    
    url = f"https://graph.facebook.com/{current_app.config['VERSION']}/{current_app.config['PHONE_NUMBER_ID']}/messages"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {current_app.config['ACCESS_TOKEN']}",
    }
    data = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "audio",
        "audio": {
            "id": media_id
        }
    }

    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        print("Audio message sent successfully")
    else:
        print(f"Failed to send audio message: {response.status_code} - {response.text}")

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

def extract_word_and_category_and_quote(text):
    cat, quote, word, quote_style = "", "", text.strip(), None
    match_cat = re.search(r'\((.*)\)', text)
    match_quote = re.search(r'\"(.*?)\"', text) 
    if match_quote:
        quote = match_quote.group(1).strip()
        word = re.sub(r'\s*\"(.*)\"', '', word).strip()
    else:
        match_quote = re.search(r'«(.*?)»', text)
        if match_quote:
            quote = match_quote.group(1).strip()
            word = re.sub(r'\s*«(.*)»', '', word).strip()
    if match_cat:
        cat = match_cat.group(1).strip()
        word = re.sub(r'\s*\((.*)\)', '', word).strip() 

    return [word, cat, quote]

def lookup_en_def(full_word):
    
    word_definition=None
    cat = None
    quote = None
    error_message = None
    load_dotenv()
    api_key = os.getenv("DICT_LEARNER_KEY")
    word_and_cat_and_quote = extract_word_and_category_and_quote(full_word)
    word = word_and_cat_and_quote[0]
    if len(word_and_cat_and_quote[1])>1:
        cat = word_and_cat_and_quote[1]
    if len(word_and_cat_and_quote[2])>1:
        quote = word_and_cat_and_quote[2]
    print("")
    print(word)
    print("")
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
                    return word, cat, word_definition, quote, error_message
                
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

    return word, cat, word_definition, quote, error_message

def lookup_fr_to_en_def(full_word):
    error_message = None
    word_definition = None
    word, cat, quote = extract_word_and_category_and_quote(full_word)
    if len(cat)==0:
        error_message=f"Please specify in parantheses the category of the word: verb, noun, adjective, adverb, expression.\nExample: berger (noun)"
        return full_word, None, None, quote, error_message

    url = f"https://en.wiktionary.org/w/api.php"
    params = {
        "action": "query",
        "format": "json",
        "titles": word,
        "prop": "extracts",
        "explaintext": True,
    }

    response = requests.get(url, params=params)
    data = response.json()
    pages = data["query"]["pages"]
    for page in pages.values():
        extract = page.get("extract", None)
        if extract:
            language_sections = re.split(r"(?m)^==\s+(.*?)\s+==\s*$", extract)
            for i in range(1, len(language_sections), 2):
                language = language_sections[i].strip().lower()  # Language name
                content = language_sections[i + 1].strip()  # Content for that language section
                if language == 'french':
                    sub_sections = re.split(r"(?m)^===\s+(.*?)\s+===\s*$", content)
                    for j in range(1, len(sub_sections), 2):
                        sub_section = re.sub(r'\d+', '',sub_sections[j]).strip().lower()
                        sub_section_content = sub_sections[j + 1].strip()
                        if sub_section == cat:
                            matches = re.findall(r'\n\n(.*?)\n\n\n', sub_section_content, re.DOTALL)
                            if len(matches)==0:
                                matches = re.findall(r'\n\n(.*?)\n', sub_section_content, re.DOTALL)                            
                                if len(matches)==0:
                                    matches = re.findall(r'\n\n(.*)', sub_section_content, re.DOTALL)
                                    if len(matches)==0:
                                        error_message= f"No definition found for the word {word}. Error of matches."
                                        return word, cat, word_definition, quote, error_message

                            definitions_int = matches[0].strip()
                            definitions = definitions_int.split("\n")
                            definitions_final = []
                            for definition in definitions:
                                if len(definition.split()) > 0 and definition.split()[0] not in ["Synonyms:", "Synonym:", "Antonym:", "Antonyms:"] and "―" not in definition:
                                    definitions_final.append(definition)
                            if len(definitions_final)>1:
                                word_definition = ''
                                for definition in definitions_final:
                                    if len (word_definition)>0:
                                        word_definition += f"\n"
                                    word_definition += f"•\u00A0 {definition}"
                            elif len(definitions_final)==1:
                                word_definition = definitions_final[0]
                            else:
                                error_message = f"Word found, but definition not retrieved"
                            return word, cat, word_definition, quote, error_message
                    error_message = f"No definition found for the word {word} in the {cat} category. Are you sure it is a {cat}?"
                    return word, cat, word_definition, quote, error_message
            error_message= f"No definition found for the word {word}"
            return word, cat, word_definition, quote, error_message
        error_message = f"There is a bug, please contact Augustin."
        return word, cat, word_definition, quote, error_message

def lookup_fr_to_fr_def(full_word):
    error_message = None
    word_definition = None
    word, cat, quote = extract_word_and_category_and_quote(full_word)
    if len(cat)==0:
        error_message=f"Please specify in parantheses the category of the word: verb, noun, adjective, adverb, expression.\nExample: berger (noun)"
        return full_word, None, None, quote, error_message

    url = f"https://fr.wiktionary.org/w/api.php"
    params = {
        "action": "query",
        "format": "json",
        "titles": word,
        "prop": "extracts",
        "explaintext": True,
    }

    response = requests.get(url, params=params)
    data = response.json()
    pages = data["query"]["pages"]
    for page in pages.values():
        extract = page.get("extract", None)
        if extract:
            language_sections = re.split(r"(?m)^==\s+(.*?)\s+==\s*$", extract)
            for i in range(1, len(language_sections), 2):
                language = language_sections[i].strip().lower()  # Language name
                content = language_sections[i + 1].strip()  # Content for that language section
                if language == 'français':
                    sub_sections = re.split(r"(?m)^===\s+(.*?)\s+===\s*$", content)
                    for j in range(1, len(sub_sections), 2):
                        sub_section = re.sub(r'\d+', '',sub_sections[j]).strip().lower()
                        sub_section_content = sub_sections[j + 1].strip()
                        if sub_section == cat:
                            matches = re.findall(r'\n\n(.*?)\n\n\n', sub_section_content, re.DOTALL)
                            if len(matches)==0:
                                matches = re.findall(r'\n\n(.*?)\n', sub_section_content, re.DOTALL)                            
                                if len(matches)==0:
                                    matches = re.findall(r'\n\n(.*)', sub_section_content, re.DOTALL)
                                    if len(matches)==0:
                                        error_message= f"No definition found for the word {word}. Error of matches."
                                        return word, cat, word_definition, quote, error_message                            
                            
                            definitions_int = matches[0].strip()
                            definitions = definitions_int.split("\n")
                            definitions_final = []
                            for definition in definitions:
                                if (
                                    len(definition.split()) > 0 
                                    and definition.split()[0] not in {"Synonyms:", "Synonym:", "Antonym:", "Antonyms:"} 
                                    and ("—" not in definition or "— Note" in definition)
                                    and not any(variant in definition.lower() for variant in {word, word + "e", word + "s", word + "es"})
                                ):
                                    definitions_final.append(definition)
                            if len(definitions_final)>1:
                                word_definition = ''
                                for definition in definitions_final:
                                    if len (word_definition)>0:
                                        word_definition += f"\n"
                                    word_definition += f"•\u00A0 {definition}"
                            elif len(definitions_final)==1:
                                word_definition = definitions_final[0]
                            else:
                                error_message = f"Word found, but definition not retrieved"
                            return word, cat, word_definition, quote, error_message
                    error_message = f"No definition found for the word {word} in the {cat} category. Are you sure *{word} is a {cat}?*\n\nIf you need the list of gramatical categories, send a message using the following template: 'vocab categories language'.\n\nFor example, in French: 'vocab categories fr'"
                    return word, cat, word_definition, quote, error_message
            error_message= f"No definition found for the word {word}"
            return word, cat, word_definition, quote, error_message
        error_message = f"There is a bug, please contact Augustin."
        return word, cat, word_definition, quote, error_message

def modify_last_definition(keep=True, to_keep=None,to_del=None):
    
    scope = ["https://spreadsheets.google.com/feeds",'https://www.googleapis.com/auth/spreadsheets',"https://www.googleapis.com/auth/drive.file","https://www.googleapis.com/auth/drive"]
    creds_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS")
    creds_json = creds_json.replace('\n', '\\n')
    creds_dict = json.loads(creds_json)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    
    sheet = client.open_by_key('1CloiuVCnGD38rPQogj1eG_yHAcQ7uxuQ4ICD_CswHhw').sheet1
    column_values = sheet.col_values(4)
    column_words = sheet.col_values(2)
    word = column_words[-1]
    last_value = column_values[-1] if column_values else None
    matches = re.findall(r'•\xa0[^\n]+', last_value)

    if keep:
        final_def = ""
        to_keep_lst = to_keep.split(",")
        to_keep_lst = [int(k) - 1  for k in to_keep_lst]
        for i,j in enumerate(to_keep_lst):
            if i==0:
                final_def += matches[j]
            else:
                final_def += "\n" + matches[j]
        if len(re.findall(r'•\xa0[^\n]+', final_def))==1:
            final_def = re.sub(r'•\xa0','',final_def).strip()
    
    else:
        final_def_lst = matches
        to_del_lst = to_del.split(",")
        to_del_lst = sorted([int(k) - 1  for k in to_del_lst], reverse=True)
        for i in to_del_lst:
            del final_def_lst[i]
        
        final_def = ""
        
        for j,k in enumerate(final_def_lst):
            if j==0:
                final_def += k
            else:
                final_def += "\n" + k
        if len(re.findall(r'•\xa0[^\n]+', final_def))==1:
            final_def = re.sub(r'•\xa0','',final_def).strip()

    num_rows = len(sheet.get_all_values())
    sheet.update_cell(num_rows, 4, final_def)
    
    return word, final_def

def add_row_to_padme_vocab(language, word):
    
    error_status = False
    print(language)

    if language == "en":
        word, cat, word_definition, quote, error_message = lookup_en_def(word)
    
    if language == "fren":
        word, cat, word_definition, quote, error_message = lookup_fr_to_en_def(word)

    if language == "fr":
        word, cat, word_definition, quote, error_message = lookup_fr_to_fr_def(word)

    if language in {"categories", "categorie", "category"}:
        if word.strip().lower()=='fr':
            error_message = f"""Please choose a gramatical category among the following:
            • Nom commun
            • Nom propre
            • Adjectif
            • Verbe
            • Adverbe
            • Pronom
            • Préposition
            • Conjonction
            • Interjection
            • Déterminant
            • Article
            • Onomatopée
            • Locution nominale
            • Locution verbale
            • Locution adjectivale
            • Locution adverbiale
            • Locution prépositive
            """
        elif word.strip().lower()=='fren':
            error_message = """Please choose a gramatical category among the following:
            • Noun
            • Proper noun
            • Adjective
            • Verb
            • Adverb
            • Pronoun
            • Preposition
            • Conjunction
            • Interjection
            • Determiner
            • Article
            • Onomatopoeia
            • Phrase
            """


        elif word.strip().lower()=='en':
            error_message = """No need to specify the category every time, but here is the list:
            • Noun
            • Pronoun
            • Verb
            • Adjective
            • Adverb
            • Preposition
            • Conjunction
            • Interjection
            • Article"""
        
        else :
            error_message = "This language does not exist or is not supported."
    
    if language not in {"en", "fr", "fren", "categories","categorie", "category"}:
        error_message = "This language does not exist or is not supported."
    

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

        new_row = [language, word, cat, word_definition, quote]

        sheet.insert_row(new_row, num_rows + 1)
        if word_definition[0]==f'•':
            message = f"*{word}*:\n{word_definition}"
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
    message_content = full_message_body.split(" ",1)[1].strip().lower()
        
    if service == 'vocab':

        for word in words:
            response_message, error_status = add_row_to_padme_vocab(language, word)
            if error_status:
                response_message += f"\n\nNo action taken."
            else:
                response_message += f"\n\n*{word}* added to database."
            data = get_text_message_input(current_app.config["RECIPIENT_WAID"], response_message)
            send_message(data)
    
    elif service == 'dis':
        try:    
            send_audio_message(current_app.config["RECIPIENT_WAID"],
                                lang="fr",
                                word=message_content)
        except Exception as e:
            error_message = f"Tried to send you a vocal, but could not: {e}"
            data = get_text_message_input(current_app.config["RECIPIENT_WAID"], error_message)
            send_message(data)

    elif service == 'say':
        try:
            send_audio_message(current_app.config["RECIPIENT_WAID"],
                            lang="en",
                            word=message_content)
        except Exception as e:
            error_message = f"Tried to send you a vocal, but could not: {e}"
            data = get_text_message_input(current_app.config["RECIPIENT_WAID"], error_message)
            send_message(data)

    elif service == 'keep':
        word, final_def = modify_last_definition(keep=True, to_keep=message_content)
        update_message = "*Definition updated* ✅" + "\n\n*word*:\n" + final_def
        data = get_text_message_input(current_app.config["RECIPIENT_WAID"], update_message)
        send_message(data)

    elif service== 'delete':
        modify_last_definition(keep=False, to_del=message_content)
        update_message = "*Definition updated* ✅" + "\n\n*word*:\n" + final_def
        data = get_text_message_input(current_app.config["RECIPIENT_WAID"], update_message)
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
