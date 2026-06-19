import sqlite3
import hashlib
import re
from flask import Flask, render_template, request, redirect, url_for, session, flash
import os
from datetime import datetime, timezone, timedelta
import csv
from flask import Response
from io import BytesIO, TextIOWrapper
from functools import wraps
from flask import abort, session
 
app = Flask(__name__)
app.secret_key = 'teste_cpFani'
 
# =============================================================================
# UTILITÁRIOS DE DATA E VALIDAÇÃO
# =============================================================================

def requer_perfil(perfis_permitidos):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))  # adicionar isso
            if session.get('perfil') not in perfis_permitidos:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def get_horario_brasilia():
    fuso_brasilia = timezone(timedelta(hours=-3))
    return datetime.now(fuso_brasilia)

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
    Converte DD/MM/AAAA para AAAA-MM-DD (armazenamento/SQLite).
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
 
# Registra os helpers no Jinja para uso direto nos templates
app.jinja_env.globals['formatar_data_br'] = formatar_data_br

def processar_regras_de_status_temporais(db):
    """
    Varre o banco executando a transição de estados baseada no tempo cronológico.
    Garante integridade e obedece à hierarquia de status do RH.
    """
    # Recupera a data atual baseada no fuso de Brasília definido nos seus utilitários
    hoje = get_horario_brasilia().strftime('%Y-%m-%d')
    
    # -------------------------------------------------------------------------
    # PASSO 1: ATUALIZAÇÃO DA TABELA DE FÉRIAS
    # -------------------------------------------------------------------------
    
    # Se hoje entrou no período de férias e estava 'Agendada', vira 'Em Gozo'
    db.execute("""
        UPDATE ferias 
        SET status_ferias = 'Em Gozo' 
        WHERE ? >= data_inicio AND ? <= data_fim AND status_ferias = 'Agendada'
    """, (hoje, hoje))
    
    # Se hoje já passou da data fim e estava 'Em Gozo', vira 'Concluída'
    db.execute("""
        UPDATE ferias 
        SET status_ferias = 'Concluída' 
        WHERE ? > data_fim AND status_ferias = 'Em Gozo'
    """, (hoje,))
    
    # -------------------------------------------------------------------------
    # PASSO 2: ATUALIZAÇÃO DA TABELA DE FUNCIONÁRIOS (A MÁQUINA DE ESTADOS)
    # -------------------------------------------------------------------------
    
    # A. GATILHO DE AFASTAMENTO: Se há ocorrência do tipo 'AFASTAMENTO' ativa hoje
    # Nota: Filtramos 'Desligado' para impedir que o sistema altere ex-funcionários
    db.execute("""
        UPDATE funcionarios 
        SET status = 'Afastado' 
        WHERE status != 'Desligado' 
          AND id IN (
              SELECT funcionario_id 
              FROM ocorrencias 
              WHERE tipo = 'AFASTAMENTO' AND ? >= data_inicio AND ? <= data_fim
          )
    """, (hoje, hoje))
    
    # B. GATILHO DE FÉRIAS: Se possui férias 'Em Gozo' e não está sob a regra de Afastado
    db.execute("""
        UPDATE funcionarios 
        SET status = 'Férias' 
        WHERE status != 'Desligado' 
          AND status != 'Afastado'
          AND id IN (
              SELECT funcionario_id 
              FROM ferias 
              WHERE status_ferias = 'Em Gozo'
          )
    """, ())
    
    # C. RETORNO AO ESTADO ATIVO: Se o funcionário está marcado como 'Férias' ou 'Afastado', 
    # mas o período do evento já expirou na data de hoje, ele volta a ser 'Ativo'
    db.execute("""
        UPDATE funcionarios 
        SET status = 'Ativo' 
        WHERE status IN ('Férias', 'Afastado')
          AND id NOT IN (
              SELECT funcionario_id FROM ferias WHERE status_ferias = 'Em Gozo'
          )
          AND id NOT IN (
              SELECT funcionario_id FROM ocorrencias WHERE tipo = 'AFASTAMENTO' AND ? >= data_inicio AND ? <= data_fim
          )
    """, (hoje, hoje))
    
    db.commit()
 
