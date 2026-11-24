-- Banco relacional do sistema de agiotagem (fictício, trabalho acadêmico).
-- Guarda o dinheiro e os vínculos obrigatórios: funcionários, clientes, empréstimos e parcelas.

CREATE TABLE funcionarios (
    id            SERIAL PRIMARY KEY,
    nome          VARCHAR(100) NOT NULL,
    papel         VARCHAR(10)  NOT NULL CHECK (papel IN ('ADMIN', 'COBRADOR')),
    telefone      VARCHAR(20),
    comissao_pct  NUMERIC(5,2) NOT NULL DEFAULT 0,
    ativo         BOOLEAN      NOT NULL DEFAULT TRUE
);

CREATE TABLE clientes (
    id           SERIAL PRIMARY KEY,
    nome         VARCHAR(100) NOT NULL,
    cpf          VARCHAR(14)  NOT NULL UNIQUE,
    telefone     VARCHAR(20)  NOT NULL,
    endereco     VARCHAR(150) NOT NULL,
    -- RESTRICT: não deixa apagar um cobrador que ainda tem clientes
    cobrador_id  INT NOT NULL REFERENCES funcionarios(id) ON DELETE RESTRICT
);

CREATE TABLE emprestimos (
    id               SERIAL PRIMARY KEY,
    cliente_id       INT NOT NULL REFERENCES clientes(id) ON DELETE RESTRICT,
    aprovado_por     INT NOT NULL REFERENCES funcionarios(id),
    solicitacao_id   VARCHAR(24),   -- _id do documento no MongoDB (ligação entre os bancos)
    valor_principal  NUMERIC(10,2) NOT NULL CHECK (valor_principal > 0),
    juros_mes        NUMERIC(5,2)  NOT NULL CHECK (juros_mes >= 0),
    qtd_parcelas     INT NOT NULL CHECK (qtd_parcelas BETWEEN 1 AND 24),
    data_emprestimo  DATE NOT NULL DEFAULT CURRENT_DATE,
    status           VARCHAR(10) NOT NULL DEFAULT 'ATIVO' CHECK (status IN ('ATIVO', 'QUITADO'))
);

-- Parcela atrasada não é um status salvo:
-- é status = 'PENDENTE' AND vencimento < CURRENT_DATE, calculado na consulta.
CREATE TABLE parcelas (
    id             SERIAL PRIMARY KEY,
    -- CASCADE: cancelar (apagar) um empréstimo apaga as parcelas junto
    emprestimo_id  INT NOT NULL REFERENCES emprestimos(id) ON DELETE CASCADE,
    numero         INT NOT NULL,
    vencimento     DATE NOT NULL,
    valor          NUMERIC(10,2) NOT NULL,
    status         VARCHAR(10) NOT NULL DEFAULT 'PENDENTE' CHECK (status IN ('PENDENTE', 'PAGA')),
    pago_em        TIMESTAMP,
    recebido_por   INT REFERENCES funcionarios(id),
    UNIQUE (emprestimo_id, numero)
);
