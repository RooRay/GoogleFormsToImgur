import os
import re
import base64
import requests
import numpy as np
import matplotlib.pyplot as plt

from dotenv import load_dotenv # type: ignore
from google.oauth2 import service_account
from googleapiclient.discovery import build

# -------------------------------------------------------------------------
# 1) CONFIGURATION
# -------------------------------------------------------------------------
load_dotenv() # Load variables from .env file


IMGUR_CLIENT_ID = os.getenv("IMGUR_CLIENT_ID")
IMGUR_CLIENT_SECRET = os.getenv("IMGUR_CLIENT_SECRET")

SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "./output")  # Default fallback for OUTPUT_DIR

# -------------------------------------------------------------------------
# 2) IMGUR OAUTH2 (PIN FLOW)
# -------------------------------------------------------------------------
def get_pin_authorization_url(client_id):
    """
    Construct the Imgur OAuth2 authorization URL for the PIN flow.
    The user must visit this URL, log in, and retrieve a PIN code.
    """
    return (
        "https://api.imgur.com/oauth2/authorize"
        f"?client_id={client_id}"
        "&response_type=pin"
    )

def exchange_pin_for_tokens(client_id, client_secret, pin_code):
    """
    Exchanges the given PIN for an access token and refresh token.
    """
    url = "https://api.imgur.com/oauth2/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "pin",
        "pin": pin_code
    }
    r = requests.post(url, data=data)
    if r.status_code != 200:
        raise Exception(f"Error exchanging PIN for tokens: {r.text}")
    resp = r.json()
    # resp contains: access_token, refresh_token, account_username, etc.
    return resp["access_token"], resp["refresh_token"]

def refresh_imgur_access_token(client_id, client_secret, refresh_token):
    """
    If you already have a refresh token, you can call this
    to get a new access token (and possibly a new refresh token).
    """
    url = "https://api.imgur.com/oauth2/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    r = requests.post(url, data=data)
    if r.status_code != 200:
        raise Exception(f"Failed to refresh token: {r.text}")
    resp = r.json()
    return resp["access_token"], resp.get("refresh_token", refresh_token)

# -------------------------------------------------------------------------
# 3) IMGUR API (Authenticated)
# -------------------------------------------------------------------------
def create_imgur_album_oauth(album_title, access_token):
    """
    Creates an album under your Imgur account with 'hidden' privacy.
    Returns album_id (public) if successful.
    """
    url = "https://api.imgur.com/3/album"
    headers = {"Authorization": f"Bearer {access_token}"}
    json_data = {
        "title": album_title,
        "privacy": "hidden"
    }
    response = requests.post(url, headers=headers, json=json_data)
    result = response.json()
    if result.get("success"):
        return result["data"]["id"]  # The public album ID
    else:
        raise Exception("Failed to create Imgur album: " + str(result))

def upload_image_to_imgur_oauth(image_path, title, album_id, access_token):
    """
    Uploads an image to Imgur under the user's account, assigned to a specific album.
    """
    url = "https://api.imgur.com/3/upload"
    headers = {"Authorization": f"Bearer {access_token}"}
    with open(image_path, "rb") as image_file:
        image_data = image_file.read()
    b64_image = base64.b64encode(image_data)
    
    data = {
        "image": b64_image,
        "type": "base64",
        "title": title,
        "album": album_id
    }
    response = requests.post(url, headers=headers, data=data)
    result = response.json()
    if result.get("success"):
        return result["data"]["link"]
    else:
        raise Exception("Failed to upload image: " + str(result.get("data")))

def delete_imgur_album(album_id, access_token):
    """
    Deletes an album under your account by album ID.
    """
    url = f"https://api.imgur.com/3/album/{album_id}"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.delete(url, headers=headers)
    if response.status_code == 200:
        print(f"Album {album_id} deleted successfully.")
    else:
        raise Exception(f"Failed to delete album {album_id}: {response.text}")

# -------------------------------------------------------------------------
# 4) GOOGLE FORMS: RETRIEVE FORM + RESPONSES
# -------------------------------------------------------------------------
def extract_form_id(form_url):
    """
    Extracts the form ID from a Google Form URL, e.g. from:
    https://docs.google.com/forms/d/FORM_ID/edit
    """
    match = re.search(r'/d/([^/]+)', form_url)
    if match:
        return match.group(1)
    else:
        raise ValueError("Could not extract form ID from the provided URL.")

def get_form_data(form_id):
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=[
            'https://www.googleapis.com/auth/forms.responses.readonly',
            'https://www.googleapis.com/auth/forms.body.readonly'
        ]
    )
    service = build('forms', 'v1', credentials=credentials)
    form_data = service.forms().get(formId=form_id).execute() # pylint: disable=no-member
    return form_data

def get_question_map(form_data):
    """
    Builds a mapping from question ID to question title.
    """
    question_map = {}
    for item in form_data.get('items', []):
        question = item.get('questionItem', {}).get('question', {})
        qid = question.get('questionId')
        title = item.get('title', 'Untitled Question')
        if qid:
            question_map[qid] = title
    return question_map

