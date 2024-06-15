# views.py

import os
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import List, Dict
import requests
from linkedin_api import Linkedin
from openai import OpenAI
import browser_cookie3
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from requests.cookies import RequestsCookieJar, create_cookie
from linkedin_api.cookie_repository import CookieRepository

# Load environment variables
openai_api_key = os.getenv("OPENAI_API_KEY")
# Extract cookies from exported JSON file
def get_linkedin_api():
    try:
        cookies_path = os.path.join(os.path.dirname(__file__), 'cookies.json')
        with open(cookies_path) as f:
            cookies = json.load(f)

        cookie_jar = RequestsCookieJar()

        for cookie_data in cookies:
            cookie = create_cookie(
                domain=cookie_data["domain"],
                name=cookie_data["name"],
                value=cookie_data["value"],
                path=cookie_data["path"],
                secure=cookie_data["secure"],
                expires=cookie_data.get("expirationDate", None),
                rest={
                    "HttpOnly": cookie_data.get("httpOnly", False),
                    "SameSite": cookie_data.get("sameSite", "unspecified"),
                    "HostOnly": cookie_data.get("hostOnly", False),
                }
            )
            cookie_jar.set_cookie(cookie)

        new_repo = CookieRepository()
        new_repo.save(cookie_jar, 'email_or_username')

        return Linkedin('', '', cookies=cookie_jar)
    except Exception as e:
        logging.error(f"Error getting LinkedIn API: {e}")
        return None

# Authenticate and fetch profile information using cookies
linkedin_api = get_linkedin_api()

logging.basicConfig(level=logging.DEBUG)

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

# def find_urls(query: str, pages: int, limit: int) -> List[str]:
#     # Mock implementation for URLs
#     return [
#         "https://www.linkedin.com/in/john-doe/",
#         "https://www.linkedin.com/in/jane-doe/"
#     ]

def get_linkedin_id_from_search_urls(urls: List[str]) -> str:
    for url in urls:
        if "linkedin.com/in/" in url:
            return url.split("linkedin.com/in/")[1].split('/')[0]
        
def fetch_profile_info(participant, company):
    search_query = f"{participant} {company} LinkedIn"
    urls_found = find_urls(search_query, pages=1, limit=5)
    profile_id = get_linkedin_id_from_search_urls(urls_found)
    print(f"profile_id: {profile_id}")

    if profile_id:
        try:
            print(f"linkedin_api: {linkedin_api}")
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
        client = OpenAI()
        prompt = f"Please generate a profile summary using the following data. Include sections for Basics, Topics, and No-gos. \n{profile}"
        completion = client.chat.completions.create(
            model="gpt-3.5-turbo-16k",  # Adjust the model as needed
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ]
        )
        print(f"completion: {completion}")
        content = completion.choices[0].message
        return {"chatgpt_content": content}
    except Exception as e:
        logging.error(f"Error generating ChatGPT info: {e}")
        return {"error": "Failed to generate ChatGPT info"}



@api_view(['POST'])
def get_profile(request):
    data = request.data
    company = data.get('company')
    participants = data.get('participants')
    purpose = data.get('purpose')
    if company is None or participants is None or purpose is None:
        return Response({"error": "Missing args"}, status=status.HTTP_400_BAD_REQUEST)

    # get profile for all participants
    with ThreadPoolExecutor() as executor:
        results = list(executor.map(partial(fetch_profile_info, company=company), participants))

    return Response(results, status=status.HTTP_200_OK)


@api_view(['GET'])  # Specify the HTTP methods allowed for this view
def hello_world(request):
    return Response({"message": "Hello, world!"})