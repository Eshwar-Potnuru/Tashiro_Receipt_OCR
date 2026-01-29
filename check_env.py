import os
from dotenv import load_dotenv

load_dotenv()

openai_key = os.getenv('OPENAI_API_KEY')
google_json = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON')
google_creds = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')

print('Environment Variables:')
print(f'  OPENAI_API_KEY: {openai_key[:20] if openai_key else "NOT FOUND"}...')
print(f'  GOOGLE_APPLICATION_CREDENTIALS: {google_creds if google_creds else "NOT SET"}')
print(f'  GOOGLE_APPLICATION_CREDENTIALS_JSON: {"SET" if google_json else "NOT SET"}')
