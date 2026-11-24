"""Menu do agiota (admin): fila de solicitações, cobradores, clientes e empréstimos."""
import psycopg2
from pymongo.errors import PyMongoError, WriteError

import integracao
from conexao import escolher, ler_float, ler_int, mongo, mostrar_erro_validacao, pg


def listar_funcionarios(papel):
    with pg, pg.cursor() as cur:
        cur.execute("SELECT id, nome, telefone, comissao_pct FROM funcionarios WHERE papel = %s ORDER BY id",
                    (papel,))
        return cur.fetchall()


def menu():
    # sem senha: o admin escolhe quem é na lista
    admin = escolher(listar_funcionarios("ADMIN"), lambda f: f[1])
    if not admin:
        return
    admin_id = admin[0]
    opcoes = {
        "1": ("Ver fila de solicitações pendentes", ver_fila),
        "2": ("Aprovar solicitação", lambda: integracao.aprovar_solicitacao(admin_id)),
        "3": ("Recusar solicitação", recusar_solicitacao),
        "4": ("Listar cobradores", listar_cobradores),
        "5": ("Cadastrar cobrador", cadastrar_cobrador),
        "6": ("Editar cobrador", editar_cobrador),
        "7": ("Excluir cobrador", excluir_cobrador),
        "8": ("Listar clientes com o cobrador", listar_clientes),
        "9": ("Editar cliente (cobrador, telefone, endereço)", editar_cliente),
        "10": ("Listar empréstimos", listar_emprestimos),
        "11": ("Cancelar empréstimo", cancelar_emprestimo),
        "12": ("Ficha do devedor", integracao.ficha_devedor),
        "13": ("Relatório dos cobradores", integracao.relatorio_cobradores),
    }
    while True:
        print(f"\n--- AGIOTA ({admin[1]}) ---")
        for chave, (texto, _) in opcoes.items():
            print(f"{chave} - {texto}")
        print("0 - Voltar")
        opcao = input("Opção: ").strip()
        if opcao == "0":
            return
        if opcao in opcoes:
            try:
                opcoes[opcao][1]()
            except psycopg2.Error as e:
                print("Erro no PostgreSQL:", e)
            except PyMongoError as e:
                print("Erro no MongoDB:", e)


# ---------- Solicitações (MongoDB) ----------

def buscar_pendentes():
    # filtra por status e ordena por criado_em: usa o índice { status: 1, criado_em: 1 }
    return list(mongo.solicitacoes.find({"status": "PENDENTE"}).sort("criado_em", 1))


def descrever_solicitacao(s):
    return (f"{s['criado_em']:%d/%m/%Y} - {s['nome']} ({s['cpf']}) - "
            f"R$ {s['valor_solicitado']:.2f} em {s['parcelas_desejadas']}x - {len(s.get('garantias', []))} garantia(s)")


def ver_fila():
    pendentes = buscar_pendentes()
    if not pendentes:
        print("Fila vazia.")
    for i, s in enumerate(pendentes, start=1):
        print(f"{i} - {descrever_solicitacao(s)}")


def recusar_solicitacao():
    s = escolher(buscar_pendentes(), descrever_solicitacao)
    if not s:
        return
    motivo = input("Motivo da recusa: ").strip()
    try:
        mongo.solicitacoes.update_one({"_id": s["_id"]},
                                      {"$set": {"status": "RECUSADA", "motivo_recusa": motivo}})
        print("Solicitação recusada.")
    except WriteError as e:
        mostrar_erro_validacao(e)


# ---------- Cobradores (PostgreSQL, CRUD completo) ----------

def listar_cobradores():
    print(f"\n{'Id':<4}{'Nome':<25}{'Telefone':<18}{'Comissão':>8}")
    for id_, nome, telefone, comissao in listar_funcionarios("COBRADOR"):
        print(f"{id_:<4}{nome:<25}{telefone or '':<18}{comissao:>7}%")


def cadastrar_cobrador():
    nome = input("Nome: ").strip()
    telefone = input("Telefone: ").strip()
    comissao = ler_float("Comissão em %: ")
    with pg, pg.cursor() as cur:
        cur.execute("INSERT INTO funcionarios (nome, papel, telefone, comissao_pct) "
                    "VALUES (%s, 'COBRADOR', %s, %s) RETURNING id", (nome, telefone, comissao))
        print(f"Cobrador cadastrado com id {cur.fetchone()[0]}.")


