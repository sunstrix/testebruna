-- -----------------------------------------------------------------------------
-- 4. HISTÓRICO DE MOVIMENTAÇÕES — auditoria do lote 3
-- -----------------------------------------------------------------------------
INSERT INTO historico_movimentacoes (funcionario_id, usuario_id, tipo_movimentacao, valor_novo, observacao)
SELECT id, 1, 'CADASTRO', nome, 'Carga inicial de dados de teste' FROM funcionarios;

-- Cadastros de junho
INSERT INTO historico_movimentacoes (funcionario_id, usuario_id, tipo_movimentacao, valor_novo, observacao, data_evento)
SELECT f.id, 2, 'CADASTRO', f.nome, 'Novo colaborador inserido com ficha completa', '2026-06-02 09:15:00'
FROM funcionarios f WHERE f.cpf = '70080090107';

INSERT INTO historico_movimentacoes (funcionario_id, usuario_id, tipo_movimentacao, valor_novo, observacao, data_evento)
SELECT f.id, 2, 'CADASTRO', f.nome, 'Novo colaborador inserido com ficha completa', '2026-06-09 10:30:00'
FROM funcionarios f WHERE f.cpf = '80090100118';

INSERT INTO historico_movimentacoes (funcionario_id, usuario_id, tipo_movimentacao, valor_novo, observacao, data_evento)
SELECT f.id, 2, 'CADASTRO', f.nome, 'Novo colaborador inserido com ficha completa', '2026-06-16 08:45:00'
FROM funcionarios f WHERE f.cpf = '90100110129';

INSERT INTO historico_movimentacoes (funcionario_id, usuario_id, tipo_movimentacao, valor_novo, observacao, data_evento)
SELECT f.id, 2, 'CADASTRO', f.nome, 'Novo colaborador inserido com ficha completa', '2026-06-23 11:00:00'
FROM funcionarios f WHERE f.cpf = '11100210131';

-- Desligamentos de junho
INSERT INTO historico_movimentacoes (funcionario_id, usuario_id, tipo_movimentacao, valor_antigo, valor_novo, observacao, data_evento)
SELECT f.id, 1, 'DES', 'Ativo', 'Desligado',
    'Colaborador desligado. Tipo: Pedido. Motivo: Empreender no ramo de tecnologia.',
    '2026-06-03 14:00:00'
FROM funcionarios f WHERE f.cpf = '22110320142';

INSERT INTO historico_movimentacoes (funcionario_id, usuario_id, tipo_movimentacao, valor_antigo, valor_novo, observacao, data_evento)
SELECT f.id, 1, 'DES', 'Ativo', 'Desligado',
    'Colaboradora desligada. Tipo: Dispensa s/ Justa Causa. Motivo: Adequação orçamentária.',
    '2026-06-10 16:30:00'
FROM funcionarios f WHERE f.cpf = '33120430153';

INSERT INTO historico_movimentacoes (funcionario_id, usuario_id, tipo_movimentacao, valor_antigo, valor_novo, observacao, data_evento)
SELECT f.id, 1, 'DES', 'Ativo', 'Desligado',
    'Colaborador desligado. Tipo: Término Experiência. Perfil não aderente.',
    '2026-06-20 17:00:00'
FROM funcionarios f WHERE f.cpf = '44130540164';

-- Férias agendadas
INSERT INTO historico_movimentacoes (funcionario_id, usuario_id, tipo_movimentacao, valor_novo, observacao, data_evento)
SELECT f.id, 2, 'FÉRIAS',
    date('now', '+2 days') || ' a ' || date('now', '+31 days'),
    'Férias agendadas. Abono: Não',
    datetime('now', '-1 day', 'localtime')
FROM funcionarios f WHERE f.cpf = '10020030041';

INSERT INTO historico_movimentacoes (funcionario_id, usuario_id, tipo_movimentacao, valor_novo, observacao, data_evento)
SELECT f.id, 2, 'FÉRIAS',
    date('now', '+6 days') || ' a ' || date('now', '+35 days'),
    'Férias agendadas. Abono: Sim',
    datetime('now', '-2 days', 'localtime')
FROM funcionarios f WHERE f.cpf = '40050060074';

-- Edições diversas para enriquecer o log de auditoria
INSERT INTO historico_movimentacoes (funcionario_id, usuario_id, tipo_movimentacao, valor_antigo, valor_novo, observacao, data_evento)
SELECT f.id, 1, 'EDICAO', 'Itaim Bibi', 'Pinheiros', 'Alteração no campo [ENDERECO_BAIRRO]', '2026-06-05 10:00:00'
FROM funcionarios f WHERE f.cpf = '30040050063';

INSERT INTO historico_movimentacoes (funcionario_id, usuario_id, tipo_movimentacao, valor_antigo, valor_novo, observacao, data_evento)
SELECT f.id, 1, 'EDICAO', '4900.0', '5100.0', 'Alteração no campo [SALARIO]', '2026-06-11 09:30:00'
FROM funcionarios f WHERE f.cpf = '40050060074';

INSERT INTO historico_movimentacoes (funcionario_id, usuario_id, tipo_movimentacao, valor_antigo, valor_novo, observacao, data_evento)
SELECT f.id, 2, 'EDICAO', 'Banco do Brasil', 'Bradesco', 'Alteração no campo [BANCO]', '2026-06-14 14:15:00'
FROM funcionarios f WHERE f.cpf = '50060070085';
