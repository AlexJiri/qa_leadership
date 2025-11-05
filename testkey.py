import os
import requests

# You can put the key directly here for testing:
api_key = os.getenv("OPENAI_API_KEY") or "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"  # replace if you want

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
