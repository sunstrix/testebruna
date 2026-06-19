-- =============================================================================
-- DADOS DE TESTE LOTE 3 — CP FANI | Essência RH
-- Foco: Junho/2026 — Aniversariantes, Admissões e Desligamentos do mês
-- Execute APÓS os lotes 1 e 2
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. FUNCIONÁRIOS
-- -----------------------------------------------------------------------------

INSERT INTO funcionarios (
    cpf, nome, data_nascimento, estado_civil, sexo, raca, escolaridade,
    telefone, email, banco, agencia, conta, modalidade_conta,
    endereco_cep, endereco_rua, endereco_num, endereco_bairro, endereco_cidade, endereco_estado,
    optou_convenio, totalpass, vt,
    salario, cargo, nivel, area, filial, gestor, login_extranet,
    data_admissao, status
) VALUES

-- ── ANIVERSARIANTES DE JUNHO ─────────────────────────────────────────────────

-- Aniversário 01/06
(
    '10020030041', 'Aline Cristina Borges',
    '1993-06-01',
    'Solteiro(a)', 'Feminino', 'Pardo', 'Ensino Superior Completo',
    '11991001001', 'aline.borges@cpfani.com.br',
    'Itaú', '1234', '10001-1', 'Conta Corrente',
    '04038001', 'Rua Verbo Divino', '1488', 'Chácara Santo Antônio', 'São Paulo', 'SP',
    'Sim', 'Sim', 'Não',
    3400.00, 'Analista Administrativo', 'Pleno', 'Administrativo',
    '14120 - Arpel Matriz', 'Matheus Dias', 'aline.borges',
    date('now', '-1 year', '-3 months'), 'Ativo'
),

-- Aniversário 07/06
(
    '20030040052', 'Marcos Vinicius Alves',
    '1988-06-07',
    'Casado(a)', 'Masculino', 'Branco', 'Pós Graduação Completa',
    '11982002002', 'marcos.alves@cpfani.com.br',
    'Bradesco', '5678', '20002-2', 'Conta Corrente',
    '01452001', 'Rua Estados Unidos', '500', 'Jardins', 'São Paulo', 'SP',
    'Sim', 'Sim', 'Não',
    7200.00, 'Gerente de Vendas Internas', 'Gerente', 'Comercial',
    '4842 - Shopping Metrópole', 'Isabella Almeida', 'marcos.alves',
    date('now', '-3 years'), 'Ativo'
),

-- Aniversário 12/06
(
    '30040050063', 'Priscila Monteiro Duarte',
    '1996-06-12',
    'União Estável', 'Feminino', 'Preto', 'Ensino Superior Completo',
    '11973003003', 'priscila.duarte@cpfani.com.br',
    'Nubank', '0001', '30003-3', 'Conta Corrente',
    '04547001', 'Rua Pedroso Alvarenga', '300', 'Itaim Bibi', 'São Paulo', 'SP',
    'Sim', 'Não', 'Sim',
    4100.00, 'Analista de Recrutamento e Seleção', 'Pleno', 'Recursos Humanos',
    '14120 - Arpel Matriz', 'Fernanda Carvalho', 'priscila.duarte',
    date('now', '-2 years'), 'Ativo'
),

-- Aniversário 18/06
(
    '40050060074', 'Rodrigo Faria Lopes',
    '1990-06-18',
    'Casado(a)', 'Masculino', 'Amarelo', 'Ensino Superior Completo',
    '11964004004', 'rodrigo.lopes@cpfani.com.br',
    'Santander', '9012', '40004-4', 'Conta Corrente',
    '09521001', 'Avenida Nazaré', '1200', 'Ipiranga', 'São Paulo', 'SP',
    'Sim', 'Sim', 'Sim',
    5100.00, 'Supervisor(a) de Campo', 'Supervisor', 'Comercial',
    '6105 - Assaí Anchieta', 'Lay Coelho', 'rodrigo.lopes',
    date('now', '-4 years'), 'Ativo'
),

-- Aniversário 23/06
(
    '50060070085', 'Tatiana Sousa Freitas',
    '2000-06-23',
    'Solteiro(a)', 'Feminino', 'Pardo', 'Ensino Superior Incompleto',
    '11955005005', 'tatiana.freitas@cpfani.com.br',
    'Banco do Brasil', '3456', '50005-5', 'Conta Salário',
    '08220001', 'Rua Bresser', '900', 'Brás', 'São Paulo', 'SP',
    'Não', 'Não', 'Sim',
    2100.00, 'Assistente Administrativo', 'Assistente', 'Administrativo',
    '12605 - Coop', 'Luciana Cerpa', 'tatiana.freitas',
    date('now', '-10 months'), 'Ativo'
),