def editar_cobrador():
    c = escolher(listar_funcionarios("COBRADOR"), lambda f: f"{f[1]} ({f[3]}%)")
    if not c:
        return
    nome = input(f"Nome (Enter mantém {c[1]}): ").strip() or c[1]
    telefone = input(f"Telefone (Enter mantém {c[2]}): ").strip() or c[2]
    comissao = ler_float(f"Comissão % (Enter mantém {c[3]}): ", c[3])
    with pg, pg.cursor() as cur:
        cur.execute("UPDATE funcionarios SET nome = %s, telefone = %s, comissao_pct = %s WHERE id = %s",
                    (nome, telefone, comissao, c[0]))
    print("Cobrador atualizado.")


def excluir_cobrador():
    c = escolher(listar_funcionarios("COBRADOR"), lambda f: f[1])
    if not c:
        return
    try:
        with pg, pg.cursor() as cur:
            cur.execute("DELETE FROM funcionarios WHERE id = %s", (c[0],))
        print("Cobrador excluído.")
    except psycopg2.errors.ForeignKeyViolation as e:
        # o ON DELETE RESTRICT de clientes.cobrador_id barra a exclusão
        if e.diag.constraint_name == "clientes_cobrador_id_fkey":
            print("Não é possível excluir: este cobrador ainda tem clientes. Transfira os clientes antes.")
        else:
            print("Não é possível excluir: este cobrador já recebeu pagamentos registrados.")


# ---------- Clientes e empréstimos (PostgreSQL) ----------

def buscar_clientes():
    with pg, pg.cursor() as cur:
        # JOIN para mostrar o nome do cobrador em vez do id
        cur.execute("""
            SELECT c.id, c.nome, c.cpf, c.telefone, c.endereco, f.nome AS cobrador
            FROM clientes c
            JOIN funcionarios f ON f.id = c.cobrador_id
            ORDER BY c.id
        """)
        return cur.fetchall()


def listar_clientes():
    print(f"\n{'Id':<4}{'Nome':<20}{'CPF':<16}{'Telefone':<18}{'Cobrador'}")
    for id_, nome, cpf, telefone, _, cobrador in buscar_clientes():
        print(f"{id_:<4}{nome:<20}{cpf:<16}{telefone:<18}{cobrador}")


def editar_cliente():
    c = escolher(buscar_clientes(), lambda x: f"{x[1]} - cobrador: {x[5]}")
    if not c:
        return
    telefone = input(f"Telefone (Enter mantém {c[3]}): ").strip() or c[3]
    endereco = input(f"Endereço (Enter mantém {c[4]}): ").strip() or c[4]
    print("Novo cobrador (0 mantém o atual):")
    novo = escolher(listar_funcionarios("COBRADOR"), lambda f: f[1])
    with pg, pg.cursor() as cur:
        if novo:
            cur.execute("UPDATE clientes SET telefone = %s, endereco = %s, cobrador_id = %s WHERE id = %s",
                        (telefone, endereco, novo[0], c[0]))
        else:
            cur.execute("UPDATE clientes SET telefone = %s, endereco = %s WHERE id = %s",
                        (telefone, endereco, c[0]))
    print("Cliente atualizado.")


def buscar_emprestimos():
    with pg, pg.cursor() as cur:
        cur.execute("""
            SELECT e.id, c.nome, e.valor_principal, e.status,
                   COUNT(p.id) FILTER (WHERE p.status = 'PAGA') AS pagas,
                   COUNT(p.id) AS total
            FROM emprestimos e
            JOIN clientes c ON c.id = e.cliente_id
            LEFT JOIN parcelas p ON p.emprestimo_id = e.id
            GROUP BY e.id, c.nome
            ORDER BY e.id
        """)
        return cur.fetchall()


def descrever_emprestimo(e):
    return f"nº {e[0]} - {e[1]} - R$ {e[2]:.2f} - {e[4]}/{e[5]} pagas - {e[3]}"


def listar_emprestimos():
    for e in buscar_emprestimos():
        print(descrever_emprestimo(e))


def cancelar_emprestimo():
    e = escolher(buscar_emprestimos(), descrever_emprestimo)
    if not e or input("Confirma o cancelamento? As parcelas serão apagadas (s/n): ").lower() != "s":
        return
    with pg, pg.cursor() as cur:
        # ON DELETE CASCADE: as parcelas deste empréstimo são apagadas junto
        cur.execute("DELETE FROM emprestimos WHERE id = %s", (e[0],))
    print("Empréstimo cancelado.")
