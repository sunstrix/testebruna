"""
Módulo de integrações externas para o Essência RH.
Todas as integrações são opcionais e controladas por variáveis de ambiente.
Se uma integração não estiver configurada ou falhar, o sistema continua funcionando normalmente.
"""

import os
import re
import io
import logging
import smtplib
import requests
import json
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Optional, Any

# Configuração de logging
logger = logging.getLogger(__name__)

# ==========================================
# 1. VIA CEP (Autocompletar Endereço)
# ==========================================
def consultar_viacep(cep: str) -> Optional[Dict[str, str]]:
    """
    Consulta um CEP na API ViaCEP (gratuita, sem chave).
    Retorna um dicionário formatado ou None em caso de erro/CEP não encontrado.
    """
    if not cep:
        return None
        
    # Remove caracteres não numéricos
    cep_limpo = re.sub(r'\D', '', cep)
    
    if len(cep_limpo) != 8:
        logger.warning(f"CEP inválido fornecido para o ViaCEP: {cep}")
        return None
        
    try:
        url = f"https://viacep.com.br/ws/{cep_limpo}/json/"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        # A API do ViaCEP retorna {"erro": true} quando o CEP não é encontrado
        if data.get("erro"):
            logger.info(f"CEP não encontrado no ViaCEP: {cep_limpo}")
            return None
            
        return {
            "rua": data.get("logradouro", ""),
            "bairro": data.get("bairro", ""),
            "cidade": data.get("localidade", ""),
            "estado": data.get("uf", "")
        }
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro de rede ao consultar ViaCEP para o CEP {cep_limpo}: {e}")
        return None
    except Exception as e:
        logger.error(f"Erro inesperado ao consultar ViaCEP: {e}")
        return None


# ==========================================
# 2. BRASIL API (Feriados Nacionais)
# ==========================================
def consultar_feriados_brasilapi(ano: int) -> List[Dict[str, str]]:
    """
    Consulta os feriados nacionais de um determinado ano na BrasilAPI (gratuita).
    Retorna uma lista de dicionários com 'date' e 'name'.
    """
    try:
        url = f"https://brasilapi.com.br/api/feriados/v1/{ano}"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        # Formata para o padrão que o app.py espera
        feriados = []
        for feriado in data:
            feriados.append({
                "date": feriado.get("date"),
                "name": feriado.get("name")
            })
        return feriados
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro de rede ao consultar BrasilAPI para o ano {ano}: {e}")
        return []
    except Exception as e:
        logger.error(f"Erro inesperado ao consultar BrasilAPI: {e}")
        return []


# ==========================================
# 3. TELEGRAM BOT (Alertas do RH)
# ==========================================
def enviar_alerta_telegram(mensagem: str) -> bool:
    """
    Envia uma mensagem para um grupo/chat do Telegram configurado.
    Controlado pelas variáveis de ambiente TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID.
    Retorna True se enviado com sucesso, False caso contrário.
    """
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    
    if not token or not chat_id:
        logger.debug("Variáveis TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID não configuradas. Alerta do Telegram ignorado.")
        return False
        
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": f"🔔 *Essência RH - Alerta*\n\n{mensagem}",
            "parse_mode": "Markdown"
        }
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("Alerta enviado com sucesso para o Telegram.")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao enviar mensagem para o Telegram: {e}")
        return False
    except Exception as e:
        logger.error(f"Erro inesperado ao enviar mensagem para o Telegram: {e}")
        return False


# ==========================================
# 4. GMAIL SMTP (E-mails Automáticos)
# ==========================================
def enviar_email(assunto: str, corpo: str, destinatarios: List[str]) -> bool:
    """
    Envia um e-mail via Gmail SMTP.
    Controlado pelas variáveis de ambiente EMAIL_USER e EMAIL_PASS (senha de app).
    Retorna True se enviado com sucesso, False caso contrário.
    """
    user = os.getenv('EMAIL_USER')
    password = os.getenv('EMAIL_PASS')
    
    if not user or not password:
        logger.debug("Variáveis EMAIL_USER ou EMAIL_PASS não configuradas. Envio de e-mail ignorado.")
        return False
        
    if not destinatarios:
        logger.warning("Nenhum destinatário fornecido para envio de e-mail.")
        return False
        
    try:
        msg = MIMEMultipart()
        msg['From'] = user
        msg['To'] = ", ".join(destinatarios)
        msg['Subject'] = f"[Essência RH] {assunto}"
        
        msg.attach(MIMEText(corpo, 'plain', 'utf-8'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(user, password)
        text = msg.as_string()
        server.sendmail(user, destinatarios, text)
        server.quit()
        
        logger.info(f"E-mail enviado com sucesso para: {', '.join(destinatarios)}")
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error("Erro de autenticação no Gmail SMTP. Verifique se EMAIL_USER e EMAIL_PASS (senha de app) estão corretos.")
        return False
    except Exception as e:
        logger.error(f"Erro inesperado ao enviar e-mail: {e}")
        return False


# ==========================================
# 5. GOOGLE DRIVE (Backup da Planilha)
# ==========================================
def backup_planilha_drive() -> bool:
    """
    Exporta a planilha atual do Google Sheets para um arquivo XLSX 
    e salva o backup no Google Drive.
    Usa a mesma Service Account configurada para o Sheets.
    """
    try:
        # Importa localmente para evitar dependência circular ou erro se o Sheets não estiver configurado
        from database_sheets import get_credentials, get_spreadsheet, SPREADSHEET_ID
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseUpload
        
        if not SPREADSHEET_ID:
            logger.warning("GOOGLE_SHEETS_ID não configurado. Backup do Drive ignorado.")
            return False
            
        creds = get_credentials()
        drive_service = build('drive', 'v3', credentials=creds)
        
        # Exporta a planilha inteira como XLSX
        request = drive_service.files().export_media(
            fileId=SPREADSHEET_ID,
            mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
        fh = io.BytesIO()
        # Precisamos importar o downloader
        from googleapiclient.http import MediaIoBaseDownload
        downloader = MediaIoBaseDownload(fh, request)
        
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            
        fh.seek(0)
        
        # Faz o upload do arquivo para o Drive
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_metadata = {
            'name': f'Backup_EssenciaRH_{timestamp}.xlsx',
            'mimeType': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        }
        
        media = MediaIoBaseUpload(fh, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        logger.info(f"Backup realizado com sucesso no Google Drive. File ID: {file.get('id')}")
        return True
        
    except ImportError as e:
        logger.error(f"Dependência do Google Drive não instalada (google-api-python-client). Erro: {e}")
        return False
    except Exception as e:
        logger.error(f"Erro ao fazer backup no Google Drive: {e}")
        return False


# ==========================================
# FUNÇÃO CENTRAL DE ALERTAS
# ==========================================
def disparar_alerta_geral(assunto: str, mensagem: str, destinatarios_email: Optional[List[str]] = None):
    """
    Dispara um alerta por todos os canais configurados (Telegram e/ou E-mail).
    Esta função deve ser chamada pelo app.py sempre que um lembrete automático for gerado.
    """
    # Envia para o Telegram
    enviar_alerta_telegram(f"*{assunto}*\n{mensagem}")
    
    # Envia por E-mail, se houver destinatários
    if destinatarios_email:
        corpo_email = f"Olá,\n\nO sistema Essência RH gerou o seguinte alerta:\n\nAssunto: {assunto}\n\n{mensagem}\n\nAtenciosamente,\nSistema Essência RH - CP Fani"
        enviar_email(assunto, corpo_email, destinatarios_email)