-- Aniversário 28/06
(
    '60070080096', 'Eduardo Peixoto Gama',
    '1984-06-28',
    'Divorciado(a)', 'Masculino', 'Branco', 'Pós Graduação Completa',
    '11946006006', 'eduardo.gama@cpfani.com.br',
    'Itaú', '7890', '60006-6', 'Conta Corrente',
    '01310100', 'Avenida Paulista', '800', 'Bela Vista', 'São Paulo', 'SP',
    'Sim', 'Sim', 'Não',
    9500.00, 'Gerente de Compras', 'Gerente', 'Suprimentos',
    '14120 - Arpel Matriz', 'Matheus Dias', 'eduardo.gama',
    date('now', '-5 years'), 'Ativo'
),

-- ── ADMITIDOS EM JUNHO/2026 ──────────────────────────────────────────────────

-- Admissão 02/06 — em experiência (fase 1)
(
    '70080090107', 'Leticia Nascimento Cruz',
    '2002-03-14',
    'Solteiro(a)', 'Feminino', 'Preto', 'Ensino Médio Completo',
    '11937007007', 'leticia.cruz@cpfani.com.br',
    'Nubank', '0001', '70007-7', 'Conta Corrente',
    '04038002', 'Rua Verbo Divino', '500', 'Chácara Santo Antônio', 'São Paulo', 'SP',
    'Não', 'Não', 'Sim',
    1650.00, 'Consultor(a) de Vendas', 'Assistente', 'Comercial',
    '12645 - Shopping Light', 'Josenilda Lopes', 'leticia.cruz',
    '2026-06-02', 'Ativo'
),

-- Admissão 09/06 — em experiência (fase 1)
(
    '80090100118', 'Gabriel Andrade Moreira',
    '1999-11-05',
    'Solteiro(a)', 'Masculino', 'Pardo', 'Ensino Superior Incompleto',
    '11928008008', 'gabriel.moreira@cpfani.com.br',
    'Bradesco', '2345', '80008-8', 'Conta Corrente',
    '05424001', 'Rua Teodoro Sampaio', '200', 'Pinheiros', 'São Paulo', 'SP',
    'Não', 'Sim', 'Sim',
    2300.00, 'Assistente de Suporte Computacional', 'Assistente', 'Tecnologia',
    '14120 - Arpel Matriz', 'Matheus Dias', 'gabriel.moreira',
    '2026-06-09', 'Ativo'
),

-- Admissão 16/06 — recém admitido
(
    '90100110129', 'Natalia Vieira Campos',
    '1997-08-22',
    'Casado(a)', 'Feminino', 'Branco', 'Ensino Superior Completo',
    '11919009009', 'natalia.campos@cpfani.com.br',
    'Santander', '6789', '90009-9', 'Conta Corrente',
    '04551001', 'Alameda Campinas', '300', 'Jardins', 'São Paulo', 'SP',
    'Sim', 'Sim', 'Não',
    4600.00, 'Analista Financeiro', 'Júnior', 'Financeiro',
    '14120 - Arpel Matriz', 'Nathalie Aron', 'natalia.campos',
    '2026-06-16', 'Ativo'
),

-- Admissão 23/06 — recém admitido
(
    '11100210131', 'Caio Drummond Neves',
    '2001-01-30',
    'Solteiro(a)', 'Masculino', 'Indígena', 'Ensino Médio Completo',
    '11910010010', 'caio.neves@cpfani.com.br',
    'Caixa Econômica', '0123', '11010-0', 'Conta Salário',
    '08460001', 'Rua Tuiuti', '400', 'Tatuapé', 'São Paulo', 'SP',
    'Não', 'Não', 'Sim',
    1650.00, 'Estoquista', 'Assistente', 'Logística',
    '23379 - Assaí Piraporinha', 'Rodrigo Jorge', 'caio.neves',
    '2026-06-23', 'Ativo'
),

-- ── DESLIGADOS EM JUNHO/2026 ─────────────────────────────────────────────────