# =============================================================================
# BANCO DE DADOS
# =============================================================================
 
def get_db_connection():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, 'database.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn
 
# =============================================================================
# LEMBRETES AUTOMÁTICOS
# =============================================================================
 
def verificar_e_gerar_lembretes():
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
                        existe = db.execute(
                            "SELECT id FROM lembretes WHERE funcionario_id=? AND titulo=? AND status='Ativo'",
                            (f['id'], titulo)).fetchone()
                        if not existe:
                            with db:
                                db.execute(
                                    "INSERT INTO lembretes (funcionario_id,titulo,descricao,data_alerta,status) VALUES(?,?,?,?,'Ativo')",
                                    (f['id'], titulo,
                                     f"Avaliar contrato de {f['nome']} — prazo de {dias} dias.",
                                     d_alvo.isoformat()))
 
                dVenc = adm + timedelta(days=320)
                if hoje >= dVenc:
                    com_ferias = db.execute(
                        "SELECT id FROM ferias WHERE funcionario_id=? AND status_ferias='Agendada'",
                        (f['id'],)).fetchone()
                    if not com_ferias:
                        titulo_alerta = "Alerta Crítico: Vencimento de Férias"
                        existe = db.execute(
                            "SELECT id FROM lembretes WHERE funcionario_id=? AND titulo=? AND status='Ativo'",
                            (f['id'], titulo_alerta)).fetchone()
                        if not existe:
                            with db:
                                db.execute(
                                    "INSERT INTO lembretes (funcionario_id,titulo,descricao,data_alerta,status) VALUES(?,?,?,?,'Ativo')",
                                    (f['id'], titulo_alerta,
                                     f"{f['nome']} está prestes a vencer o período aquisitivo sem férias programadas.",
                                     hoje.isoformat()))
            except Exception as e:
                print(f"Erro ao processar alertas para ID {f['id']}: {e}")
 
        if f['data_nascimento']:
            try:
                nasc = datetime.strptime(para_iso(f['data_nascimento']), '%Y-%m-%d').date()
                aniversario_atual = datetime(hoje.year, nasc.month, nasc.day).date()
                if aniversario_atual < hoje:
                    aniversario_atual = datetime(hoje.year + 1, nasc.month, nasc.day).date()
 
                if hoje <= aniversario_atual <= (hoje + timedelta(days=7)):
                    titulo_alerta = "Aniversariante do Dia!" if aniversario_atual == hoje else "Aniversário Próximo"
                    existe = db.execute(
                        "SELECT id FROM lembretes WHERE funcionario_id=? AND titulo LIKE 'Aniversário%' AND data_alerta=? AND status='Ativo'",
                        (f['id'], aniversario_atual.isoformat())).fetchone()
                    if not existe:
                        msg = (f"Hoje é o aniversário de {f['nome']}!" if aniversario_atual == hoje
                               else f"{f['nome']} fará aniversário em {aniversario_atual.strftime('%d/%m')}.")
                        with db:
                            db.execute(
                                "INSERT INTO lembretes (funcionario_id,titulo,descricao,data_alerta,status) VALUES(?,?,?,?,'Ativo')",
                                (f['id'], titulo_alerta, msg, aniversario_atual.isoformat()))
            except Exception as e:
                print(f"Erro ao processar aniversário para ID {f['id']}: {e}")
 
    db.close()
 
# =============================================================================
# AUTENTICAÇÃO
# =============================================================================
 
