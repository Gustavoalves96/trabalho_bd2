# Modelo ER (PostgreSQL)

```mermaid
erDiagram
    FUNCIONARIOS ||--o{ CLIENTES : "cobra (cobrador_id, RESTRICT)"
    FUNCIONARIOS ||--o{ EMPRESTIMOS : "aprova (aprovado_por)"
    FUNCIONARIOS |o--o{ PARCELAS : "recebe (recebido_por)"
    CLIENTES ||--o{ EMPRESTIMOS : "toma (cliente_id, RESTRICT)"
    EMPRESTIMOS ||--|{ PARCELAS : "tem (emprestimo_id, CASCADE)"

    FUNCIONARIOS {
        int id PK
        varchar nome
        varchar papel "ADMIN ou COBRADOR"
        varchar telefone
        numeric comissao_pct
        boolean ativo
    }
    CLIENTES {
        int id PK
        varchar nome
        varchar cpf UK
        varchar telefone
        varchar endereco
        int cobrador_id FK
    }
    EMPRESTIMOS {
        int id PK
        int cliente_id FK
        int aprovado_por FK
        varchar solicitacao_id "_id da solicitação no MongoDB"
        numeric valor_principal
        numeric juros_mes
        int qtd_parcelas
        date data_emprestimo
        varchar status "ATIVO ou QUITADO"
    }
    PARCELAS {
        int id PK
        int emprestimo_id FK
        int numero
        date vencimento
        numeric valor
        varchar status "PENDENTE ou PAGA"
        timestamp pago_em
        int recebido_por FK
    }
```

Ligações com o MongoDB (não são FKs, são referências guardadas pela aplicação):

- `emprestimos.solicitacao_id` guarda o `_id` do documento em `solicitacoes`.
- `solicitacoes.emprestimo_id` guarda o `id` do empréstimo criado na aprovação.
- `ocorrencias_cobranca` guarda `emprestimo_id`, `cliente_id` e `cobrador_id` do PostgreSQL.
