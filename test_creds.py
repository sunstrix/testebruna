import os
import json
from google.oauth2.service_account import Credentials

# Carrega o JSON diretamente (sem base64)
json_path = r"C:\Users\AlexPaulo\Desktop\testebruna\credentials\essencia-rh-cp-fani-dd8d28f5ede6.json"

print(f"Carregando: {json_path}")
print(f"Arquivo existe: {os.path.exists(json_path)}")

# Lê o conteúdo
with open(json_path, 'r', encoding='utf-8') as f:
    content = f.read()
    
print(f"\nTamanho do arquivo: {len(content)} caracteres")
print(f"Primeiros 100 chars: {content[:100]}")

# Tenta parsear como JSON
try:
    creds_dict = json.loads(content)
    print(f"\n✓ JSON válido!")
    print(f"Tipo: {creds_dict.get('type')}")
    print(f"Email: {creds_dict.get('client_email')}")
    
    # Verifica se tem private_key
    private_key = creds_dict.get('private_key', '')
    print(f"\nPrivate key presente: {bool(private_key)}")
    print(f"Private key tamanho: {len(private_key)} caracteres")
    print(f"Private key início: {private_key[:50] if private_key else 'VAZIO'}")
    
    # Tenta criar as credenciais
    print("\nTentando criar credenciais...")
    creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    print("✓ Credenciais criadas com sucesso!")
    
except json.JSONDecodeError as e:
    print(f"\n✗ Erro ao parsear JSON: {e}")
except Exception as e:
    print(f"\n✗ Erro ao criar credenciais: {e}")
    print(f"Tipo do erro: {type(e).__name__}")
