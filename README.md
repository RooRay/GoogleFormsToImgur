# Google Forms to Imgur
Retrieves Google Forms responses via the Google Forms API before making them into a pie chart and uploading them to a private Imgur album via the OAuth2 API

Written by ChatGPT with some light refactoring and touchups done by me. This is purely a tool I made to use in daily life and is not a good demonstration of my coding skills.

## Usage

Requires a Google Forms API Service Account and Imgur OAuth2 app both of which are detailed below.

Steps:
1. Connects to the Imgur API and then asks you to complete an OAuth2 flow so it can obtain a PIN (this is needed elsewhere)
2. Asks for a Google Form URL where it will then filter the ID and load the responses from
3. Creates a hidden album on Imgur to upload the later generated pie charts to
4. Uses matplotlib to generate pie charts and saves them to the local filesystem before uploading them to the Imgur private album previously generated
5. Returns the URL to the album for the user to share and read

## Accounts Setup

### Imgur Setup

1. Go to https://api.imgur.com/oauth2/addclient
2. Create an app with `Authorization Type` set to `OAuth 2 authorization without a callback URL`
3. Fill out the rest of the fields as you like and submit
4. Populate the `.env` file with the variables shown on screen

### Google Service Account Setup

1. Enable the Google Forms API at https://console.cloud.google.com/marketplace/product/google/forms.googleapis.com
2. Go to the `Credentials` page, click `Create Credentials` and create a Service Account
3. Give your Service Account a reasonable email address and the appropriate permissions to access the Google Forms API (pls use principle of least privilege here)
4. Create your Service Account and go to the `Keys` section, create a JSON key and download it
5. Populate the `.env` file with the path to where your JSON key is stored on your computer
6. Add the email address for your Service Account to any forms you want to load
