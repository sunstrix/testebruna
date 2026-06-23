import os
import json
import base64
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

# Carrega o .env
load_dotenv()

print("=== Teste 1: Lendo do .env ===")
creds_b64 = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
print(f"Tamanho do base64 no .env: {len(creds_b64) if creds_b64 else 'VAZIO'} caracteres")

if creds_b64:
    print(f"Primeiros 50 chars: {creds_b64[:50]}")
    
    try:
        # Decodifica base64
        creds_json = base64.b64decode(creds_b64).decode('utf-8')
        print(f"\n✓ Base64 decodificado com sucesso!")
        print(f"Tamanho do JSON: {len(creds_json)} caracteres")
        print(f"Primeiros 100 chars: {creds_json[:100]}")
        
        # Parse como JSON
        creds_dict = json.loads(creds_json)
        print(f"\n✓ JSON parseado com sucesso!")
        print(f"Tipo: {creds_dict.get('type')}")
        print(f"Email: {creds_dict.get('client_email')}")
        
        # Verifica private_key
        private_key = creds_dict.get('private_key', '')
        print(f"\nPrivate key presente: {bool(private_key)}")
        print(f"Private key tamanho: {len(private_key)} caracteres")
        print(f"Private key início: {private_key[:50] if private_key else 'VAZIO'}")
        
        # Tenta criar credenciais
        print("\nTentando criar credenciais...")
        creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
        print("✓ Credenciais criadas com sucesso!")
        
    except Exception as e:
        print(f"\n✗ Erro: {e}")
        print(f"Tipo do erro: {type(e).__name__}")
        
        # Mostra mais detalhes
        import traceback
        traceback.print_exc()
else:
    print("✗ GOOGLE_SERVICE_ACCOUNT_JSON não encontrado no .env")
