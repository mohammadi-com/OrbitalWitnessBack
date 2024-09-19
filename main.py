from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import requests
import re

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Allow specific origins (React app)
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allow all headers
)

@app.get("/usage", status_code=status.HTTP_200_OK, summary="Endpoint to retrieve usage data for the current billing period")
def get_usage() -> JSONResponse:
    """
    Returns:
    - dict: A dictionary containing a 'usage' key with a list of usage records.

    Functionality:
    1. Fetches all messages sent to Orbital Copilot in the current billing period from:
       `https://owpublic.blob.core.windows.net/tech-task/messages/current-period`.
    2. Iterates over each message to construct a usage item containing:
       - 'message_id': The message ID.
       - 'timestamp': The message timestamp.
       - 'report_name' (if available): The name of the report associated with the message.
       - 'credits_used': The number of credits consumed by the message.
    3. For messages with a 'report_id':
       - Attempts to fetch the report details from:
         `https://owpublic.blob.core.windows.net/tech-task/reports/:id`.
       - If the report exists, uses the report's 'cost' as the credits consumed.
       - If the report does not exist (HTTP 404), calculates credits based on the message text.
       - If there's another error fetching the report, raises an HTTPException.
    4. For messages without a 'report_id' or with an invalid 'report_id', calculates the credits
       consumed using the `calculate_credits` function.
    5. Compiles all usage items into a list and returns it in the required JSON format:
       {
           "usage": [
               {
                   "message_id": ...,
                   "timestamp": ...,
                   "report_name": ...,  # Optional
                   "credits_used": ...
               },
               ...
           ]
       }

    Raises:
    - HTTPException: If there's a failure in fetching messages or reports.
    """
    messages_url = "https://owpublic.blob.core.windows.net/tech-task/messages/current-period"

    try:
        messages_response = requests.get(messages_url)
        messages_response.raise_for_status()
        messages = messages_response.json()["messages"]
    except requests.exceptions.RequestException:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch messages")

    usage_list = []

    for message in messages:
        message_id = message.get("id")
        timestamp = message.get("timestamp")
        text = message.get("text", "")
        report_id = message.get("report_id")

        credit_used = 0
        usage_item = {
            "message_id": message_id,
            "timestamp": timestamp
        }

        if report_id:
            report_url = f"https://owpublic.blob.core.windows.net/tech-task/reports/{report_id}"
            report_response = requests.get(report_url)
            if report_response.status_code == status.HTTP_200_OK:
                report_data = report_response.json()
                report_name = report_data.get("name")
                credit_used = report_data.get("credit_cost", 0)
                usage_item["report_name"] = report_name
            elif report_response.status_code == status.HTTP_404_NOT_FOUND:
                credit_used = calculate_credits(text)
            else:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch report")
        else:
            credit_used = calculate_credits(text)

        usage_item["credits_used"] = credit_used
        usage_list.append(usage_item)

    return JSONResponse(content={"usage": usage_list})


def calculate_credits(text: str) -> float:
    """
    Calculate the number of credits consumed by a message based on specific rules.

    Parameters:
    - text (str): The text content of the message.

    Returns:
    - float: The total credits consumed.

    Calculation Steps:
    1. Base Cost: Start with a base cost of 1 credit.
    2. Character Count: Add 0.05 credits for each character in the message.
    3. Word Length Multipliers:
        - Extract words using `re.findall(r"[a-zA-Z'-]+", text)`.
            - Regex Explanation:
                - `[a-zA-Z'-]`: Matches any uppercase letter (`A-Z`), lowercase letter (`a-z`), apostrophe (`'`), or hyphen (`-`).
                - `+`: Matches one or more occurrences of the preceding pattern.
            - This captures words that may include letters, apostrophes, and hyphens.
        - For each word:
            - If the word length is 1-3 characters, add 0.1 credits.
            - If the word length is 4-7 characters, add 0.2 credits.
            - If the word length is 8 or more characters, add 0.3 credits.
    4. Third Vowels:
        - Identify every third character in the text starting from the third character (index 2).
        - For each of these characters, if it is a vowel (`a`, `e`, `i`, `o`, `u`, case-insensitive), add 0.3 credits.
    5. Length Penalty:
        - If the message length exceeds 100 characters, add a penalty of 5 credits.
    6. Unique Word Bonus:
        - If all extracted words are unique (case-sensitive), subtract 2 credits from the total.
    7. Minimum Cost:
        - Ensure the total credits do not fall below 1 credit.
    8. Palindrome Check:
        - Clean the text using `re.sub(r'[^A-Za-z0-9]', '', text).lower()`.
            - Regex Explanation:
                - `[^A-Za-z0-9]`: Matches any character that is NOT an uppercase letter (`A-Z`), lowercase letter (`a-z`), or digit (`0-9`).
                - The caret `^` inside `[]` negates the character class.
                - `re.sub` replaces all non-alphanumeric characters with an empty string.
            - Converts the text to lowercase to ensure case-insensitive comparison.
        - If the cleaned text reads the same forwards and backwards, double the total credits.

    """
    total_credits = 1  # Base cost

    # Character Count Cost
    num_chars = len(text)
    total_credits += num_chars * 0.05

    # Word Length Multipliers
    words = re.findall(r"[a-zA-Z'-]+", text)
    for word in words:
        word_length = len(word)
        if 1 <= word_length <= 3:
            total_credits += 0.1
        elif 4 <= word_length <= 7:
            total_credits += 0.2
        elif word_length >= 8:
            total_credits += 0.3

    # Third Vowels
    vowels = 'aeiouAEIOU'
    third_positions = [i for i in range(2, num_chars, 3)]
    for i in third_positions:
        if text[i] in vowels:
            total_credits += 0.3

    # Length Penalty
    if num_chars > 100:
        total_credits += 5

    # Unique Word Bonus
    if len(words) == len(set(words)):
        total_credits = max(total_credits - 2, 1) # Ensure minimum cost of 1


    # Palindrome Check
    cleaned_text = re.sub(r'[^A-Za-z0-9]', '', text).lower()
    if cleaned_text and cleaned_text == cleaned_text[::-1]:
        total_credits *= 2


    return total_credits # since the rounding was mentioned in the front end section, I didn't round the results here