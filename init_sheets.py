"""
Script de inicialização e migração para o Google Sheets.
Cria a planilha, as abas e os cabeçalhos.
Opcionalmente, migra os dados do database.db (SQLite) para o Google Sheets.
"""

import os
import sys
import sqlite3
import logging
import json
import base64

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Escopos necessários
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# Estrutura das tabelas (Nome da Aba: Lista de Colunas)
# Os nomes das abas devem bater com o mapeamento em database_sheets.py
# CORREÇÃO BUG 1 e BUG 2: Schemas atualizados para corresponder às queries do app.py
TABLE_SCHEMAS = {
    'Perfis': ['id', 'nome'],
    'Usuarios': ['id', 'username', 'senha', 'perfil_id', 'nome_completo', 'email', 'ativo', 'data_criacao'],
    'Funcionarios': [
        'id', 'cpf', 'nome', 'data_nascimento', 'estado_civil', 'telefone', 'email', 
        'sexo', 'raca', 'escolaridade', 'banco', 'agencia', 'conta', 'modalidade_conta',
        'endereco_rua', 'endereco_num', 'endereco_bairro', 'endereco_cidade', 
        'endereco_estado', 'endereco_cep', 'optou_convenio', 'totalpass', 'vt', 
        'salario', 'cargo', 'nivel', 'area', 'filial', 'gestor', 'login_extranet', 
        'data_admissao', 'status', 'data_desligamento', 'tipo_desligamento', 'motivo_desligamento'
    ],
    'Ferias': ['id', 'funcionario_id', 'periodo_aquisitivo_inicio', 'periodo_aquisitivo_fim', 'data_inicio', 'data_fim', 'abono_pecuniario', 'status_ferias'],
    'Lembretes': ['id', 'funcionario_id', 'titulo', 'descricao', 'data_alerta', 'status'],
    'Historico_Movimentacoes': ['id', 'funcionario_id', 'usuario_id', 'tipo_movimentacao', 'valor_antigo', 'valor_novo', 'observacao', 'data_evento'],
    'Ocorrencias': ['id', 'funcionario_id', 'tipo', 'data_inicio', 'data_fim', 'quantidade_dias', 'cid', 'observacao', 'data_registro']
}


def get_credentials() -> Credentials:
    """Carrega as credenciais da Service Account do Google."""
    creds_b64 = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
    if creds_b64:
        try:
            creds_json = base64.b64decode(creds_b64).decode('utf-8')
            creds_dict = json.loads(creds_json)
            return Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        except Exception as e:
            logger.error(f"Erro ao decodificar GOOGLE_SERVICE_ACCOUNT_JSON: {e}")
            sys.exit(1)
    
    creds_file = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
    if creds_file and os.path.exists(creds_file):
        return Credentials.from_service_account_file(creds_file, scopes=SCOPES)
    
    logger.error("Credenciais do Google não configuradas. Defina GOOGLE_SERVICE_ACCOUNT_JSON ou GOOGLE_APPLICATION_CREDENTIALS.")
    sys.exit(1)


def create_or_get_spreadsheet(client, spreadsheet_id=None, title="Essencia_RH_Database"):
    """Cria uma nova planilha ou abre uma existente pelo ID."""
    if spreadsheet_id:
        try:
            logger.info(f"Abrindo planilha existente com ID: {spreadsheet_id}")
            return client.open_by_key(spreadsheet_id)
        except gspread.exceptions.SpreadsheetNotFound:
            logger.warning(f"Planilha com ID {spreadsheet_id} não encontrada. Criando uma nova...")
            
    logger.info(f"Criando nova planilha: {title}")
    return client.create(title)


def setup_worksheets(spreadsheet):
    """Cria as abas e os cabeçalhos na planilha."""
    logger.info("Configurando abas e cabeçalhos...")
    
    # Remove a aba padrão "Sheet1" se existir e não estiver na nossa lista
    try:
        default_sheet = spreadsheet.worksheet("Sheet1")
        if "Sheet1" not in TABLE_SCHEMAS:
            spreadsheet.del_worksheet(default_sheet)
            logger.info("Aba padrão 'Sheet1' removida.")
    except gspread.exceptions.WorksheetNotFound:
        pass

    for sheet_name, columns in TABLE_SCHEMAS.items():
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
            logger.info(f"Aba '{sheet_name}' já existe. Verificando cabeçalhos...")
            
            # Verifica se os cabeçalhos estão corretos
            current_headers = worksheet.row_values(1)
            if current_headers != columns:
                logger.warning(f"Cabeçalhos da aba '{sheet_name}' não correspondem ao esperado. Atualizando...")
                worksheet.clear()
                worksheet.append_row(columns)
            else:
                logger.info(f"Cabeçalhos da aba '{sheet_name}' estão corretos.")
                
        except gspread.exceptions.WorksheetNotFound:
            logger.info(f"Criando aba '{sheet_name}'...")
            worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=len(columns))
            worksheet.append_row(columns)
            
    logger.info("Configuração das abas concluída.")


