# Vidya

**Vidya** is a vocabulary app I created to help learn new words in both French and English. Whenever I come across a word or expression I want to remember, I simply send it to *Vidya* on WhatsApp, and it responds with the definition while saving it automatically to my vocabulary database on Google Sheets.

### Example of Definitions from Vidya for English to English words:
![](/assets/vocab_whatpass.png)

### Example of Saved Vocabulary in Google Sheets:
![](/assets/vocab_sheet.png)

## How Does It Work?

1. **Send a Message**: The user sends a message to *Vidya*, starting with "vocab" followed by the language code ("en" for English, "fr" for French, "fren" for French to English translation).
2. **Fetch Definition**: *Vidya* fetches the word or expression's definition.
3. **Receive Response**: It sends the definition back via WhatsApp.
4. **Save to Database**: The word or expression, along with its definition, is saved to the vocabulary database.

# Capabilities

- Specify the grammatical category of a word or expression, e.g., `vocab en shepherd (noun)`.
- Retrieve the list of grammatical categories with: `vocab categories {language}`, e.g., `vocab categories fr`.
- Add a quotation to the database by enclosing it in quotation marks, e.g., `vocab en shepherd (noun) "The shepherd guided his flock of sheep across the rolling hills as the sun set behind him."`.
- Request *Vidya* to pronounce a word or sentence in English or French using `say {word}` for English or `dis {mot}` for French, e.g., `say I feel exhausted`, and *Vidya* will reply with an audio pronunciation.
- For the most recently defined word, you can either retain only specific definitions (e.g., `keep 1, 2` to keep only the first two definitions) or remove certain ones (e.g., `delete 3` to remove the third definition).
- Remove a definition from the database using `remove {word}` (e.g. `remove poach` to remove the word "poach") or `remove last def` to remove most recent addition to the database. 
- For English to English definitions, add the word "advanced" to use the Collegiate Dictionary instead of the Learner's Dictionary.

## Where Do the Definitions Come From?

- **English**: Merriam-Webster, a leading authority in American English.
- **French**: Wiktionary.
- **French to English**: Wiktionary.


## Next Steps

- **Add Translation Capabilities**:
    - French ↔ Spanish
    - French ↔ Russian

---