def verify_password(stored_password, provided_password):
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
            return redirect(url_for('dashboard'))
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
    ano_atual_str = hoje.strftime('%Y') # Isolado em variável para não repetir código
 
    processar_regras_de_status_temporais(db)
    
    count_ativos = db.execute("SELECT COUNT(*) FROM funcionarios WHERE status='Ativo'").fetchone()[0]
    
    count_admitidos = db.execute(
        "SELECT COUNT(*) FROM funcionarios WHERE strftime('%m',data_admissao)=? AND strftime('%Y',data_admissao)=?",
        (mes_atual_str, ano_atual_str)).fetchone()[0]
        
    count_desligados = db.execute(
        "SELECT COUNT(*) FROM funcionarios WHERE status='Desligado' AND strftime('%m',data_desligamento)=? AND strftime('%Y',data_desligamento)=?",
        (mes_atual_str, ano_atual_str)).fetchone()[0]
 
    count_ocorrencias = db.execute(
        "SELECT COUNT(*) FROM ocorrencias WHERE strftime('%m', data_inicio)=? AND strftime('%Y', data_inicio)=?",
        (mes_atual_str, ano_atual_str)).fetchone()[0]

    funcionarios_ativos = db.execute(
        "SELECT id, nome, data_nascimento, data_admissao FROM funcionarios WHERE status='Ativo'"
    ).fetchall()
 
    # 1. Busca os dados dos aniversariantes do banco
    query = """
        SELECT id, nome, data_nascimento, 
            strftime('%d', data_nascimento) as dia
        FROM funcionarios 
        WHERE status = 'Ativo' 
        AND strftime('%m', data_nascimento) = ?
        ORDER BY CAST(dia AS INTEGER) ASC
    """
    resultados = db.execute(query, (mes_atual_str,)).fetchall()

    # 2. Processa os aniversariantes para o formato do HTML
    aniversariantes = []
    for row in resultados:
        func = dict(row)
        func['data_completa'] = f"{func['dia'].zfill(2)}/{mes_atual_str}"
        aniversariantes.append(func)
 
    # Alerta de vencimento de férias
    alerta_vencimento = []
    for f in funcionarios_ativos:
        try:
            if f['data_admissao']:
                adm = datetime.strptime(para_iso(f['data_admissao']), '%Y-%m-%d').date()
                if (hoje - adm).days >= 320:
                    tem_ferias = db.execute(
                        "SELECT id FROM ferias WHERE funcionario_id=? AND status_ferias='Agendada'",
                        (f['id'],)).fetchone()
                    if not tem_ferias:
                        alerta_vencimento.append(f)
        except Exception:
            continue
 
    # Saídas próxima semana
    proxima_semana = (hoje + timedelta(days=7)).strftime('%Y-%m-%d')
    # 1. Busca do banco
    resultados_saidas = db.execute('''
        SELECT f.nome, fe.data_inicio FROM ferias fe
        JOIN funcionarios f ON fe.funcionario_id = f.id
        WHERE f.status='Ativo' AND fe.data_inicio BETWEEN date('now') AND ?
    ''', (proxima_semana,)).fetchall()
    # 2. Processa para o formato DD/MM
    saidas_breve = []
    for row in resultados_saidas:
        item = dict(row)
        # Converte a string YYYY-MM-DD para objeto datetime e formata como DD/MM
        if item['data_inicio']:
            dt = datetime.strptime(item['data_inicio'], '%Y-%m-%d')
            item['data_formatada'] = dt.strftime('%d/%m')
        saidas_breve.append(item)
 
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
            print(f"Erro no alerta de experiência para o ID {f.get('id')}: {e}")
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
    funcionarios = db.execute("""
        SELECT nome, cargo, filial, data_nascimento FROM funcionarios
        WHERE strftime('%m', data_nascimento) = ? AND status = 'Ativo'
        ORDER BY strftime('%d', data_nascimento) ASC
    """, (mes_atual_str,)).fetchall()
    db.close()
 
    output = BytesIO()
    output.write(b'\xef\xbb\xbf')
    stream = TextIOWrapper(output, encoding='utf-8', newline='')
    writer = csv.writer(stream, delimiter=';', quoting=csv.QUOTE_MINIMAL)
    writer.writerow(['Nome', 'Cargo', 'Filial', 'Data de Aniversário'])
    for f in funcionarios:
        writer.writerow([f['nome'], f['cargo'], f['filial'],
                         formatar_data_br(f['data_nascimento'])])
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
 
        # ── Validações do backend (segunda barreira após o JS) ──────────────
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
        # ────────────────────────────────────────────────────────────────────
 
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
        # Se o usuário digitou algo, vamos buscar
        # Lógica: Se tem dígitos, tenta buscar por CPF ou Nome. Se não tem, busca só por Nome.
        if termo_limpo:
            # Tem números, pode ser CPF ou Nome (ex: "Maria 123")
            query = """SELECT id,nome,cpf,cargo,data_admissao,status 
                       FROM funcionarios 
                       WHERE status='Ativo' AND (nome LIKE ? OR cpf LIKE ?) 
                       ORDER BY nome"""
            params = (f"%{termo_busca}%", f"%{termo_limpo}%")
        else:
            # Só tem texto, busca apenas por Nome
            query = """SELECT id,nome,cpf,cargo,data_admissao,status 
                       FROM funcionarios 
                       WHERE status='Ativo' AND nome LIKE ? 
                       ORDER BY nome"""
            params = (f"%{termo_busca}%",)
            
        funcionarios = db.execute(query, params).fetchall()
        
        # Feedback se nada for encontrado
        if not funcionarios:
            flash(f"Nenhum colaborador encontrado para '{termo_busca}'.", "info")
            
    else:
        # Lista tudo se não houver busca
        funcionarios = db.execute(
            "SELECT id,nome,cpf,cargo,data_admissao,status FROM funcionarios WHERE status='Ativo' ORDER BY nome"
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
    termo_limpo = re.sub(r'\D', '', termo_busca)
    
    db = get_db_connection()
    funcionarios = []
    
    if termo_busca:
                
        query = """SELECT id,nome,cpf,cargo,data_admissao,data_desligamento,tipo_desligamento,motivo_desligamento 
                   FROM funcionarios 
                   WHERE status='Desligado' AND (nome LIKE ? OR cpf LIKE ?) 
                   ORDER BY data_desligamento DESC"""
        params = (f"%{termo_busca}%", f"%{termo_busca}%") 
        
        funcionarios = db.execute(query, params).fetchall()
        
        if not funcionarios:
            flash(f"Nenhum registro encontrado para '{termo_busca}'.", "warning")
            
    else:
        funcionarios = db.execute(
            "SELECT id,nome,cpf,cargo,data_admissao,data_desligamento,tipo_desligamento,motivo_desligamento FROM funcionarios WHERE status='Desligado' ORDER BY data_desligamento DESC"
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
    
    # 1. TRAVA DE SEGURANÇA: CPF tem 11 dígitos. 
    # Se digitar menos que 3-4 dígitos, nem tente buscar, pois pode pegar IDs.
    if len(termo) < 3:
        flash("Digite mais dígitos para realizar a busca (evite conflito com IDs).", "warning")
        return redirect(url_for('dashboard'))

    db = get_db_connection()
    db.row_factory = sqlite3.Row
    
    # Esta query agora olha EXCLUSIVAMENTE para a coluna CPF.
    query = """SELECT * FROM funcionarios 
               WHERE REPLACE(REPLACE(cpf,'.',''),'-','') LIKE ?"""
    
    # Buscamos apenas pelo que começa com os dígitos digitados
    funcionarios = db.execute(query, (f"{termo}%",)).fetchall()
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
        # Se encontrou vários, manda para a lista
        flash(f'{total} resultados encontrados. Refine o CPF.', 'info')
        return redirect(url_for('listar_funcionarios', busca=termo))
 
@app.route('/editar_funcionario/<int:id>', methods=['GET', 'POST'])
@requer_perfil([1, 2])
def editar_funcionario(id):
    
    db = get_db_connection()
    db.row_factory = sqlite3.Row
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
        # 1. Campos Sensíveis: Ignoramos o formulário e mantemos os dados originais do banco
        cpf_final = funcionario['cpf']
        nascimento_final = funcionario['data_nascimento']
        admissao_final = funcionario['data_admissao']
        login_extranet_final = funcionario['login_extranet']

        # 2. Campos Editáveis: Coletamos do formulário
        status_novo = request.form.get('status')
        email_novo = request.form.get('email', '').strip()

        # Validação básica de campos editáveis
        if email_novo and not validar_email(email_novo):
            flash('E-mail com formato inválido.', 'danger')
            return redirect(url_for('editar_funcionario', id=id))

        campos_formulario = {
            'cpf': cpf_final, # Protegido
            'nome': request.form.get('nome', '').strip(),
            'data_nascimento': nascimento_final, # Protegido
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
            'login_extranet': login_extranet_final, # Protegido
            'data_admissao': admissao_final, # Protegido
            'status': status_novo,
            'optou_convenio': request.form.get('optou_convenio'),
            'totalpass': request.form.get('totalpass'),
            'vt': request.form.get('vt'),
            'data_desligamento': para_iso(request.form.get('data_desligamento', '')) if status_novo == 'Desligado' else funcionario['data_desligamento'],
            'tipo_desligamento': request.form.get('tipo_desligamento') if status_novo == 'Desligado' else funcionario['tipo_desligamento'],
            'motivo_desligamento': request.form.get('motivo_desligamento') if status_novo == 'Desligado' else funcionario['motivo_desligamento']
        }

        # Tratamento de salário
        salario_raw = request.form.get('salario')
        campos_formulario['salario'] = float(str(salario_raw).replace('.', '').replace(',', '.')) if salario_raw else funcionario['salario']

        # Execução da atualização com auditoria
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
    funcionario = db.execute(
        "SELECT id, status FROM funcionarios WHERE REPLACE(REPLACE(cpf,'.',''),'-','') = ?",
        (cpf,)).fetchone()
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
    db.row_factory = sqlite3.Row
    funcionario = None
    cpf_buscado = ""
    periodo_sugerido_inicio = ""
    periodo_sugerido_fim = ""
    pode_agendar = True
    pode_editar = False
    motivo_trava = ""
    ferias_existentes = None
    
    # DETECÇÃO DE PERFIL: Verifica se o usuário logado é Administrador (ID 1)
    is_admin = (session.get('perfil') == 1)
 
    if id is not None:
        # ALTERAÇÃO 1: Adicionado o campo 'filial' (Loja) no SELECT por ID
        funcionario = db.execute(
            'SELECT id, nome, cpf, data_admissao, filial FROM funcionarios WHERE id = ?', (id,)).fetchone()
        if funcionario:
            cpf_buscado = funcionario['cpf']
 
    if request.method == 'POST' and 'buscar_cpf' in request.form:
        cpf_buscado = re.sub(r'\D', '', request.form['cpf'].strip())
        # ALTERAÇÃO 2: Adicionado o campo 'filial' (Loja) no SELECT por CPF
        funcionario = db.execute(
            "SELECT id, nome, cpf, data_admissao, status, filial FROM funcionarios WHERE REPLACE(REPLACE(cpf,'.',''),'-','')=? AND status='Ativo'", 
            (cpf_buscado,)).fetchone()
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
 
        ferias_existentes = db.execute('''
            SELECT * FROM ferias WHERE funcionario_id=? AND status_ferias='Agendada'
            AND (strftime('%Y', data_inicio)=? OR data_inicio LIKE ?) LIMIT 1
        ''', (funcionario['id'], str(ano_atual), f"%{ano_atual}%")).fetchone()
 
        if ferias_existentes:
            pode_agendar = False
            try:
                dt_inicio_ferias = datetime.strptime(
                    para_iso(ferias_existentes['data_inicio']), '%Y-%m-%d').date()
            except Exception:
                dt_inicio_ferias = data_atual
            dias_restantes = (dt_inicio_ferias - data_atual).days
            
            # ALTERAÇÃO 3: Controle da trava dos 30 dias com Bypass de Administrador
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
        action_type     = request.form.get('action_type', 'NEW') # Captura se é NEW, UPDATE ou CANCEL
        agora_br        = get_horario_brasilia().strftime('%d/%m/%Y %H:%M:%S')
 
        # BLINDAGEM DE BACK-END: Impede que operadores enviem requisições forçadas com prazo < 30 dias
        if action_type in ['UPDATE', 'CANCEL'] and not pode_editar and ferias_existentes:
            flash('Ação bloqueada! Prazo inferior a 30 dias exige perfil de Administrador.', 'danger')
            return redirect(url_for('lancar_ferias_busca', id=funcionario_id))
 
        try:
            with db:
                # ALTERAÇÃO 4: Fluxo de Cancelamento de Férias (Muda status e audita)
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
 
                # Fluxo de processamento de datas comum a NEW e UPDATE
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
            import traceback
            print("====== RASTRO DO ERRO REAL ======")
            traceback.print_exc() # Isto vai forçar o erro a aparecer no terminal
            print("=================================")
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
    funcionarios = db.execute(
        "SELECT nome, data_admissao, status FROM funcionarios WHERE status='Ativo'").fetchall()
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
                'alerta':          alerta,          # novo
                'mensagem_status': mensagem_status, # novo
            })
        except Exception as e:
            print(f"Erro ao processar {f['nome']}: {e}")
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
                    VALUES(?,?,?,?,?,?,?,datetime('now','localtime'))""",
                    (funcionario_id, tipo, data_inicio_str, data_fim_str, quantidade_dias, cid, observacao_usuario))
 
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
    
    # 1. Contagem total
    query_count = "SELECT COUNT(*) FROM historico_movimentacoes h LEFT JOIN funcionarios f ON h.funcionario_id = f.id WHERE 1=1"
    params = []
    if termo:
        query_count += " AND (f.nome LIKE ? OR h.observacao LIKE ?)"
        params.extend([f'%{termo}%', f'%{termo}%'])
        
    total = db.execute(query_count, params).fetchone()[0]
    total_paginas = max(1, (total + POR_PAGINA - 1) // POR_PAGINA)
    offset = (pagina_atual - 1) * POR_PAGINA

    # 2. Busca de dados
    query_logs = '''
        SELECT h.data_evento, u.username, f.nome as funcionario,
               h.tipo_movimentacao, h.observacao, h.valor_antigo, h.valor_novo
        FROM historico_movimentacoes h
        JOIN usuarios u ON h.usuario_id = u.id
        LEFT JOIN funcionarios f ON h.funcionario_id = f.id
        WHERE 1=1
    '''
    
    if termo:
        query_logs += " AND (f.nome LIKE ? OR h.observacao LIKE ?)"
    
    query_logs += " ORDER BY h.id DESC LIMIT ? OFFSET ?"
    
    # Executa a query de busca
    params.extend([POR_PAGINA, offset])
    raw_logs = db.execute(query_logs, params).fetchall()
    db.close() # FECHE APENAS UMA VEZ

    # 3. Transformação dos dados com proteção contra erros
    logs = []
    for row in raw_logs:
        log = dict(row)
        data_str = log.get('data_evento')
        
        if data_str:
            try:
                dt_obj = datetime.strptime(data_str, '%Y-%m-%d %H:%M:%S')
                log['data_evento'] = dt_obj.strftime('%d/%m/%Y %H:%M:%S')
            except ValueError:
                pass 
        
        logs.append(log)

    return render_template('auditoria.html', 
                           logs=logs, 
                           pagina_atual=pagina_atual, 
                           total_paginas=total_paginas,
                           busca=termo)
 
if __name__ == '__main__':
    app.run(debug=True)