"""
Essência RH - Sistema de Departamento Pessoal
Versão com Google Sheets API + Melhorias de Segurança
"""

import os
import re
import csv
import hashlib
import logging
from io import BytesIO, TextIOWrapper
from datetime import datetime, timezone, timedelta
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, abort
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv

# Importa a nova camada de dados e integrações
from database_sheets import get_db_connection
import integracoes

# Carrega variáveis de ambiente do arquivo .env (desenvolvimento local)
load_dotenv()

# =============================================================================
# CONFIGURAÇÃO DA APLICAÇÃO
# =============================================================================

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'teste_cpFani_dev_only')

# Configuração de logging estruturado
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Proteção CSRF global
csrf = CSRFProtect(app)

# Rate limiting para mitigar força bruta no login
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# =============================================================================
# DECORATORS E UTILITÁRIOS
# =============================================================================

def requer_perfil(perfis_permitidos):
    """
    Decorator para proteger rotas baseado no perfil do usuário.
    Perfis: 1=Administrador, 2=Operador RH, 3=Auditor
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            if session.get('perfil') not in perfis_permitidos:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def get_horario_brasilia():
    """Retorna a data/hora atual no fuso horário de Brasília (UTC-3)."""
    fuso_brasilia = timezone(timedelta(hours=-3))
    return datetime.now(fuso_brasilia)

# =============================================================================
# FILTROS JINJA E HELPERS
# =============================================================================

@app.template_filter('data_br') 
def formatar_data_br(data_str):
    """
    Converte qualquer string de data para DD/MM/AAAA (exibição).
    Aceita AAAA-MM-DD (ISO) ou DD/MM/AAAA (já formatado).
    Retorna '' se a entrada for None ou inválida.
    """
    if not data_str:
        return ''
    data_str = str(data_str).strip()
    try:
        if '-' in data_str:
            return datetime.strptime(data_str, '%Y-%m-%d').strftime('%d/%m/%Y')
        elif '/' in data_str:
            datetime.strptime(data_str, '%d/%m/%Y')  # valida formato
            return data_str
    except ValueError:
        pass
    return data_str
 
def para_iso(data_str):
    """
    Converte DD/MM/AAAA para AAAA-MM-DD (armazenamento).
    Aceita qualquer dos dois formatos.
    """
    if not data_str:
        return ''
    data_str = str(data_str).strip()
    try:
        if '/' in data_str:
            return datetime.strptime(data_str, '%d/%m/%Y').strftime('%Y-%m-%d')
        elif '-' in data_str:
            datetime.strptime(data_str, '%Y-%m-%d')  # valida
            return data_str
    except ValueError:
        pass
    return data_str

# Registra os helpers no Jinja para uso direto nos templates
app.jinja_env.globals['formatar_data_br'] = formatar_data_br
 
def validar_cpf(cpf):
    """
    Valida CPF removendo máscara e calculando dígitos verificadores.
    Retorna True se válido, False caso contrário.
    """
    cpf = re.sub(r'\D', '', str(cpf))
    if len(cpf) != 11:
        return False
    if len(set(cpf)) == 1:  # rejeita 111.111.111-11, 000.000.000-00, etc.
        return False
 
    # 1º dígito verificador
    soma = sum(int(cpf[i]) * (10 - i) for i in range(9))
    d1 = (soma * 10) % 11
    if d1 in (10, 11):
        d1 = 0
    if d1 != int(cpf[9]):
        return False
 
    # 2º dígito verificador
    soma = sum(int(cpf[i]) * (11 - i) for i in range(10))
    d2 = (soma * 10) % 11
    if d2 in (10, 11):
        d2 = 0
    if d2 != int(cpf[10]):
        return False
 
    return True
 
def validar_email(email):
    """
    Valida formato básico de e-mail com regex.
    Exige usuário, @, domínio e extensão de pelo menos 2 caracteres.
    """
    if not email:
        return True 
    regex = r'^[^\s@]+@[^\s@]+\.[^\s@]{2,}$'
    return bool(re.match(regex, str(email).strip()))

# =============================================================================
# PROCESSAMENTO DE REGRAS DE STATUS TEMPORAIS
# =============================================================================

def processar_regras_de_status_temporais(db):
    """
    Varre o banco executando a transição de estados baseada no tempo cronológico.
    Garante integridade e obedece à hierarquia de status do RH.
    """
    hoje = get_horario_brasilia().strftime('%Y-%m-%d')
    
    # -------------------------------------------------------------------------
    # PASSO 1: ATUALIZAÇÃO DA TABELA DE FÉRIAS
    # -------------------------------------------------------------------------
    
    # Busca todas as férias para processamento em Python
    ferias = db.execute("SELECT id, data_inicio, data_fim, status_ferias FROM ferias").fetchall()
    
    for ferias_row in ferias:
        # Se hoje entrou no período de férias e estava 'Agendada', vira 'Em Gozo'
        if ferias_row['status_ferias'] == 'Agendada' and ferias_row['data_inicio'] <= hoje <= ferias_row['data_fim']:
            db.execute("UPDATE ferias SET status_ferias = 'Em Gozo' WHERE id = ?", (ferias_row['id'],))
        
        # Se hoje já passou da data fim e estava 'Em Gozo', vira 'Concluída'
        elif ferias_row['status_ferias'] == 'Em Gozo' and hoje > ferias_row['data_fim']:
            db.execute("UPDATE ferias SET status_ferias = 'Concluída' WHERE id = ?", (ferias_row['id'],))
    
    # -------------------------------------------------------------------------
    # PASSO 2: ATUALIZAÇÃO DA TABELA DE FUNCIONÁRIOS (A MÁQUINA DE ESTADOS)
    # -------------------------------------------------------------------------
    
    # Busca todas as ocorrências e férias para processamento
    ocorrencias = db.execute("SELECT funcionario_id, data_inicio, data_fim, tipo FROM ocorrencias").fetchall()
    ferias_gozo = db.execute("SELECT funcionario_id FROM ferias WHERE status_ferias = 'Em Gozo'").fetchall()
    
    funcionarios_ids_afastamento = set()
    for oc in ocorrencias:
        if oc['tipo'] == 'AFASTAMENTO' and oc['data_inicio'] <= hoje <= oc['data_fim']:
            funcionarios_ids_afastamento.add(oc['funcionario_id'])
    
    funcionarios_ids_ferias = set(f['funcionario_id'] for f in ferias_gozo)
    
    # Busca todos os funcionários para processamento
    funcionarios = db.execute("SELECT id, status FROM funcionarios").fetchall()
    
    for func in funcionarios:
        func_id = func['id']
        status_atual = func['status']
        
        # A. GATILHO DE AFASTAMENTO
        if func_id in funcionarios_ids_afastamento and status_atual != 'Desligado':
            db.execute("UPDATE funcionarios SET status = 'Afastado' WHERE id = ?", (func_id,))
        
        # B. GATILHO DE FÉRIAS
        elif func_id in funcionarios_ids_ferias and status_atual not in ['Desligado', 'Afastado']:
            db.execute("UPDATE funcionarios SET status = 'Férias' WHERE id = ?", (func_id,))
        
        # C. RETORNO AO ESTADO ATIVO
        elif status_atual in ['Férias', 'Afastado']:
            if func_id not in funcionarios_ids_ferias and func_id not in funcionarios_ids_afastamento:
                db.execute("UPDATE funcionarios SET status = 'Ativo' WHERE id = ?", (func_id,))
    
    db.commit()

# =============================================================================
# LEMBRETES AUTOMÁTICOS
# =============================================================================

def verificar_e_gerar_lembretes():
    """
    Verifica condições para gerar lembretes automáticos (experiência, férias, aniversários).
    Integra com o módulo de notificações (Telegram/Email) quando um novo lembrete é criado.
    """
    db = get_db_connection()
    hoje = get_horario_brasilia().date()
    funcionarios = db.execute('SELECT id, nome, data_admissao, data_nascimento FROM funcionarios').fetchall()
 
    for f in funcionarios:
        if f['data_admissao']:
            try:
                adm = datetime.strptime(para_iso(f['data_admissao']), '%Y-%m-%d').date()
 
                for dias, titulo in [(45, "Vencimento de Experiência (45 dias)"),
                                     (90, "Vencimento de Experiência (90 dias)")]:
                    d_alvo = adm + timedelta(days=dias)
                    if hoje <= d_alvo <= (hoje + timedelta(days=7)):
                        # Busca lembretes existentes
                        lembretes = db.execute(
                            "SELECT id, titulo, status FROM lembretes WHERE funcionario_id = ?",
                            (f['id'],)).fetchall()
                        
                        existe = any(l['titulo'] == titulo and l['status'] == 'Ativo' for l in lembretes)
                        
                        if not existe:
                            db.execute(
                                "INSERT INTO lembretes (funcionario_id, titulo, descricao, data_alerta, status) VALUES (?, ?, ?, ?, 'Ativo')",
                                (f['id'], titulo,
                                 f"Avaliar contrato de {f['nome']} — prazo de {dias} dias.",
                                 d_alvo.isoformat()))
                            
                            # Dispara alerta externo
                            integracoes.disparar_alerta_geral(
                                titulo,
                                f"Avaliar contrato de {f['nome']} — prazo de {dias} dias."
                            )
 
                dVenc = adm + timedelta(days=320)
                if hoje >= dVenc:
                    ferias = db.execute(
                        "SELECT id, status_ferias FROM ferias WHERE funcionario_id = ?",
                        (f['id'],)).fetchall()
                    com_ferias = any(fe['status_ferias'] == 'Agendada' for fe in ferias)
                    
                    if not com_ferias:
                        titulo_alerta = "Alerta Crítico: Vencimento de Férias"
                        lembretes = db.execute(
                            "SELECT id, titulo, status FROM lembretes WHERE funcionario_id = ?",
                            (f['id'],)).fetchall()
                        existe = any(l['titulo'] == titulo_alerta and l['status'] == 'Ativo' for l in lembretes)
                        
                        if not existe:
                            db.execute(
                                "INSERT INTO lembretes (funcionario_id, titulo, descricao, data_alerta, status) VALUES (?, ?, ?, ?, 'Ativo')",
                                (f['id'], titulo_alerta,
                                 f"{f['nome']} está prestes a vencer o período aquisitivo sem férias programadas.",
                                 hoje.isoformat()))
                            
                            # Dispara alerta externo
                            integracoes.disparar_alerta_geral(
                                titulo_alerta,
                                f"{f['nome']} está prestes a vencer o período aquisitivo sem férias programadas."
                            )
            except Exception as e:
                logger.error(f"Erro ao processar alertas para ID {f['id']}: {e}")
 
        if f['data_nascimento']:
            try:
                nasc = datetime.strptime(para_iso(f['data_nascimento']), '%Y-%m-%d').date()
                aniversario_atual = datetime(hoje.year, nasc.month, nasc.day).date()
                if aniversario_atual < hoje:
                    aniversario_atual = datetime(hoje.year + 1, nasc.month, nasc.day).date()
 
                if hoje <= aniversario_atual <= (hoje + timedelta(days=7)):
                    titulo_alerta = "Aniversariante do Dia!" if aniversario_atual == hoje else "Aniversário Próximo"
                    
                    lembretes = db.execute(
                        "SELECT id, titulo, data_alerta, status FROM lembretes WHERE funcionario_id = ?",
                        (f['id'],)).fetchall()
                    
                    existe = any(
                        'Aniversário' in l['titulo'] and 
                        l['data_alerta'] == aniversario_atual.isoformat() and 
                        l['status'] == 'Ativo' 
                        for l in lembretes
                    )
                    
                    if not existe:
                        msg = (f"Hoje é o aniversário de {f['nome']}!" if aniversario_atual == hoje
                               else f"{f['nome']} fará aniversário em {aniversario_atual.strftime('%d/%m')}.")
                        db.execute(
                            "INSERT INTO lembretes (funcionario_id, titulo, descricao, data_alerta, status) VALUES (?, ?, ?, ?, 'Ativo')",
                            (f['id'], titulo_alerta, msg, aniversario_atual.isoformat()))
                        
                        # Dispara alerta externo
                        integracoes.disparar_alerta_geral(
                            titulo_alerta,
                            msg
                        )
            except Exception as e:
                logger.error(f"Erro ao processar aniversário para ID {f['id']}: {e}")
 
    db.close()

# =============================================================================
# AUTENTICAÇÃO
# =============================================================================

def verify_password(stored_password, provided_password):
    """Verifica a senha usando PBKDF2-HMAC-SHA256 com salt."""
    if isinstance(stored_password, str):
        stored_password = stored_password.encode('latin-1')
    salt = stored_password[:32]
    original_hash = stored_password[32:]
    new_hash = hashlib.pbkdf2_hmac('sha256', provided_password.encode('utf-8'), salt, 100000)
    return new_hash == original_hash

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")  # Rate limiting para mitigar força bruta
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db_connection()
        user = db.execute('SELECT * FROM usuarios WHERE username = ?', (username,)).fetchone()
        db.close()
        
        if user and verify_password(user['senha'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['perfil'] = user['perfil_id']
            logger.info(f"Login bem-sucedido: {username}")
            return redirect(url_for('dashboard'))
        
        logger.warning(f"Tentativa de login falhou para: {username}")
        flash('Usuário ou senha inválidos.', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# =============================================================================
# DASHBOARD
# =============================================================================

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    verificar_e_gerar_lembretes()
 
    db = get_db_connection()
    hoje = get_horario_brasilia().date()
    mes_atual_str = hoje.strftime('%m')
    ano_atual_str = hoje.strftime('%Y')
 
    processar_regras_de_status_temporais(db)
    
    # Busca todos os funcionários para processamento em Python
    todos_funcionarios = db.execute("SELECT * FROM funcionarios").fetchall()
    
    count_ativos = sum(1 for f in todos_funcionarios if f['status'] == 'Ativo')
    
    count_admitidos = sum(
        1 for f in todos_funcionarios 
        if f['data_admissao'] and 
           f['data_admissao'][5:7] == mes_atual_str and 
           f['data_admissao'][0:4] == ano_atual_str
    )
    
    count_desligados = sum(
        1 for f in todos_funcionarios 
        if f['status'] == 'Desligado' and 
           f['data_desligamento'] and 
           f['data_desligamento'][5:7] == mes_atual_str and 
           f['data_desligamento'][0:4] == ano_atual_str
    )
    
    # Busca ocorrências do mês
    todas_ocorrencias = db.execute("SELECT * FROM ocorrencias").fetchall()
    count_ocorrencias = sum(
        1 for oc in todas_ocorrencias 
        if oc['data_inicio'] and 
           oc['data_inicio'][5:7] == mes_atual_str and 
           oc['data_inicio'][0:4] == ano_atual_str
    )

    funcionarios_ativos = [f for f in todos_funcionarios if f['status'] == 'Ativo']
 
    # Aniversariantes do mês
    aniversariantes = []
    for f in funcionarios_ativos:
        if f['data_nascimento'] and f['data_nascimento'][5:7] == mes_atual_str:
            dia = f['data_nascimento'][8:10]
            aniversariantes.append({
                'id': f['id'],
                'nome': f['nome'],
                'data_nascimento': f['data_nascimento'],
                'dia': dia,
                'data_completa': f"{dia.zfill(2)}/{mes_atual_str}"
            })
    
    aniversariantes.sort(key=lambda x: int(x['dia']))
 
    # Alerta de vencimento de férias
    alerta_vencimento = []
    for f in funcionarios_ativos:
        try:
            if f['data_admissao']:
                adm = datetime.strptime(para_iso(f['data_admissao']), '%Y-%m-%d').date()
                if (hoje - adm).days >= 320:
                    ferias_func = db.execute(
                        "SELECT id, status_ferias FROM ferias WHERE funcionario_id = ?",
                        (f['id'],)).fetchall()
                    tem_ferias = any(fe['status_ferias'] == 'Agendada' for fe in ferias_func)
                    
                    if not tem_ferias:
                        alerta_vencimento.append(f)
        except Exception as e:
            logger.error(f"Erro ao verificar vencimento de férias para ID {f['id']}: {e}")
            continue
 
    # Saídas próxima semana
    proxima_semana = (hoje + timedelta(days=7)).strftime('%Y-%m-%d')
    todas_ferias = db.execute("SELECT * FROM ferias").fetchall()
    
    saidas_breve = []
    for fe in todas_ferias:
        func = next((f for f in todos_funcionarios if f['id'] == fe['funcionario_id']), None)
        if func and func['status'] == 'Ativo' and fe['data_inicio']:
            if hoje.strftime('%Y-%m-%d') <= fe['data_inicio'] <= proxima_semana:
                dt = datetime.strptime(fe['data_inicio'], '%Y-%m-%d')
                saidas_breve.append({
                    'nome': func['nome'],
                    'data_inicio': fe['data_inicio'],
                    'data_formatada': dt.strftime('%d/%m')
                })
 
    # Alertas de experiência
    alertas_experiencia = []
    for f in funcionarios_ativos:
        try:
            if f['data_admissao']:
                adm = datetime.strptime(para_iso(f['data_admissao']), '%Y-%m-%d').date()                
                dias_corridos = (hoje - adm).days
                
                if dias_corridos > 90:
                    continue
                
                if 40 <= dias_corridos <= 45:
                    f_dict = dict(f)
                    f_dict['mensagem_exp'] = f"Fase 1 (45 dias) vence em {45 - dias_corridos} dia(s)!"
                    alertas_experiencia.append(f_dict)
                elif 85 <= dias_corridos <= 90:
                    f_dict = dict(f)
                    f_dict['mensagem_exp'] = f"Contrato Final (90 dias) vence em {90 - dias_corridos} dia(s)!"
                    alertas_experiencia.append(f_dict)
        except Exception as e:
            logger.error(f"Erro no alerta de experiência para o ID {f.get('id')}: {e}")
            continue
 
    db.close()
    
    return render_template('dashboard.html',
                           nome=session['username'],
                           perfil=session['perfil'],
                           ativos=count_ativos,
                           admitidos=count_admitidos,
                           desligados=count_desligados,
                           ocorrencias_mes=count_ocorrencias,
                           alerta_experiencia=alertas_experiencia,
                           aniversariantes=aniversariantes,
                           alerta_vencimento=alerta_vencimento,
                           saidas_breve=saidas_breve)

# =============================================================================
# EXPORTAÇÃO
# =============================================================================

@app.route('/exportar_aniversariantes_mes')
@requer_perfil([1, 2])
def exportar_aniversariantes_mes():
    if 'user_id' not in session:
        return "Acesso negado!", 401
    
    db = get_db_connection()
    mes_atual_str = get_horario_brasilia().strftime('%m')
    funcionarios = db.execute("SELECT * FROM funcionarios WHERE status = 'Ativo'").fetchall()
    db.close()
 
    # Filtra aniversariantes do mês em Python
    aniversariantes = [
        f for f in funcionarios 
        if f['data_nascimento'] and f['data_nascimento'][5:7] == mes_atual_str
    ]
    
    # Ordena por dia
    aniversariantes.sort(key=lambda x: int(x['data_nascimento'][8:10]))
 
    output = BytesIO()
    output.write(b'\xef\xbb\xbf')
    stream = TextIOWrapper(output, encoding='utf-8', newline='')
    writer = csv.writer(stream, delimiter=';', quoting=csv.QUOTE_MINIMAL)
    writer.writerow(['Nome', 'Cargo', 'Filial', 'Data de Aniversário'])
    
    for f in aniversariantes:
        writer.writerow([
            f['nome'], 
            f.get('cargo', ''), 
            f.get('filial', ''),
            formatar_data_br(f['data_nascimento'])
        ])
    
    stream.flush()
    output.seek(0)
    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-disposition": "attachment; filename=aniversariantes_do_mes.csv"})

# =============================================================================
# CADASTRO
# =============================================================================

@app.route('/cadastrar', methods=['GET', 'POST'])
@requer_perfil([1, 2])
def cadastrar():
    if 'user_id' not in session or session['perfil'] not in [1, 2]:
        return "Acesso negado!", 403
 
    if request.method == 'POST':
        # Coleta
        cpf        = re.sub(r'\D', '', request.form.get('cpf', ''))
        nome       = request.form.get('nome', '').strip()
        email      = request.form.get('email', '').strip()
 
        # Validações do backend
        erros = []
        if not validar_cpf(cpf):
            erros.append('CPF inválido. Verifique os dígitos informados.')
        if email and not validar_email(email):
            erros.append('E-mail com formato inválido.')
        if not nome:
            erros.append('O nome do colaborador é obrigatório.')
 
        if erros:
            for e in erros:
                flash(e, 'danger')
            return redirect(url_for('cadastrar'))
 
        # Datas: garante armazenamento ISO independente do que veio do form
        data_nascimento = para_iso(request.form.get('data_nascimento', ''))
        data_admissao   = para_iso(request.form.get('data_admissao', ''))
 
        estado_civil    = request.form.get('estado_civil')
        sexo            = request.form.get('sexo')
        raca            = request.form.get('raca')
        escolaridade    = request.form.get('escolaridade')
        telefone        = re.sub(r'\D', '', request.form.get('telefone', ''))
        banco           = request.form.get('banco')
        agencia         = request.form.get('agencia')
        conta           = request.form.get('conta')
        modalidade_conta= request.form.get('modalidade_conta')
        endereco_cep    = re.sub(r'\D', '', request.form.get('endereco_cep', ''))
        endereco_rua    = request.form.get('endereco_rua')
        endereco_num    = request.form.get('endereco_num')
        endereco_bairro = request.form.get('endereco_bairro')
        endereco_cidade = request.form.get('endereco_cidade')
        endereco_estado = request.form.get('endereco_estado')
        optou_convenio  = request.form.get('optou_convenio')
        totalpass       = request.form.get('totalpass')
        vt              = request.form.get('vt')
        cargo           = request.form.get('cargo')
        nivel           = request.form.get('nivel')
        area            = request.form.get('area')
        login_extranet  = request.form.get('login_extranet')
        filial          = request.form.get('filial')
        gestor          = request.form.get('gestor')
        status          = request.form.get('status', 'Ativo')
 
        salario_raw = request.form.get('salario', '0')
        try:
            salario = float(salario_raw.replace('.', '').replace(',', '.')) if salario_raw else 0.0
        except ValueError:
            salario = 0.0
 
        db = get_db_connection()
        try:
            with db:
                cursor = db.execute('''
                    INSERT INTO funcionarios (
                        cpf, nome, data_nascimento, estado_civil, telefone, email, sexo, raca, escolaridade,
                        banco, agencia, conta, modalidade_conta, endereco_rua, endereco_num, endereco_bairro,
                        endereco_cidade, endereco_estado, endereco_cep, optou_convenio, totalpass, vt, salario,
                        cargo, nivel, area, filial, gestor, login_extranet, data_admissao, status
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ''', (cpf, nome, data_nascimento, estado_civil, telefone, email, sexo, raca, escolaridade,
                      banco, agencia, conta, modalidade_conta, endereco_rua, endereco_num, endereco_bairro,
                      endereco_cidade, endereco_estado, endereco_cep, optou_convenio, totalpass, vt, salario,
                      cargo, nivel, area, filial, gestor, login_extranet, data_admissao, status))
 
                novo_id = cursor.lastrowid
                agora_br = get_horario_brasilia().strftime('%d/%m/%Y %H:%M:%S')
                db.execute('''INSERT INTO historico_movimentacoes
                    (funcionario_id, usuario_id, tipo_movimentacao, valor_novo, observacao, data_evento)
                    VALUES (?,?,?,?,?,?)''',
                    (novo_id, session['user_id'], 'CADASTRO', nome,
                     'Novo colaborador inserido com ficha completa', agora_br))
 
            flash('Funcionário cadastrado com sucesso!', 'success')
            return redirect(url_for('listar_funcionarios'))
        except Exception as e:
            logger.error(f"Erro ao cadastrar no banco de dados: {e}")
            return f"Erro ao cadastrar no banco de dados: {e}"
        finally:
            db.close()
 
    return render_template('cadastrar.html')

# =============================================================================
# LISTAGEM
# =============================================================================

@app.route('/funcionarios')
@requer_perfil([1, 2])
def listar_funcionarios():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    termo_busca = request.args.get('busca', '').strip()
    termo_limpo = re.sub(r'\D', '', termo_busca) 
    
    db = get_db_connection()
    funcionarios = []
    
    if termo_busca:
        # Busca todos os funcionários ativos
        todos = db.execute("SELECT * FROM funcionarios WHERE status='Ativo'").fetchall()
        
        # Filtra em Python
        for f in todos:
            if termo_limpo:
                # Busca por CPF ou Nome
                cpf_limpo = re.sub(r'\D', '', str(f.get('cpf', '')))
                if termo_busca.lower() in f['nome'].lower() or termo_limpo in cpf_limpo:
                    funcionarios.append(f)
            else:
                # Busca apenas por Nome
                if termo_busca.lower() in f['nome'].lower():
                    funcionarios.append(f)
        
        # Ordena por nome
        funcionarios.sort(key=lambda x: x['nome'])
        
        if not funcionarios:
            flash(f"Nenhum colaborador encontrado para '{termo_busca}'.", "info")
    else:
        funcionarios = db.execute(
            "SELECT * FROM funcionarios WHERE status='Ativo' ORDER BY nome"
        ).fetchall()
        
    db.close()
    return render_template('lista_funcionarios.html',
                           funcionarios=funcionarios,
                           termo_busca=termo_busca)

@app.route('/funcionarios/desligados')
@requer_perfil([1, 2])
def listar_desligados():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    termo_busca = request.args.get('busca', '').strip()
    
    db = get_db_connection()
    funcionarios = []
    
    if termo_busca:
        todos = db.execute("SELECT * FROM funcionarios WHERE status='Desligado'").fetchall()
        
        for f in todos:
            cpf_limpo = re.sub(r'\D', '', str(f.get('cpf', '')))
            if termo_busca.lower() in f['nome'].lower() or termo_busca in cpf_limpo:
                funcionarios.append(f)
        
        # Ordena por data de desligamento (mais recente primeiro)
        funcionarios.sort(key=lambda x: x.get('data_desligamento', ''), reverse=True)
        
        if not funcionarios:
            flash(f"Nenhum registro encontrado para '{termo_busca}'.", "warning")
    else:
        funcionarios = db.execute(
            "SELECT * FROM funcionarios WHERE status='Desligado' ORDER BY data_desligamento DESC"
        ).fetchall()
        
    db.close()
    return render_template('lista_desligados.html',
                           funcionarios=funcionarios,
                           termo_busca=termo_busca,
                           nome=session.get('nome'))

@app.route('/funcionario/<int:id>')
@requer_perfil([1, 2])
def detalhes_funcionario(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    db = get_db_connection()
    func = db.execute('SELECT * FROM funcionarios WHERE id = ?', (id,)).fetchone()
    db.close()
    
    if not func:
        return "Funcionário não encontrado", 404
    
    return render_template('detalhes.html', f=func)

# =============================================================================
# BUSCA E EDIÇÃO
# =============================================================================

@app.route('/buscar_para_editar', methods=['POST'])
@requer_perfil([1, 2])
def buscar_para_editar():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    termo = re.sub(r'\D', '', request.form.get('termo_busca', '').strip())
    
    if len(termo) < 3:
        flash("Digite mais dígitos para realizar a busca (evite conflito com IDs).", "warning")
        return redirect(url_for('dashboard'))

    db = get_db_connection()
    
    # Busca todos os funcionários
    todos = db.execute("SELECT * FROM funcionarios").fetchall()
    
    # Filtra por CPF em Python
    funcionarios = []
    for f in todos:
        cpf_limpo = re.sub(r'\D', '', str(f.get('cpf', '')))
        if cpf_limpo.startswith(termo):
            funcionarios.append(f)
    
    db.close()
    
    total = len(funcionarios)
    
    if total == 0:
        flash(f'Nenhum colaborador encontrado com o CPF iniciado em "{termo}".', 'danger')
        return redirect(url_for('dashboard'))
    
    elif total == 1:
        func = funcionarios[0]
        if func['status'] == 'Desligado':
            flash(f"Atenção: O colaborador {func['nome']} está desligado.", "danger")
            return redirect(url_for('dashboard'))
        return redirect(url_for('editar_funcionario', id=func['id']))
    
    else:
        flash(f'{total} resultados encontrados. Refine o CPF.', 'info')
        return redirect(url_for('listar_funcionarios', busca=termo))

@app.route('/editar_funcionario/<int:id>', methods=['GET', 'POST'])
@requer_perfil([1, 2])
def editar_funcionario(id):
    db = get_db_connection()
    funcionario = db.execute('SELECT * FROM funcionarios WHERE id = ?', (id,)).fetchone()

    if not funcionario:
        db.close()
        flash("Cadastro não encontrado!", "warning")
        return redirect(url_for('listar_funcionarios'))

    if funcionario['status'] == 'Desligado':
        db.close()
        flash(f"O colaborador {funcionario['nome']} está desligado e não pode ser editado. Acesse o Arquivo Morto para consultar o registro.", "danger")
        return redirect(url_for('listar_funcionarios'))

    if request.method == 'POST':
        # Campos Sensíveis: Ignoramos o formulário e mantemos os dados originais do banco
        cpf_final = funcionario['cpf']
        nascimento_final = funcionario['data_nascimento']
        admissao_final = funcionario['data_admissao']
        login_extranet_final = funcionario['login_extranet']

        # Campos Editáveis: Coletamos do formulário
        status_novo = request.form.get('status')
        email_novo = request.form.get('email', '').strip()

        if email_novo and not validar_email(email_novo):
            flash('E-mail com formato inválido.', 'danger')
            return redirect(url_for('editar_funcionario', id=id))

        campos_formulario = {
            'cpf': cpf_final,
            'nome': request.form.get('nome', '').strip(),
            'data_nascimento': nascimento_final,
            'estado_civil': request.form.get('estado_civil'),
            'telefone': re.sub(r'\D', '', request.form.get('telefone', '')),
            'email': email_novo,
            'sexo': request.form.get('sexo'),
            'raca': request.form.get('raca'),
            'escolaridade': request.form.get('escolaridade'),
            'banco': request.form.get('banco'),
            'agencia': request.form.get('agencia'),
            'conta': request.form.get('conta'),
            'modalidade_conta': request.form.get('modalidade_conta'),
            'endereco_rua': request.form.get('endereco_rua'),
            'endereco_num': request.form.get('endereco_num'),
            'endereco_bairro': request.form.get('endereco_bairro'),
            'endereco_cidade': request.form.get('endereco_cidade'),
            'endereco_estado': request.form.get('endereco_estado'),
            'endereco_cep': re.sub(r'\D', '', request.form.get('endereco_cep', '')),
            'cargo': request.form.get('cargo'),
            'nivel': request.form.get('nivel'),
            'area': request.form.get('area'),
            'filial': request.form.get('filial'),
            'gestor': request.form.get('gestor'),
            'login_extranet': login_extranet_final,
            'data_admissao': admissao_final,
            'status': status_novo,
            'optou_convenio': request.form.get('optou_convenio'),
            'totalpass': request.form.get('totalpass'),
            'vt': request.form.get('vt'),
            'data_desligamento': para_iso(request.form.get('data_desligamento', '')) if status_novo == 'Desligado' else funcionario['data_desligamento'],
            'tipo_desligamento': request.form.get('tipo_desligamento') if status_novo == 'Desligado' else funcionario['tipo_desligamento'],
            'motivo_desligamento': request.form.get('motivo_desligamento') if status_novo == 'Desligado' else funcionario['motivo_desligamento']
        }

        salario_raw = request.form.get('salario')
        campos_formulario['salario'] = float(str(salario_raw).replace('.', '').replace(',', '.')) if salario_raw else funcionario['salario']

        try:
            with db:
                db.execute('''UPDATE funcionarios SET
                    cpf=?, nome=?, data_nascimento=?, estado_civil=?, telefone=?, email=?, sexo=?, raca=?, escolaridade=?,
                    banco=?, agencia=?, conta=?, modalidade_conta=?, endereco_rua=?, endereco_num=?, endereco_bairro=?,
                    endereco_cidade=?, endereco_estado=?, endereco_cep=?, salario=?, cargo=?, nivel=?, area=?, filial=?, 
                    gestor=?, login_extranet=?, data_admissao=?, status=?, optou_convenio=?, totalpass=?, vt=?, 
                    data_desligamento=?, tipo_desligamento=?, motivo_desligamento=? WHERE id=?''', 
                    (*list(campos_formulario.values()), id))
                flash('Alterações salvas com sucesso!', 'success')
            return redirect(url_for('listar_funcionarios'))
        except Exception as e:
            logger.error(f"Erro ao salvar: {e}")
            flash(f"Erro ao salvar: {e}", "danger")
        finally:
            db.close()

    return render_template('editar.html', funcionario=funcionario)

# =============================================================================
# DESLIGAMENTO
# =============================================================================

@app.route('/buscar_colaborador_desligar', methods=['POST'])
@requer_perfil([1, 2])
def buscar_colaborador_desligar():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    cpf = re.sub(r'\D', '', request.form.get('cpf', '').strip())
    db = get_db_connection()
    
    todos = db.execute("SELECT * FROM funcionarios").fetchall()
    
    funcionario = None
    for f in todos:
        cpf_limpo = re.sub(r'\D', '', str(f.get('cpf', '')))
        if cpf_limpo == cpf:
            funcionario = f
            break
    
    db.close()
    
    if not funcionario:
        flash("Colaborador não localizado com o CPF informado.", "danger")
        return redirect(url_for('dashboard'))
    
    if funcionario['status'] == 'Desligado':
        flash("Este colaborador já consta como desligado no sistema.", "warning")
        return redirect(url_for('dashboard'))
    
    return redirect(url_for('detalhes_funcionario', id=funcionario['id']))

@app.route('/desligar_funcionario/<int:id>', methods=['POST'])
@requer_perfil([1, 2])
def desligar_funcionario(id):
    db = get_db_connection()
    data_desligamento  = para_iso(request.form.get('data_desligamento', ''))
    tipo_desligamento  = request.form.get('type_desligamento')
    motivo_desligamento= request.form.get('motivo_desligamento', '')
    agora_br = get_horario_brasilia().strftime('%d/%m/%Y %H:%M:%S')
    
    try:
        with db:
            db.execute("""UPDATE funcionarios SET status='Desligado',
                data_desligamento=?, tipo_desligamento=?, motivo_desligamento=? WHERE id=?""",
                (data_desligamento, tipo_desligamento, motivo_desligamento, id))
            db.execute("""INSERT INTO historico_movimentacoes
                (funcionario_id, usuario_id, tipo_movimentacao, valor_antigo, valor_novo, observacao, data_evento)
                VALUES (?,?,?,?,?,?,?)""",
                (id, session['user_id'], 'DES', 'Ativo', 'Desligado',
                 f"Desligado. Tipo: {tipo_desligamento}. Motivo: {motivo_desligamento}", agora_br))
        flash('Colaborador desligado com sucesso e registrado na auditoria!', 'success')
    except Exception as e:
        logger.error(f'Erro ao processar desligamento: {e}')
        flash(f'Erro ao processar desligamento: {e}', 'error')
    finally:
        db.close()
    
    return redirect(url_for('listar_funcionarios'))

# =============================================================================
# FÉRIAS
# =============================================================================

@app.route('/lancar_ferias_busca', methods=['GET', 'POST'])
@app.route('/lancar_ferias_busca/<int:id>', methods=['GET', 'POST'])
@requer_perfil([1, 2])
def lancar_ferias_busca(id=None):
    db = get_db_connection()
    funcionario = None
    cpf_buscado = ""
    periodo_sugerido_inicio = ""
    periodo_sugerido_fim = ""
    pode_agendar = True
    pode_editar = False
    motivo_trava = ""
    ferias_existentes = None
    
    is_admin = (session.get('perfil') == 1)
 
    if id is not None:
        funcionario = db.execute(
            'SELECT id, nome, cpf, data_admissao, filial FROM funcionarios WHERE id = ?', (id,)).fetchone()
        if funcionario:
            cpf_buscado = funcionario['cpf']
 
    if request.method == 'POST' and 'buscar_cpf' in request.form:
        cpf_buscado = re.sub(r'\D', '', request.form['cpf'].strip())
        
        todos = db.execute("SELECT * FROM funcionarios WHERE status='Ativo'").fetchall()
        for f in todos:
            cpf_limpo = re.sub(r'\D', '', str(f.get('cpf', '')))
            if cpf_limpo == cpf_buscado:
                funcionario = f
                break
        
        if not funcionario:
            flash('Funcionário não encontrado!', 'danger')
 
    if funcionario:
        ano_atual  = datetime.now().year
        data_atual = datetime.now().date()
        try:
            dt_admissao = datetime.strptime(para_iso(funcionario['data_admissao']), '%Y-%m-%d').date()
        except Exception:
            dt_admissao = data_atual
 
        if data_atual < dt_admissao.replace(year=ano_atual):
            inicio_ciclo = dt_admissao.replace(year=ano_atual - 1)
            fim_ciclo    = dt_admissao.replace(year=ano_atual) - timedelta(days=1)
        else:
            inicio_ciclo = dt_admissao.replace(year=ano_atual)
            fim_ciclo    = dt_admissao.replace(year=ano_atual + 1) - timedelta(days=1)
 
        periodo_sugerido_inicio = inicio_ciclo.strftime('%Y-%m-%d')
        periodo_sugerido_fim    = fim_ciclo.strftime('%Y-%m-%d')
 
        todas_ferias = db.execute("SELECT * FROM ferias WHERE funcionario_id = ?", (funcionario['id'],)).fetchall()
        
        for fe in todas_ferias:
            if fe['status_ferias'] == 'Agendada' and fe['data_inicio'] and str(ano_atual) in fe['data_inicio']:
                ferias_existentes = fe
                break
 
        if ferias_existentes:
            pode_agendar = False
            try:
                dt_inicio_ferias = datetime.strptime(
                    para_iso(ferias_existentes['data_inicio']), '%Y-%m-%d').date()
            except Exception:
                dt_inicio_ferias = data_atual
            dias_restantes = (dt_inicio_ferias - data_atual).days
            
            if dias_restantes >= 30:
                pode_editar = True
            else:
                if is_admin:
                    pode_editar = True
                    motivo_trava = f"Aviso de Alçada: Restam apenas {dias_restantes} dias para o gozo. Alteração liberada exclusivamente por perfil Administrador."
                else:
                    pode_editar = False
                    motivo_trava = (f"Modificações bloqueadas. Restam apenas {dias_restantes} dias para o início "
                                    f"do gozo. A CLT exige antecedência mínima de 30 dias para alterações.")
 
    if request.method == 'POST' and 'salvar_ferias' in request.form:
        funcionario_id  = request.form['funcionario_id']
        action_type     = request.form.get('action_type', 'NEW')
        agora_br        = get_horario_brasilia().strftime('%d/%m/%Y %H:%M:%S')
 
        if action_type in ['UPDATE', 'CANCEL'] and not pode_editar and ferias_existentes:
            flash('Ação bloqueada! Prazo inferior a 30 dias exige perfil de Administrador.', 'danger')
            return redirect(url_for('lancar_ferias_busca', id=funcionario_id))
 
        try:
            with db:
                if action_type == 'CANCEL':
                    db.execute("UPDATE ferias SET status_ferias='Cancelada' WHERE id=?", (ferias_existentes['id'],))
                    db.execute('''INSERT INTO historico_movimentacoes
                        (funcionario_id, usuario_id, tipo_movimentacao, valor_antigo, valor_novo, observacao, data_evento)
                        VALUES(?,?,?,?,?,?,?)''',
                        (funcionario_id, session['user_id'], 'CANCELAMENTO_FERIAS',
                         f"{ferias_existentes['data_inicio']} até {ferias_existentes['data_fim']}",
                         "Status: Cancelada", "Cancelamento manual autorizado no painel de férias.", agora_br))
                    flash('Agendamento de férias cancelado com sucesso!', 'success')
                    return redirect(url_for('dashboard'))
 
                data_inicio_str = para_iso(request.form['data_inicio'])
                data_fim_str    = para_iso(request.form['data_fim'])
                periodo_inicio  = para_iso(request.form.get('periodo_aquisitivo_inicio', ''))
                periodo_fim     = para_iso(request.form.get('periodo_aquisitivo_fim', ''))
                abono           = request.form.get('abono_pecuniario', 'Não')
                
                dt_inicio_calc = datetime.strptime(data_inicio_str, '%Y-%m-%d')
                dt_fim_calc    = datetime.strptime(data_fim_str, '%Y-%m-%d')
                data_inicio = data_inicio_str
                data_fim = data_fim_str
 
                dias_gozo = (dt_fim_calc - dt_inicio_calc).days + 1
                dias_abono = 10 if abono == 'Sim' else 0
                total_impacto = dias_gozo + dias_abono
 
                if total_impacto > 30:
                    flash(f'Erro: A soma do descanso ({dias_gozo} dias) com o abono ({dias_abono} dias) resulta em {total_impacto} dias. O limite legal é 30.', 'danger')
                    return redirect(url_for('lancar_ferias_busca', id=funcionario_id))
                
                if dias_gozo <= 0:
                    flash('Erro: A data de término deve ser posterior ou igual à data de início.', 'danger')
                    return redirect(url_for('lancar_ferias_busca', id=funcionario_id))
 
                dt_inicio_obj = datetime.strptime(data_inicio, '%Y-%m-%d').date()
                dt_fim_aq_obj = datetime.strptime(periodo_fim, '%Y-%m-%d').date()
                
                if dt_inicio_obj <= dt_fim_aq_obj:
                    flash('Erro: A data de início das férias deve ser posterior ao fim do período aquisitivo.', 'danger')
                    return redirect(url_for('lancar_ferias_busca', id=funcionario_id))
 
                if action_type == 'UPDATE':
                    db.execute(
                        "UPDATE ferias SET data_inicio=?, data_fim=?, abono_pecuniario=? WHERE id=?",
                        (data_inicio, data_fim, abono, ferias_existentes['id']))
                    db.execute('''INSERT INTO historico_movimentacoes
                        (funcionario_id,usuario_id,tipo_movimentacao,valor_antigo,valor_novo,observacao,data_evento)
                        VALUES(?,?,?,?,?,?,?)''',
                        (funcionario_id, session['user_id'], 'REPROGRAMACAO_FERIAS',
                         f"{ferias_existentes['data_inicio']} até {ferias_existentes['data_fim']}",
                         f"{data_inicio} até {data_fim}", "Férias reprogramadas via painel.", agora_br))
                    flash('Período de férias reprogramado com sucesso!', 'success')
                else:
                    if not pode_agendar:
                        flash('Este colaborador já possui agendamento vigente para este ano.', 'danger')
                        return redirect(url_for('dashboard'))
                    db.execute('''INSERT INTO ferias
                        (funcionario_id, periodo_aquisitivo_inicio, periodo_aquisitivo_fim,
                         data_inicio, data_fim, abono_pecuniario, status_ferias)
                        VALUES(?,?,?,?,?,?,'Agendada')''',
                        (funcionario_id, periodo_inicio, periodo_fim, data_inicio, data_fim, abono))
                    db.execute('''INSERT INTO historico_movimentacoes
                        (funcionario_id,usuario_id,tipo_movimentacao,valor_novo,observacao,data_evento)
                        VALUES(?,?,?,?,?,?)''',
                        (funcionario_id, session['user_id'], 'FÉRIAS',
                         f"{data_inicio} a {data_fim}", f"Férias agendadas. Abono: {abono}", agora_br))
                    flash('Férias agendadas com sucesso!', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            logger.error(f"Erro ao salvar férias: {e}")
            return f"Erro ao salvar: {e}"
        
    db.close()
    return render_template('lancar_ferias.html',
                           funcionario=funcionario,
                           cpf_buscado=cpf_buscado,
                           periodo_inicio=periodo_sugerido_inicio,
                           periodo_fim=periodo_sugerido_fim,
                           pode_agendar=pode_agendar,
                           pode_editar=pode_editar,
                           motivo_trava=motivo_trava,
                           ferias=ferias_existentes)

# =============================================================================
# EXPERIÊNCIA
# =============================================================================

@app.route('/relatorio_experiencia')
@requer_perfil([1, 2])
def relatorio_experiencia():
    db = get_db_connection()
    funcionarios = db.execute("SELECT * FROM funcionarios WHERE status='Ativo'").fetchall()
    lista_exp = []
    hoje = get_horario_brasilia().date()
    
    for f in funcionarios:
        try:
            adm  = datetime.strptime(para_iso(f['data_admissao']), '%Y-%m-%d').date()
            d45  = adm + timedelta(days=45)
            d90  = adm + timedelta(days=90)
            if hoje > d90:
                continue
            alvo = d45 if hoje <= d45 else d90
            fase = "1ª Fase (45 dias)" if hoje <= d45 else "Fase Final (90 dias)"
            dias_restantes = (alvo - hoje).days

            if dias_restantes < 0:
                alerta = 'danger'
                mensagem_status = 'Vencido!'
            elif dias_restantes <= 5:
                alerta = 'warning'
                mensagem_status = f'Urgente ({dias_restantes} dias)'
            else:
                alerta = 'success'
                mensagem_status = f'Em dia ({dias_restantes} dias)'

            lista_exp.append({
                'nome':            f['nome'],
                'data_admissao':   adm.strftime('%d/%m/%Y'),
                'data_45':         d45.strftime('%d/%m/%Y'),
                'data_90':         d90.strftime('%d/%m/%Y'),
                'dias_restantes':  dias_restantes,
                'fase':            fase,
                'alerta':          alerta,
                'mensagem_status': mensagem_status,
            })
        except Exception as e:
            logger.error(f"Erro ao processar {f['nome']}: {e}")
    
    db.close()
    return render_template('experiencia.html', lista_exp=lista_exp)

# =============================================================================
# OCORRÊNCIAS
# =============================================================================

@app.route('/ocorrencias/nova', methods=['GET', 'POST'])
@requer_perfil([1, 2])
def nova_ocorrencia():
    if 'user_id' not in session:
        return redirect(url_for('login'))
 
    db = get_db_connection()
 
    if request.method == 'POST':
        funcionario_id   = request.form.get('funcionario_id')
        tipo             = request.form.get('tipo')
        data_inicio_str  = para_iso(request.form.get('data_inicio', ''))
        data_fim_str     = para_iso(request.form.get('data_fim', ''))
        cid              = request.form.get('cid', '')
        observacao_usuario = request.form.get('observacao', '')
 
        if not funcionario_id or not tipo or not data_inicio_str or not data_fim_str:
            flash('Preencha todos os campos obrigatórios.', 'error')
            db.close()
            return redirect(url_for('nova_ocorrencia'))
 
        try:
            dt_ini = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
            dt_fim = datetime.strptime(data_fim_str,    '%Y-%m-%d').date()
            quantidade_dias = (dt_fim - dt_ini).days + 1
            if quantidade_dias < 1:
                flash('A data de término não pode ser anterior à data de início.', 'error')
                db.close()
                return redirect(url_for('nova_ocorrencia'))
        except Exception as e:
            flash('Formato de data inválido.', 'error')
            db.close()
            return redirect(url_for('nova_ocorrencia'))
 
        try:
            agora_br = get_horario_brasilia().strftime('%d/%m/%Y %H:%M:%S')
            with db:
                db.execute("""INSERT INTO ocorrencias
                    (funcionario_id,tipo,data_inicio,data_fim,quantidade_dias,cid,observacao,data_registro)
                    VALUES(?,?,?,?,?,?,?,?)""",
                    (funcionario_id, tipo, data_inicio_str, data_fim_str, quantidade_dias, cid, observacao_usuario, agora_br))
 
                tipo_fmt = tipo.replace('_', ' ').title()
                detalhe  = f"Período: {data_inicio_str} até {data_fim_str} ({quantidade_dias} dias)."
                if cid:
                    detalhe += f" CID: {cid}."
                db.execute('''INSERT INTO historico_movimentacoes
                    (funcionario_id,usuario_id,tipo_movimentacao,valor_antigo,valor_novo,observacao,data_evento)
                    VALUES(?,?,?,?,?,?,?)''',
                    (funcionario_id, session['user_id'], 'OCORRENCIA',
                     'Regular/Disponível', tipo,
                     f"Lançamento de Ausência: {tipo_fmt} | {detalhe}", agora_br))
 
            flash('Ocorrência registrada e auditada com sucesso!', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            logger.error(f'Erro ao salvar ocorrência: {e}')
            flash(f'Erro ao salvar: {e}', 'error')
            return redirect(url_for('nova_ocorrencia'))
        finally:
            db.close()
 
    try:
        funcionarios = db.execute(
            "SELECT id, nome FROM funcionarios WHERE status='Ativo' ORDER BY nome").fetchall()
    except Exception:
        funcionarios = []
    
    db.close()
    return render_template('nova_ocorrencia.html', funcionarios=funcionarios, nome=session.get('nome'))

# =============================================================================
# AUDITORIA
# =============================================================================

@app.route('/auditoria')
@requer_perfil([1, 3])
def auditoria():
    POR_PAGINA = 30
    pagina_atual = request.args.get('pagina', 1, type=int)
    termo = request.args.get('busca', '').strip()
    
    db = get_db_connection()
    
    # Busca todos os logs de auditoria
    todos_logs = db.execute("SELECT * FROM historico_movimentacoes ORDER BY id DESC").fetchall()
    
    # Busca funcionários e usuários para JOIN
    funcionarios = {f['id']: f['nome'] for f in db.execute("SELECT id, nome FROM funcionarios").fetchall()}
    usuarios = {u['id']: u['username'] for u in db.execute("SELECT id, username FROM usuarios").fetchall()}
    
    db.close()
    
    # Filtra por termo de busca
    if termo:
        logs_filtrados = []
        for log in todos_logs:
            nome_func = funcionarios.get(log['funcionario_id'], '')
            if termo.lower() in nome_func.lower() or termo.lower() in log.get('observacao', '').lower():
                logs_filtrados.append(log)
        todos_logs = logs_filtrados
    
    # Paginação
    total = len(todos_logs)
    total_paginas = max(1, (total + POR_PAGINA - 1) // POR_PAGINA)
    offset = (pagina_atual - 1) * POR_PAGINA
    logs_pagina = todos_logs[offset:offset + POR_PAGINA]
    
    # Formata datas
    logs = []
    for log in logs_pagina:
        log_dict = dict(log)
        data_str = log_dict.get('data_evento')
        
        if data_str:
            try:
                dt_obj = datetime.strptime(data_str, '%d/%m/%Y %H:%M:%S')
                log_dict['data_evento'] = dt_obj.strftime('%d/%m/%Y %H:%M:%S')
            except ValueError:
                pass
        
        log_dict['funcionario'] = funcionarios.get(log_dict['funcionario_id'], 'N/A')
        log_dict['username'] = usuarios.get(log_dict['usuario_id'], 'N/A')
        
        logs.append(log_dict)

    return render_template('auditoria.html', 
                           logs=logs, 
                           pagina_atual=pagina_atual, 
                           total_paginas=total_paginas,
                           busca=termo)

if __name__ == '__main__':
    app.run(debug=True)