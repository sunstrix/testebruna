-- 1. TABELA DE PERFIS
CREATE TABLE IF NOT EXISTS perfis (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL UNIQUE
);

-- 2. TABELA DE USUÁRIOS (Acesso ao Sistema)
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    senha TEXT NOT NULL,
    perfil_id INTEGER,
    FOREIGN KEY(perfil_id) REFERENCES perfis(id)
);

-- 3. TABELA DE FUNCIONÁRIOS (Dados Cadastrais e Profissionais)
CREATE TABLE IF NOT EXISTS funcionarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT, -- Use sempre ID numérico como PK
    cpf TEXT UNIQUE NOT NULL,             -- O CPF continua único para evitar duplicados
    nome TEXT NOT NULL,
    data_nascimento TEXT, -- Formato: DD-MM-YYYY
    estado_civil TEXT,
    telefone TEXT,
    email TEXT,
    sexo TEXT, -- Feminino, Masculino, Não-Binário, Outro
    raca TEXT, -- Branco, Amarelo, Indígena, Pardo, Preto
    escolaridade TEXT, -- Ensino Médio, Ensino Superior, Pós Graduação
    -- Dados Bancários
    banco TEXT,
    agencia TEXT,
    conta TEXT,
    modalidade_conta TEXT, -- Conta Corrente, Conta Poupança, Conta Salário
    -- Endereço
    endereco_rua TEXT,
    endereco_num TEXT,
    endereco_bairro TEXT,
    endereco_cidade TEXT,
    endereco_estado TEXT,
    endereco_cep TEXT,
    -- Benefícios
    optou_convenio TEXT,
    totalpass TEXT,
    vt TEXT,
    -- Profissional
    salario REAL,
    cargo TEXT,
	nivel TEXT,
	area TEXT,
    filial TEXT,
    gestor TEXT,
    login_extranet TEXT,
    data_admissao TEXT, -- Formato: YYYY-MM-DD
    -- Status e Desligamento
    status TEXT DEFAULT 'Ativo', -- 'Ativo', 'Férias', 'Afastado', 'Desligado'
    data_desligamento TEXT,
    tipo_desligamento TEXT, -- 'Pedido', 'Dispensa s/ Justa Causa', 'Dispensa c/ Justa Causa', 'Término Experiência', etc.
    motivo_desligamento TEXT,
    -- Documentos (Caminhos de Arquivo)
    caminho_documento_civil TEXT,
    caminho_diploma TEXT,
    observacoes TEXT
);

-- 4. TABELA DE FÉRIAS (Controle e Abono)
CREATE TABLE IF NOT EXISTS ferias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    funcionario_id INTEGER,
    periodo_aquisitivo_inicio TEXT,
    periodo_aquisitivo_fim TEXT,
    data_inicio TEXT,
    data_fim TEXT,
    abono_pecuniario TEXT DEFAULT 'Não', -- Se 'Sim', vendeu 10 dias
    status_ferias TEXT, -- 'Agendada', 'Em Gozo', 'Concluída'
    FOREIGN KEY(funcionario_id) REFERENCES funcionarios(id)
);

-- 5. TABELA DE LEMBRETES (Alertas de Experiência e Outros)
CREATE TABLE IF NOT EXISTS lembretes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    funcionario_id INTEGER,
    titulo TEXT, -- 'Vencimento Tempo de Experiência', 'Aniversário', lembrar de deixar o vencimento como lembrete 
	-- apenas pelo prazo de 1 semana antes e depois.
    descricao TEXT,
    data_alerta TEXT,
    status TEXT DEFAULT 'Pendente',
    FOREIGN KEY(funcionario_id) REFERENCES funcionarios(id)
);

-- 6. TABELA DE HISTÓRICO (Onde o Auditor trabalha)
CREATE TABLE IF NOT EXISTS historico_movimentacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    funcionario_id INTEGER,
    usuario_id INTEGER,
    data_evento TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tipo_movimentacao TEXT, 
    valor_antigo TEXT,
    valor_novo TEXT,
    observacao TEXT, -- Recomendo fortemente manter este campo
    FOREIGN KEY(funcionario_id) REFERENCES funcionarios(id),
    FOREIGN KEY(usuario_id) REFERENCES usuarios(id)
);

CREATE TABLE ocorrencias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    funcionario_id INTEGER NOT NULL,
    tipo TEXT CHECK(tipo IN ('FALTA_JUSTIFICADA', 'FALTA_INJUSTIFICADA', 'ATESTADO_MEDICO', 'AFASTAMENTO', 'DECLARAÇÃO', 'ACOMPANHAMENTO')),
    data_inicio DATE NOT NULL,
    data_fim DATE NOT NULL, 
    quantidade_dias INTEGER NOT NULL, -- Ficará 0 se for uma ocorrência de apenas horas
    quantidade_horas INTEGER NULL,    -- Campo novo: preenchido apenas se for DECLARAÇÃO ou abono parcial
    cid TEXT NULL, 
    observacao TEXT,
    data_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    caminho_documento TEXT NULL,      -- Campo novo: armazena o nome criptográfico do arquivo no servidor
    FOREIGN KEY (funcionario_id) REFERENCES funcionarios(id) ON DELETE CASCADE
);

-- Este TRIGGER garante que, se alguém tentar inserir uma data manual no 
-- histórico de movimentações, o banco ignore e force o horário real do servidor.
CREATE TRIGGER IF NOT EXISTS trg_forcar_data_atual
AFTER INSERT ON historico_movimentacoes
BEGIN
    UPDATE historico_movimentacoes 
    SET data_evento = CURRENT_TIMESTAMP 
    WHERE id = NEW.id;
END;

-- 1. Garante que os perfis existam

INSERT OR IGNORE INTO perfis (id, nome) VALUES (1, 'Admin'), (2, 'Operador'), (3, 'Auditor');