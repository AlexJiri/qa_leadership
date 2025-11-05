import os
import requests

# You can put the key directly here for testing:
# IMPORTANT: Never commit API keys to Git! Use environment variables or .env file
api_key = os.getenv("OPENAI_API_KEY") or "YOUR_API_KEY_HERE"  # Replace with your key for local testing only

headers = {
    "Authorization": f"Bearer {api_key}"
}

response = requests.get("https://api.openai.com/v1/models", headers=headers)

if response.status_code == 200:
    print("Cheie valida. Modele disponibile:")
    models = response.json().get("data", [])
    for model in models[:10]:
        print("-", model.get("id"))
else:
    print("Eroare la autentificare:")
    print("Status:", response.status_code)
    print(response.json())