def migrate_sqlite_to_sheets(spreadsheet, db_path="database.db"):
    """Migra os dados do SQLite para o Google Sheets."""
    if not os.path.exists(db_path):
        logger.warning(f"Arquivo de banco de dados SQLite '{db_path}' não encontrado. Pulando migração de dados.")
        return

    logger.info(f"Iniciando migração de dados do SQLite ({db_path}) para o Google Sheets...")
    
    # Mapeamento de tabelas SQLite para nomes de abas
    sqlite_to_sheets_map = {
        'perfis': 'Perfis',
        'usuarios': 'Usuarios',
        'funcionarios': 'Funcionarios',
        'ferias': 'Ferias',
        'lembretes': 'Lembretes',
        'historico_movimentacoes': 'Historico_Movimentacoes',
        'ocorrencias': 'Ocorrencias'
    }

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    for sqlite_table, sheet_name in sqlite_to_sheets_map.items():
        try:
            # Verifica se a tabela existe no SQLite
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{sqlite_table}';")
            if not cursor.fetchone():
                logger.info(f"Tabela '{sqlite_table}' não existe no SQLite. Pulando...")
                continue

            cursor.execute(f"SELECT * FROM {sqlite_table}")
            rows = cursor.fetchall()
            
            if not rows:
                logger.info(f"Tabela '{sqlite_table}' está vazia. Pulando...")
                continue

            columns = [description[0] for description in cursor.description]
            worksheet = spreadsheet.worksheet(sheet_name)
            
            # Limpa a aba antes de inserir os dados (mantém o cabeçalho)
            worksheet.clear()
            worksheet.append_row(columns)
            
            # Prepara os dados para inserção
            data_to_insert = []
            for row in rows:
                # Converte todos os valores para string, tratando None como string vazia
                row_data = [str(val) if val is not None else "" for val in row]
                data_to_insert.append(row_data)
            
            # Insere em lotes (batch) para evitar limites de API
            logger.info(f"Migrando {len(data_to_insert)} registros da tabela '{sqlite_table}' para a aba '{sheet_name}'...")
            
            # gspread tem um limite de células por requisição, então dividimos em lotes de 500 linhas
            batch_size = 500
            for i in range(0, len(data_to_insert), batch_size):
                batch = data_to_insert[i:i + batch_size]
                worksheet.append_rows(batch)
                
            logger.info(f"Migração da tabela '{sqlite_table}' concluída.")
            
        except Exception as e:
            logger.error(f"Erro ao migrar a tabela '{sqlite_table}': {e}")

    conn.close()
    logger.info("Migração de dados concluída.")


def share_spreadsheet(spreadsheet, service_account_email):
    """Compartilha a planilha com a própria Service Account (se necessário) e configura permissões."""
    # A Service Account já tem acesso por ser a criadora, mas podemos compartilhar com um e-mail específico se desejado
    admin_email = os.getenv('ADMIN_EMAIL_TO_SHARE')
    if admin_email:
        try:
            spreadsheet.share(admin_email, perm_type='user', role='writer')
            logger.info(f"Planilha compartilhada com {admin_email} como Editor.")
        except HttpError as e:
            logger.warning(f"Não foi possível compartilhar a planilha com {admin_email}: {e}")


def main():
    logger.info("=== Script de Inicialização do Essência RH (Google Sheets) ===")
    
    creds = get_credentials()
    # CORREÇÃO BUG 4: Substituir gspread.authorize() por gspread.Client(auth=creds)
    client = gspread.Client(auth=creds)
    
    # Pega o email da service account para compartilhamento
    service_account_email = creds.service_account_email
    
    spreadsheet_id = os.getenv('GOOGLE_SHEETS_ID')
    spreadsheet_title = os.getenv('SPREADSHEET_TITLE', 'Essencia_RH_Database')
    
    spreadsheet = create_or_get_spreadsheet(client, spreadsheet_id, spreadsheet_title)
    
    setup_worksheets(spreadsheet)
    share_spreadsheet(spreadsheet, service_account_email)
    
    # Pergunta se deseja migrar dados do SQLite
    migrate_data = input("Deseja migrar os dados do database.db (SQLite) para a planilha? (s/n): ").strip().lower()
    if migrate_data == 's':
        migrate_sqlite_to_sheets(spreadsheet)
        
    logger.info("=== Configuração Concluída ===")
    logger.info(f"ID da Planilha (GOOGLE_SHEETS_ID): {spreadsheet.id}")
    logger.info(f"URL da Planilha: {spreadsheet.url}")
    logger.info("Adicione o ID acima ao seu arquivo .env na variável GOOGLE_SHEETS_ID.")


if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv()
    main()