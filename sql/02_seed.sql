-- Dados de exemplo. A ordem dos INSERTs importa: os ids do SERIAL ficam 1, 2, 3...
-- e o seed do MongoDB (mongo/setup.js) usa esses ids.
-- As datas são relativas a CURRENT_DATE para sempre existirem parcelas atrasadas no dia da apresentação.

-- funcionarios: 1 = admin, 2..4 = cobradores
INSERT INTO funcionarios (nome, papel, telefone, comissao_pct) VALUES
    ('Seu Madruga',    'ADMIN',    '(53) 99000-0001', 0),
    ('Jaiminho',       'COBRADOR', '(53) 99000-0002', 10),
    ('Nhonho',         'COBRADOR', '(53) 99000-0003', 15),
    ('Professor Girafales', 'COBRADOR', '(53) 99000-0004', 12);

-- clientes 1..4
INSERT INTO clientes (nome, cpf, telefone, endereco, cobrador_id) VALUES
    ('Carlos Pereira',  '111.222.333-44', '(53) 98111-2233', 'Rua XV de Novembro, 500, Centro, Pelotas', 2),
    ('Ana Souza',       '222.333.444-55', '(53) 98222-3344', 'Av. Bento Goncalves, 1200, Centro, Pelotas', 3),
    ('Bruno Lima',      '333.444.555-66', '(53) 98333-4455', 'Rua Gomes Carneiro, 80, Porto, Pelotas', 2),
    ('Fernanda Rocha',  '444.555.666-77', '(53) 98444-5566', 'Av. Dom Joaquim, 300, Tres Vendas, Pelotas', 4);

-- emprestimos 1..4 (os dois primeiros vieram de solicitações que estão no MongoDB)
INSERT INTO emprestimos (cliente_id, aprovado_por, solicitacao_id, valor_principal, juros_mes, qtd_parcelas, data_emprestimo) VALUES
    (1, 1, '650000000000000000000001', 1000, 20, 5, CURRENT_DATE - INTERVAL '100 days'),
    (2, 1, '650000000000000000000002', 2000, 15, 4, CURRENT_DATE - INTERVAL '95 days'),
    (3, 1, NULL,                        500, 10, 3, CURRENT_DATE - INTERVAL '20 days'),
    (4, 1, NULL,                       3000, 20, 6, CURRENT_DATE - INTERVAL '45 days');

-- Empréstimo 1: 1000 * (1 + 0.20 * 5) = 2000 -> 5 x 400. Pagou 2, a 3ª está atrasada.
INSERT INTO parcelas (emprestimo_id, numero, vencimento, valor, status, pago_em, recebido_por) VALUES
    (1, 1, CURRENT_DATE - INTERVAL '70 days', 400, 'PAGA', NOW() - INTERVAL '70 days', 2),
    (1, 2, CURRENT_DATE - INTERVAL '40 days', 400, 'PAGA', NOW(), 2),
    (1, 3, CURRENT_DATE - INTERVAL '10 days', 400, 'PENDENTE', NULL, NULL),
    (1, 4, CURRENT_DATE + INTERVAL '20 days', 400, 'PENDENTE', NULL, NULL),
    (1, 5, CURRENT_DATE + INTERVAL '50 days', 400, 'PENDENTE', NULL, NULL);

-- Empréstimo 2: 2000 * (1 + 0.15 * 4) = 3200 -> 4 x 800. Pagou 1, a 2ª e a 3ª estão atrasadas.
INSERT INTO parcelas (emprestimo_id, numero, vencimento, valor, status, pago_em, recebido_por) VALUES
    (2, 1, CURRENT_DATE - INTERVAL '65 days', 800, 'PAGA', NOW(), 3),
    (2, 2, CURRENT_DATE - INTERVAL '35 days', 800, 'PENDENTE', NULL, NULL),
    (2, 3, CURRENT_DATE - INTERVAL '5 days',  800, 'PENDENTE', NULL, NULL),
    (2, 4, CURRENT_DATE + INTERVAL '25 days', 800, 'PENDENTE', NULL, NULL);

-- Empréstimo 3: 500 * (1 + 0.10 * 3) = 650 -> 216.67 + 216.67 + 216.66 (centavos na última). Nada vencido.
INSERT INTO parcelas (emprestimo_id, numero, vencimento, valor) VALUES
    (3, 1, CURRENT_DATE + INTERVAL '10 days', 216.67),
    (3, 2, CURRENT_DATE + INTERVAL '40 days', 216.67),
    (3, 3, CURRENT_DATE + INTERVAL '70 days', 216.66);

-- Empréstimo 4: 3000 * (1 + 0.20 * 6) = 6600 -> 6 x 1100. Pagou a 1ª.
INSERT INTO parcelas (emprestimo_id, numero, vencimento, valor, status, pago_em, recebido_por) VALUES
    (4, 1, CURRENT_DATE - INTERVAL '15 days',  1100, 'PAGA', NOW(), 4),
    (4, 2, CURRENT_DATE + INTERVAL '15 days',  1100, 'PENDENTE', NULL, NULL),
    (4, 3, CURRENT_DATE + INTERVAL '45 days',  1100, 'PENDENTE', NULL, NULL),
    (4, 4, CURRENT_DATE + INTERVAL '75 days',  1100, 'PENDENTE', NULL, NULL),
    (4, 5, CURRENT_DATE + INTERVAL '105 days', 1100, 'PENDENTE', NULL, NULL),
    (4, 6, CURRENT_DATE + INTERVAL '135 days', 1100, 'PENDENTE', NULL, NULL);