-- Desligado 03/06 — Pedido de demissão
(
    '22110320142', 'Henrique Castro Pinto',
    '1991-07-17',
    'Solteiro(a)', 'Masculino', 'Branco', 'Ensino Superior Completo',
    '11901011011', 'henrique.pinto@cpfani.com.br',
    'Itaú', '4567', '22011-1', 'Conta Corrente',
    '01414001', 'Rua da Consolação', '1500', 'Consolação', 'São Paulo', 'SP',
    'Sim', 'Sim', 'Não',
    5600.00, 'Analista de Suporte Computacional', 'Pleno', 'Tecnologia',
    '14120 - Arpel Matriz', 'Matheus Dias', 'henrique.pinto',
    date('now', '-2 years'), 'Desligado'
),

-- Desligado 10/06 — Dispensa sem justa causa
(
    '33120430153', 'Claudia Mendonça Ramos',
    '1987-04-09',
    'Divorciado(a)', 'Feminino', 'Pardo', 'Ensino Superior Completo',
    '11892012012', 'claudia.ramos@cpfani.com.br',
    'Bradesco', '8901', '33012-2', 'Conta Corrente',
    '09310001', 'Rua Domingos de Morais', '800', 'Vila Mariana', 'São Paulo', 'SP',
    'Sim', 'Não', 'Sim',
    4200.00, 'Supervisor(a) Interno', 'Supervisor', 'Administrativo',
    '14353 - Arpel Filial', 'Rodrigo Jorge', 'claudia.ramos',
    date('now', '-3 years'), 'Desligado'
),

-- Desligado 20/06 — Término de Experiência
(
    '44130540164', 'Igor Santos Tavares',
    '2003-02-11',
    'Solteiro(a)', 'Masculino', 'Preto', 'Ensino Médio Completo',
    '11883013013', 'igor.tavares@cpfani.com.br',
    'Nubank', '0001', '44013-3', 'Conta Corrente',
    '08110002', 'Rua Javari', '600', 'Mooca', 'São Paulo', 'SP',
    'Não', 'Não', 'Sim',
    1650.00, 'Consultor(a) de Vendas', 'Assistente', 'Comercial',
    '21502 - Bem Barato', 'Joselita Arante', 'igor.tavares',
    date('now', '-95 days'), 'Desligado'
);


-- -----------------------------------------------------------------------------
-- 2. ATUALIZA DESLIGAMENTOS DE JUNHO
-- -----------------------------------------------------------------------------

UPDATE funcionarios SET
    data_desligamento = '2026-06-03',
    tipo_desligamento = 'Pedido',
    motivo_desligamento = 'Colaborador solicitou desligamento para empreender no ramo de tecnologia.'
WHERE cpf = '22110320142';

UPDATE funcionarios SET
    data_desligamento = '2026-06-10',
    tipo_desligamento = 'Dispensa s/ Justa Causa',
    motivo_desligamento = 'Redução de headcount por adequação orçamentária do segundo semestre.'
WHERE cpf = '33120430153';

UPDATE funcionarios SET
    data_desligamento = '2026-06-20',
    tipo_desligamento = 'Término Experiência',
    motivo_desligamento = 'Perfil não aderente à cultura e requisitos técnicos da função.'
WHERE cpf = '44130540164';


-- -----------------------------------------------------------------------------
-- 3. FÉRIAS — saída na próxima semana para prints do dashboard
-- -----------------------------------------------------------------------------

-- Aline (aniversariante 01/06) — férias saindo em 2 dias
INSERT INTO ferias (funcionario_id, periodo_aquisitivo_inicio, periodo_aquisitivo_fim, data_inicio, data_fim, abono_pecuniario, status_ferias)
SELECT id,
    date('now', '-1 year', '-3 months'),
    date('now', '-3 months', '-1 day'),
    date('now', '+2 days'),
    date('now', '+31 days'),
    'Não', 'Agendada'
FROM funcionarios WHERE cpf = '10020030041';

-- Rodrigo (aniversariante 18/06) — férias saindo em 6 dias
INSERT INTO ferias (funcionario_id, periodo_aquisitivo_inicio, periodo_aquisitivo_fim, data_inicio, data_fim, abono_pecuniario, status_ferias)
SELECT id,
    date('now', '-4 years'),
    date('now', '-3 years', '-1 day'),
    date('now', '+6 days'),
    date('now', '+35 days'),
    'Sim', 'Agendada'
FROM funcionarios WHERE cpf = '40050060074';
