"""
Camada de acesso a dados via Google Sheets API.
Substitui get_db_connection() do SQLite por uma implementação compatível
que lê/escreve em uma planilha Google Sheets usando gspread.
"""

import os
import re
import json
import base64
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union
from collections import OrderedDict
from functools import wraps

import gspread
from google.oauth2.service_account import Credentials
from cachetools import TTLCache

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cache com TTL de 120 segundos (aumentado de 30s para reduzir requisições)
_cache = TTLCache(maxsize=100, ttl=120)

# Escopos necessários para Google Sheets API
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# ID da planilha (deve ser configurado via variável de ambiente)
SPREADSHEET_ID = os.getenv('GOOGLE_SHEETS_ID')

# Mapeamento de tabelas SQLite para nomes de abas no Google Sheets
TABLE_NAMES = {
    'perfis': 'Perfis',
    'usuarios': 'Usuarios',
    'funcionarios': 'Funcionarios',
    'ferias': 'Ferias',
    'lembretes': 'Lembretes',
    'historico_movimentacoes': 'Historico_Movimentacoes',
    'ocorrencias': 'Ocorrencias'
}


# CORREÇÃO BUG 7: Adicionado @wraps para preservar __name__ e __doc__
def retry_on_quota_error(max_retries=3, initial_delay=2):
    """
    Decorator para retry com backoff exponencial quando der erro 429 (quota exceeded).
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except gspread.exceptions.APIError as e:
                    error_str = str(e)
                    if '429' in error_str or 'RESOURCE_EXHAUSTED' in error_str or 'RATE_LIMIT_EXCEEDED' in error_str:
                        if attempt < max_retries - 1:
                            logger.warning(f"Quota exceeded. Retrying in {delay} seconds... (attempt {attempt + 1}/{max_retries})")
                            time.sleep(delay)
                            delay *= 2  # Backoff exponencial
                        else:
                            logger.error(f"Quota exceeded after {max_retries} retries")
                            raise
                    else:
                        raise
        return wrapper
    return decorator


def get_credentials() -> Credentials:
    """
    Carrega as credenciais da Service Account do Google.
    Tenta primeiro via variável de ambiente (base64), depois via arquivo.
    """
    # Tenta carregar de variável de ambiente (base64 encoded JSON)
    creds_b64 = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON')
    if creds_b64:
        try:
            creds_json = base64.b64decode(creds_b64).decode('utf-8')
            creds_dict = json.loads(creds_json)
            return Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        except Exception as e:
            logger.error(f"Erro ao decodificar GOOGLE_SERVICE_ACCOUNT_JSON: {e}")
            raise
    
    # Tenta carregar de arquivo (desenvolvimento local)
    creds_file = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
    if creds_file and os.path.exists(creds_file):
        return Credentials.from_service_account_file(creds_file, scopes=SCOPES)
    
    raise ValueError(
        "Credenciais do Google não configuradas. "
        "Defina GOOGLE_SERVICE_ACCOUNT_JSON (base64) ou GOOGLE_APPLICATION_CREDENTIALS (caminho do arquivo)."
    )



# Cache da instância do spreadsheet — evita reconectar a cada request Flask
_spreadsheet_instance = None
_spreadsheet_instance_time = None
_SPREADSHEET_CACHE_TTL = 300  # segundos (5 minutos)


def get_spreadsheet():
    """
    Retorna a instância da planilha Google Sheets.
    Mantém a conexão em cache por até 5 minutos para evitar
    reconexões a cada request e estourar a quota de leitura da API.
    """
    global _spreadsheet_instance, _spreadsheet_instance_time

    if not SPREADSHEET_ID:
        raise ValueError("GOOGLE_SHEETS_ID não configurado nas variáveis de ambiente.")

    agora = time.time()
    if (
        _spreadsheet_instance is not None
        and _spreadsheet_instance_time is not None
        and (agora - _spreadsheet_instance_time) < _SPREADSHEET_CACHE_TTL
    ):
        return _spreadsheet_instance

    creds = get_credentials()
    client = gspread.Client(auth=creds)

    # Retry do open_by_key para absorver 429 logo na abertura
    delay = 2
    last_exc = None
    for attempt in range(4):
        try:
            spreadsheet = client.open_by_key(SPREADSHEET_ID)
            _spreadsheet_instance = spreadsheet
            _spreadsheet_instance_time = agora
            return _spreadsheet_instance
        except gspread.exceptions.APIError as e:
            error_str = str(e)
            if '429' in error_str or 'RESOURCE_EXHAUSTED' in error_str or 'RATE_LIMIT_EXCEEDED' in error_str:
                logger.warning(f"Quota exceeded ao abrir planilha. Aguardando {delay}s... (tentativa {attempt + 1}/4)")
                time.sleep(delay)
                delay *= 2
                last_exc = e
            else:
                raise
    raise last_exc


class SheetsRow:
    """
    Simula sqlite3.Row, permitindo acesso por nome de coluna e por índice.
    """
    def __init__(self, data: Dict[str, Any], columns: List[str]):
        self._data = data
        self._columns = columns
    
    def __getitem__(self, key):
        if isinstance(key, int):
            col_name = self._columns[key]
            return self._data.get(col_name)
        else:
            return self._data.get(key)
    
    def __contains__(self, key):
        return key in self._data
    
    def keys(self):
        return self._data.keys()
    
    def values(self):
        return self._data.values()
    
    def items(self):
        return self._data.items()
    
    def get(self, key, default=None):
        return self._data.get(key, default)


class SheetsCursor:
    """
    Simula sqlite3.Cursor, executando operações na planilha Google Sheets.
    """
    def __init__(self, connection: 'SheetsConnection'):
        self.connection = connection
        self.spreadsheet = connection.spreadsheet
        self._results: List[SheetsRow] = []
        self._rowcount = 0
        self._lastrowid = None
        self._description = None
    
    @property
    def rowcount(self):
        return self._rowcount
    
    @property
    def lastrowid(self):
        return self._lastrowid
    
    @property
    def description(self):
        return self._description
    
    @retry_on_quota_error(max_retries=3, initial_delay=2)
    def execute(self, sql: str, params: Tuple = ()) -> 'SheetsCursor':
        """
        Executa uma query SQL na planilha Google Sheets.
        """
        sql_clean = sql.strip()
        
        # Parse da query SQL
        query_type = self._parse_query_type(sql_clean)
        
        if query_type == 'SELECT':
            self._execute_select(sql_clean, params)
        elif query_type == 'INSERT':
            self._execute_insert(sql_clean, params)
        elif query_type == 'UPDATE':
            self._execute_update(sql_clean, params)
        elif query_type == 'DELETE':
            self._execute_delete(sql_clean, params)
        else:
            raise ValueError(f"Tipo de query não suportado: {query_type}")
        
        return self
    
    def _parse_query_type(self, sql: str) -> str:
        """Determina o tipo de operação SQL."""
        sql_upper = sql.upper().strip()
        if sql_upper.startswith('SELECT'):
            return 'SELECT'
        elif sql_upper.startswith('INSERT'):
            return 'INSERT'
        elif sql_upper.startswith('UPDATE'):
            return 'UPDATE'
        elif sql_upper.startswith('DELETE'):
            return 'DELETE'
        return 'UNKNOWN'
    
    def _get_worksheet(self, table_name: str):
        """
        Retorna a worksheet correspondente à tabela.
        Cacheia instâncias de worksheet para evitar fetch_sheet_metadata()
        a cada query — cada chamada a .worksheet() faz uma requisição HTTP.
        """
        sheet_name = TABLE_NAMES.get(table_name, table_name)
        ws_instance_key = f"ws_instance_{sheet_name}"

        if ws_instance_key in _cache:
            return _cache[ws_instance_key]

        delay = 2
        last_exc = None
        for attempt in range(4):
            try:
                # spreadsheet.worksheets() retorna lista local (sem req extra se metadados já carregados)
                for ws in self.spreadsheet.worksheets():
                    if ws.title == sheet_name:
                        _cache[ws_instance_key] = ws
                        return ws
                raise gspread.exceptions.WorksheetNotFound(sheet_name)
            except gspread.exceptions.WorksheetNotFound:
                raise ValueError(f"Worksheet '{sheet_name}' não encontrada na planilha.")
            except gspread.exceptions.APIError as e:
                error_str = str(e)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str or "RATE_LIMIT_EXCEEDED" in error_str:
                    logger.warning(f"Quota exceeded ao buscar worksheet. Aguardando {delay}s... (tentativa {attempt + 1}/4)")
                    time.sleep(delay)
                    delay *= 2
                    last_exc = e
                else:
                    raise
        if last_exc:
            raise last_exc
        raise ValueError(f"Worksheet '{sheet_name}' não encontrada na planilha.")
    
    # CORREÇÃO BUG 6: Usar get_all_values() para buscar cabeçalhos separadamente
    @retry_on_quota_error(max_retries=3, initial_delay=2)
    def _get_all_records(self, worksheet) -> Tuple[List[Dict], List[str]]:
        """
        Retorna todos os registros da worksheet com cache.
        Retorna (records, columns).
        Usa get_all_values() para garantir que os cabeçalhos sejam sempre retornados,
        mesmo quando a aba está vazia (apenas com cabeçalho).
        """
        cache_key = f"ws_{worksheet.title}"
        
        if cache_key in _cache:
            return _cache[cache_key]
        
        all_values = worksheet.get_all_values()
        if not all_values:
            _cache[cache_key] = ([], [])
            return [], []
        
        headers = all_values[0]
        records = []
        for row in all_values[1:]:
            # Preenche com string vazia se a linha for mais curta que o header
            padded = row + [''] * (len(headers) - len(row))
            record = {headers[i]: padded[i] for i in range(len(headers))}
            records.append(record)
        
        _cache[cache_key] = (records, headers)
        return records, headers
    
    def _execute_select(self, sql: str, params: Tuple):
        """Executa uma query SELECT."""
        # Extrai nome da tabela
        table_match = re.search(r'FROM\s+(\w+)', sql, re.IGNORECASE)
        if not table_match:
            raise ValueError("Não foi possível extrair o nome da tabela da query SELECT.")
        
        table_name = table_match.group(1)
        worksheet = self._get_worksheet(table_name)
        records, columns = self._get_all_records(worksheet)
        
        # Aplica filtros WHERE
        filtered_records = self._apply_where_clause(sql, params, records)
        
        # Aplica ORDER BY
        filtered_records = self._apply_order_by(sql, filtered_records)
        
        # Aplica LIMIT
        limit_match = re.search(r'LIMIT\s+(\d+)', sql, re.IGNORECASE)
        if limit_match:
            limit = int(limit_match.group(1))
            filtered_records = filtered_records[:limit]
        
        # Converte para SheetsRow
        self._results = [SheetsRow(record, columns) for record in filtered_records]
        self._rowcount = len(self._results)
        self._description = [(col, None, None, None, None, None, None) for col in columns] if columns else None
    
    def _execute_insert(self, sql: str, params: Tuple):
        """Executa uma query INSERT."""
        table_match = re.search(r'INTO\s+(\w+)', sql, re.IGNORECASE)
        columns_match = re.search(r'\(([^)]+)\)\s*VALUES', sql, re.IGNORECASE)
        
        if not table_match or not columns_match:
            raise ValueError("Query INSERT malformada.")
        
        table_name = table_match.group(1)
        columns_str = columns_match.group(1)
        columns = [col.strip() for col in columns_str.split(',')]
        
        worksheet = self._get_worksheet(table_name)
        
        # Cria dicionário com os valores
        values_dict = {col: params[i] if i < len(params) else None for i, col in enumerate(columns)}
        
        # Adiciona nova linha
        worksheet.append_row([values_dict.get(col, '') for col in columns])
        
        # CORREÇÃO BUG 8: Invalidar cache imediatamente após INSERT
        cache_key = f"ws_{worksheet.title}"
        if cache_key in _cache:
            del _cache[cache_key]
        
        # Obtém o ID da última linha inserida
        all_values = worksheet.get_all_values()
        self._lastrowid = len(all_values) - 1
        self._rowcount = 1
    
    @retry_on_quota_error(max_retries=3, initial_delay=2)
    def _execute_update(self, sql: str, params: Tuple):
        """Executa uma query UPDATE com batch update para otimizar."""
        table_match = re.search(r'UPDATE\s+(\w+)', sql, re.IGNORECASE)
        set_match = re.search(r'SET\s+(.+?)\s+WHERE', sql, re.IGNORECASE)
        
        if not table_match or not set_match:
            raise ValueError("Query UPDATE malformada.")
        
        table_name = table_match.group(1)
        set_clause = set_match.group(1)
        
        worksheet = self._get_worksheet(table_name)
        records, columns = self._get_all_records(worksheet)
        
        # Parse do SET clause
        set_parts = [part.strip() for part in set_clause.split(',')]
        updates = {}
        param_idx = 0
        
        for part in set_parts:
            col_val_match = re.match(r'(\w+)\s*=\s*\?', part)
            if col_val_match:
                col_name = col_val_match.group(1)
                updates[col_name] = params[param_idx]
                param_idx += 1
            else:
                col_val_match = re.match(r'(\w+)\s*=\s*[\'"]?([^\'"]+)[\'"]?', part)
                if col_val_match:
                    updates[col_val_match.group(1)] = col_val_match.group(2)
        
        # Aplica filtros WHERE
        filtered_records = self._apply_where_clause(sql, params[param_idx:], records)
        
        # Batch update: atualiza todas as linhas de uma vez
        if filtered_records:
            batch_updates = []
            for record in filtered_records:
                row_idx = records.index(record) + 2
                
                for col, value in updates.items():
                    col_idx = columns.index(col) + 1
                    # Converte índice da coluna para letra (A=1, B=2, ..., Z=26, AA=27, etc.)
                    col_letter = self._get_column_letter(col_idx)
                    cell_range = f"{col_letter}{row_idx}"
                    batch_updates.append({
                        'range': cell_range,
                        'values': [[value]]
                    })
            
            # Executa batch update (1 requisição em vez de N)
            if batch_updates:
                worksheet.batch_update(batch_updates)
        
        # CORREÇÃO BUG 8: Invalidar cache imediatamente após UPDATE
        cache_key = f"ws_{worksheet.title}"
        if cache_key in _cache:
            del _cache[cache_key]
        
        self._rowcount = len(filtered_records)
    
    def _get_column_letter(self, col_idx: int) -> str:
        """Converte índice numérico da coluna para letra (1=A, 2=B, ..., 27=AA)."""
        result = ""
        while col_idx > 0:
            col_idx, remainder = divmod(col_idx - 1, 26)
            result = chr(65 + remainder) + result
        return result
    
    @retry_on_quota_error(max_retries=3, initial_delay=2)
    def _execute_delete(self, sql: str, params: Tuple):
        """Executa uma query DELETE."""
        table_match = re.search(r'FROM\s+(\w+)', sql, re.IGNORECASE)
        if not table_match:
            raise ValueError("Query DELETE malformada.")
        
        table_name = table_match.group(1)
        worksheet = self._get_worksheet(table_name)
        records, columns = self._get_all_records(worksheet)
        
        # Aplica filtros WHERE
        filtered_records = self._apply_where_clause(sql, params, records)
        
        # Deleta as linhas (de trás para frente para não afetar índices)
        deleted_count = 0
        for record in reversed(filtered_records):
            row_idx = records.index(record) + 2
            worksheet.delete_rows(row_idx)
            deleted_count += 1
        
        # CORREÇÃO BUG 8: Invalidar cache imediatamente após DELETE
        cache_key = f"ws_{worksheet.title}"
        if cache_key in _cache:
            del _cache[cache_key]
        
        self._rowcount = deleted_count
    
    # CORREÇÃO BUG 3: Refatorado para usar nova assinatura com param_idx
    def _apply_where_clause(self, sql: str, params: Tuple, records: List[Dict]) -> List[Dict]:
        """Aplica a cláusula WHERE aos registros."""
        where_match = re.search(r'WHERE\s+(.+?)(?:\s+ORDER|\s+LIMIT|\s*$)', sql, re.IGNORECASE | re.DOTALL)
        if not where_match:
            return records
        
        where_clause = where_match.group(1).strip()
        
        filtered = []
        for record in records:
            # CORREÇÃO BUG 3: _evaluate_where agora retorna (bool, next_param_idx)
            result, _ = self._evaluate_where(where_clause, record, params, 0)
            if result:
                filtered.append(record)
        
        return filtered
    
    # CORREÇÃO BUG 3: Retorna tupla (bool_resultado, next_param_idx)
    def _evaluate_where(self, where_clause: str, record: Dict, params: Tuple, param_idx: int) -> Tuple[bool, int]:
        """
        Avalia se um registro atende à cláusula WHERE.
        Retorna (bool_resultado, next_param_idx).
        """
        where_clause = re.sub(r'\s+', ' ', where_clause).strip()
        
        if ' AND ' in where_clause.upper():
            parts = re.split(r'\s+AND\s+', where_clause, flags=re.IGNORECASE)
            result = True
            for part in parts:
                cond_result, param_idx = self._evaluate_condition(part.strip(), record, params, param_idx)
                result = result and cond_result
            return result, param_idx
        
        if ' OR ' in where_clause.upper():
            parts = re.split(r'\s+OR\s+', where_clause, flags=re.IGNORECASE)
            result = False
            for part in parts:
                cond_result, param_idx = self._evaluate_condition(part.strip(), record, params, param_idx)
                result = result or cond_result
            return result, param_idx
        
        return self._evaluate_condition(where_clause, record, params, param_idx)
    
    # CORREÇÃO BUG 3 e BUG 9: Retorna tupla e usa re.fullmatch para LIKE
    def _evaluate_condition(self, condition: str, record: Dict, params: Tuple, param_idx: int) -> Tuple[bool, int]:
        """
        Avalia uma condição individual.
        Retorna (bool_resultado, next_param_idx).
        """
        condition = condition.strip()
        
        # LIKE - CORREÇÃO BUG 9: Usa re.fullmatch para match correto
        like_match = re.match(r'(\w+)\s+LIKE\s+\?', condition, re.IGNORECASE)
        if like_match:
            col = like_match.group(1)
            pattern = params[param_idx] if param_idx < len(params) else ''
            value = str(record.get(col, '') or '')
            regex_pattern = pattern.replace('%', '.*').replace('_', '.')
            return bool(re.fullmatch(regex_pattern, value, re.IGNORECASE)), param_idx + 1
        
        # = ?
        eq_match = re.match(r'(\w+)\s*=\s*\?', condition, re.IGNORECASE)
        if eq_match:
            col = eq_match.group(1)
            value = params[param_idx] if param_idx < len(params) else None
            return str(record.get(col, '')) == str(value), param_idx + 1
        
        # = 'valor'
        eq_literal_match = re.match(r'(\w+)\s*=\s*[\'"]([^\'"]+)[\'"]', condition, re.IGNORECASE)
        if eq_literal_match:
            col = eq_literal_match.group(1)
            value = eq_literal_match.group(2)
            return str(record.get(col, '')) == value, param_idx
        
        # != 'valor'
        neq_match = re.match(r'(\w+)\s*!=\s*[\'"]([^\'"]+)[\'"]', condition, re.IGNORECASE)
        if neq_match:
            col = neq_match.group(1)
            value = neq_match.group(2)
            return str(record.get(col, '')) != value, param_idx
        
        # > ?
        gt_match = re.match(r'(\w+)\s*>\s*\?', condition, re.IGNORECASE)
        if gt_match:
            col = gt_match.group(1)
            value = params[param_idx] if param_idx < len(params) else ''
            return str(record.get(col, '')) > str(value), param_idx + 1
        
        # >= ?
        gte_match = re.match(r'(\w+)\s*>=\s*\?', condition, re.IGNORECASE)
        if gte_match:
            col = gte_match.group(1)
            value = params[param_idx] if param_idx < len(params) else ''
            return str(record.get(col, '')) >= str(value), param_idx + 1
        
        # < ?
        lt_match = re.match(r'(\w+)\s*<\s*\?', condition, re.IGNORECASE)
        if lt_match:
            col = lt_match.group(1)
            value = params[param_idx] if param_idx < len(params) else ''
            return str(record.get(col, '')) < str(value), param_idx + 1
        
        # <= ?
        lte_match = re.match(r'(\w+)\s*<=\s*\?', condition, re.IGNORECASE)
        if lte_match:
            col = lte_match.group(1)
            value = params[param_idx] if param_idx < len(params) else ''
            return str(record.get(col, '')) <= str(value), param_idx + 1
        
        # BETWEEN - CORREÇÃO BUG 3: Consome 2 parâmetros
        between_match = re.match(r'(\w+)\s+BETWEEN\s+\?\s+AND\s+\?', condition, re.IGNORECASE)
        if between_match:
            col = between_match.group(1)
            value1 = params[param_idx] if param_idx < len(params) else ''
            value2 = params[param_idx + 1] if (param_idx + 1) < len(params) else ''
            record_value = str(record.get(col, ''))
            return value1 <= record_value <= value2, param_idx + 2
        
        # IS NULL
        is_null_match = re.match(r'(\w+)\s+IS\s+NULL', condition, re.IGNORECASE)
        if is_null_match:
            col = is_null_match.group(1)
            return not record.get(col), param_idx
        
        # IS NOT NULL
        is_not_null_match = re.match(r'(\w+)\s+IS\s+NOT\s+NULL', condition, re.IGNORECASE)
        if is_not_null_match:
            col = is_not_null_match.group(1)
            return bool(record.get(col)), param_idx
        
        logger.warning(f"Condição WHERE não reconhecida: {condition}")
        return True, param_idx
    
    def _apply_order_by(self, sql: str, records: List[Dict]) -> List[Dict]:
        """Aplica ORDER BY aos registros."""
        order_match = re.search(r'ORDER\s+BY\s+(\w+)(?:\s+(ASC|DESC))?', sql, re.IGNORECASE)
        if not order_match:
            return records
        
        col = order_match.group(1)
        direction = (order_match.group(2) or 'ASC').upper()
        
        def sort_key(record):
            value = record.get(col, '')
            try:
                return float(value)
            except (ValueError, TypeError):
                return str(value)
        
        return sorted(records, key=sort_key, reverse=(direction == 'DESC'))
    
    def fetchone(self) -> Optional[SheetsRow]:
        """Retorna a próxima linha do resultado."""
        if self._results:
            return self._results.pop(0)
        return None
    
    def fetchall(self) -> List[SheetsRow]:
        """Retorna todas as linhas do resultado."""
        results = self._results.copy()
        self._results = []
        return results
    
    def fetchmany(self, size: int = 1) -> List[SheetsRow]:
        """Retorna até 'size' linhas do resultado."""
        results = self._results[:size]
        self._results = self._results[size:]
        return results
    
    def close(self):
        """Fecha o cursor (no-op para Google Sheets)."""
        pass


class SheetsConnection:
    """
    Simula sqlite3.Connection, fornecendo uma interface compatível
    para operações no Google Sheets.
    """
    def __init__(self):
        self.spreadsheet = get_spreadsheet()
        self._closed = False
    
    def cursor(self) -> SheetsCursor:
        """Retorna um novo cursor."""
        if self._closed:
            raise ValueError("Connection is closed.")
        return SheetsCursor(self)
    
    def execute(self, sql: str, params: Tuple = ()) -> SheetsCursor:
        """Executa uma query diretamente na connection."""
        cursor = self.cursor()
        cursor.execute(sql, params)
        return cursor
    
    def commit(self):
        """
        Confirma as alterações.
        No Google Sheets, as alterações são aplicadas imediatamente.
        """
        pass
    
    def rollback(self):
        """
        Reverte as alterações.
        Google Sheets não suporta transações nativas.
        """
        logger.warning("Google Sheets não suporta transações. Rollback ignorado.")
    
    def close(self):
        """Fecha a conexão."""
        self._closed = True
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def get_db_connection() -> SheetsConnection:
    """
    Função principal que substitui a get_db_connection() do SQLite.
    Retorna uma SheetsConnection compatível com sqlite3.Connection.
    """
    return SheetsConnection()


def clear_cache():
    """Limpa o cache de leituras."""
    _cache.clear()


def invalidate_table_cache(table_name: str):
    """Invalida o cache de uma tabela específica."""
    sheet_name = TABLE_NAMES.get(table_name, table_name)
    cache_key = f"ws_{sheet_name}"
    if cache_key in _cache:
        del _cache[cache_key]