def get_form_responses(form_id):
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=['https://www.googleapis.com/auth/forms.responses.readonly']
    )
    service = build('forms', 'v1', credentials=credentials)
    response = service.forms().responses().list(formId=form_id).execute() # pylint: disable=no-member
    return response.get('responses', [])

def count_responses_per_question(question_map, responses):
    """
    Returns a dict mapping each question title -> {answer: count, ...}.
    """
    counts = {title: {} for title in question_map.values()}
    for response in responses:
        answers = response.get('answers', {})
        for qid, answer_obj in answers.items():
            question_title = question_map.get(qid, qid)
            text_answers = answer_obj.get('textAnswers', {}).get('answers', [])
            if text_answers:
                answer_text = text_answers[0].get('value', '').strip()
            else:
                answer_text = ''
            if answer_text:
                counts[question_title][answer_text] = (
                    counts[question_title].get(answer_text, 0) + 1
                )
    return counts

# -------------------------------------------------------------------------
# 5) MATPLOTLIB: GENERATE PIE CHARTS
# -------------------------------------------------------------------------
def generate_pie_chart(question_title, answer_counts, output_filename):
    """
    Generates a pie chart with external labels and lines, no autopct inside the slices.
    """
    labels = list(answer_counts.keys())
    sizes = list(answer_counts.values())
    total = sum(sizes)
    percentages = [(s / total) * 100 for s in sizes]
    
    fig, ax = plt.subplots(figsize=(8, 6))
    wedges, _ = ax.pie(sizes, startangle=140)
    
    ax.set_title(question_title, pad=30)
    ax.axis('equal')  # keep circle shape
    
    for i, w in enumerate(wedges):
        angle = (w.theta2 + w.theta1) / 2.0
        x = np.cos(np.deg2rad(angle))
        y = np.sin(np.deg2rad(angle))
        
        # line from slice to external label
        line_x = 1.05 * x
        line_y = 1.05 * y
        end_x = 1.15 * x
        end_y = 1.15 * y
        label_x = 1.25 * x
        label_y = 1.25 * y
        
        label_text = f"{labels[i]} ({percentages[i]:.1f}%)"
        
        ax.plot([line_x, end_x], [line_y, end_y], color='black', lw=1)
        
        align = 'left' if x >= 0 else 'right'
        ax.text(label_x, label_y, label_text, ha=align, va='center')
    
    plt.tight_layout()
    plt.savefig(output_filename)
    plt.close()

# -------------------------------------------------------------------------
# 6) MAIN
# -------------------------------------------------------------------------
def main():
    # A) OBTAIN REFRESH TOKEN VIA PIN FLOW (if you don't already have one)
    print("==== Imgur PIN Flow ====")
    auth_url = get_pin_authorization_url(IMGUR_CLIENT_ID)
    print("1) Open this URL in your browser:")
    print(auth_url)
    print("\n2) Grant access, and Imgur will give you a PIN code.")
    pin_code = input("3) Enter the PIN code here: ").strip()
    
    try:
        access_token, refresh_token = exchange_pin_for_tokens(
            IMGUR_CLIENT_ID, IMGUR_CLIENT_SECRET, pin_code
        )
    except Exception as e:
        print("Error exchanging PIN for tokens:", e)
        return
    
    # B) Prompt for the Google Form link
    form_link = input("\nEnter the Google Form link: ").strip()
    try:
        form_id = extract_form_id(form_link)
    except ValueError as ve:
        print("Error extracting form ID:", ve)
        return
    
    # C) Retrieve form data, question map, and responses
    form_data = get_form_data(form_id)
    form_title = form_data.get('info', {}).get('title', 'Untitled Form')
    question_map = get_question_map(form_data)
    responses = get_form_responses(form_id)
    counts = count_responses_per_question(question_map, responses)
    
    # D) Create a private album in your account
    album_name = f"{form_title} Responses"
    try:
        # We have an access token from the pin exchange
        album_id = create_imgur_album_oauth(album_name, access_token)
        print(f"Created album '{album_name}' with ID '{album_id}' on Imgur")
    except Exception as e:
        print("Error creating album:", e)
        return
    
    # E) Generate & upload charts
    print("Processing and uploading responses...")

    question_counter = 1
    uploaded_links = []
    for question_title, answer_counts in counts.items():
        if not answer_counts:
            continue
        image_filename = os.path.join(OUTPUT_DIR, f"question{question_counter}.png")
        generate_pie_chart(question_title, answer_counts, image_filename)
        
        try:
            link = upload_image_to_imgur_oauth(image_filename, question_title, album_id, access_token)
            uploaded_links.append(link)
        except Exception as e:
            print("Error uploading image:", e)
        
        if os.path.exists(image_filename):
            os.remove(image_filename)
        
        question_counter += 1
    
    album_link = f"https://imgur.com/a/{album_id}"
    print("\nDone! Imgur Album Link:", album_link)
    
    # Optional: You can delete the album at the end:
    # delete_imgur_album(album_id, access_token)

if __name__ == '__main__':
    main()
