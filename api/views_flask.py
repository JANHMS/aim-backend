import os
from functools import partial
from typing import List, Dict

import requests
from linkedin_api import Linkedin
from dotenv import load_dotenv
import logging
from flask import Flask, jsonify, request
from flask_cors import CORS, cross_origin
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
CORS(app)  # enable CORS for all routes and all origins

logging.basicConfig(level=logging.DEBUG)

load_dotenv()
email = os.getenv("LINKEDIN_EMAIL")
password = os.getenv("LINKEDIN_PASSWORD")
openai_api_key = os.getenv("OPENAI_API_KEY")
# Authenticate and fetch profile information
linkedin_api = Linkedin(email, password)

def extract_urls(data):
    urls = []
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, str) and key == "url" and "google." not in value:
                urls.append(value)
            else:
                urls.extend(extract_urls(value))
    elif isinstance(data, list):
        for item in data:
            urls.extend(extract_urls(item))
    return urls


def find_urls(query: str, pages: int, limit: int) -> List[str]:
    payload = {
        'source': 'google_search',
        'query': query,
        'domain': 'de',
        'geo_location': 'Germany',
        'locale': 'en-us',
        'parse': True,
        'start_page': 1,
        'pages': pages,
        'limit': limit,
    }

    # Get response.
    response = requests.request(
        'POST',
        'https://realtime.oxylabs.io/v1/queries',
        auth=('artabalt', 'blAblabla001789'),
        json=payload,
    )

    if response.status_code != 200:
        print("Error - ", response.json())
        exit(-1)

    import json
    json_payload = response.json()
    urls = extract_urls(json_payload)
    return urls


def get_linkedin_id_from_search_urls(urls: List[str]) -> str:
    for url in urls:
        if "linkedin.com/in/" in url:
            return url.split("linkedin.com/in/")[1].split('/')[0]


def fetch_profile_info(participant, company):
    search_query = f"{participant} {company} LinkedIn"
    urls_found = find_urls(search_query, pages=1, limit=5)
    profile_id = get_linkedin_id_from_search_urls(urls_found)

    if profile_id:
        try:
            profile = linkedin_api.get_profile(profile_id)
            contact_info = linkedin_api.get_profile_contact_info(profile_id)
            # Generate info using ChatGPT
            chatgpt_info = generate_chatgpt_info(profile)
            return {"participant": participant, "profile_id": profile_id, "profile": profile,
                    "contact_info": contact_info, "chatgpt_info": chatgpt_info}
        except Exception as e:
            logging.error(f"Error fetching profile information for {participant}: {e}")
            return {"participant": participant, "error": "Failed to fetch profile information"}
    else:
        return {"participant": participant, "error": f"No LinkedIn profile found for {participant}"}


def generate_chatgpt_info(profile: Dict) -> Dict:
    try:
        prompt = f"Please generate a profile summary using the following data. Include sections for Basics, Topics, and No-gos. \n{profile}"
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {openai_api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o",
                "messages": [{"role": "system", "content": "You are a helpful assistant."},
                             {"role": "user", "content": prompt}],
                "temperature": 0.0
            }
        )
        response.raise_for_status()
        chatgpt_response = response.json()
        content = chatgpt_response['choices'][0]['message']['content']
        return {"chatgpt_content": content}
    except Exception as e:
        logging.error(f"Error generating ChatGPT info: {e}")
        return {"error": "Failed to generate ChatGPT info"}


@app.route('/get_profile', methods=['POST'])
@cross_origin()
def get_profile():
    data = request.get_json()
    company = data.get('company')
    participants = data.get('participants')
    participants = participants.split(",")
    purpose = data.get('purpose')
    if company is None:
        return jsonify({"error": "Missing args"}), 400

    # get profile for all participants
    with ThreadPoolExecutor() as executor:
        results = list(executor.map(partial(fetch_profile_info, company=company), participants))

    return jsonify({"results": results})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)