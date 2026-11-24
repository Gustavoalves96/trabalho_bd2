"""Menu do cobrador: rota e pagamentos no PostgreSQL, diário de cobrança no MongoDB."""
from datetime import datetime

import psycopg2
from pymongo.errors import PyMongoError, WriteError

from admin import listar_funcionarios
from conexao import escolher, ler_float, mongo, mostrar_erro_validacao, pg


def menu():
    cobrador = escolher(listar_funcionarios("COBRADOR"), lambda f: f[1])
    if not cobrador:
        return
    cobrador_id = cobrador[0]
    while True:
        print(f"\n--- COBRADOR ({cobrador[1]}) ---")
        print("1 - Minha rota: parcelas atrasadas")
        print("2 - Registrar pagamento de parcela")
        print("3 - Registrar ocorrência")
        print("4 - Ver ocorrências de um empréstimo")
        print("5 - Apagar ocorrência registrada por engano")
        print("0 - Voltar")
        opcao = input("Opção: ").strip()
        try:
            if opcao == "1":
                minha_rota(cobrador_id)
            elif opcao == "2":
                registrar_pagamento(cobrador_id)
            elif opcao == "3":
                registrar_ocorrencia(cobrador_id)
            elif opcao == "4":
                ver_ocorrencias(cobrador_id)
            elif opcao == "5":
                apagar_ocorrencia(cobrador_id)
            elif opcao == "0":
                return
        except psycopg2.Error as e:
            print("Erro no PostgreSQL:", e)
        except PyMongoError as e:
            print("Erro no MongoDB:", e)


def minha_rota(cobrador_id):
    # "atrasada" não é salva no banco: é PENDENTE com vencimento no passado
    with pg, pg.cursor() as cur:
        cur.execute("""
            SELECT c.nome, c.telefone, c.endereco, e.id, p.numero, p.vencimento, p.valor,
                   CURRENT_DATE - p.vencimento AS dias_atraso
            FROM clientes c
            JOIN emprestimos e ON e.cliente_id = c.id
            JOIN parcelas p ON p.emprestimo_id = e.id
            WHERE c.cobrador_id = %s
              AND p.status = 'PENDENTE'
              AND p.vencimento < CURRENT_DATE
            ORDER BY p.vencimento
        """, (cobrador_id,))
        linhas = cur.fetchall()
    if not linhas:
        print("Nenhuma parcela atrasada. Dia tranquilo!")
    for nome, telefone, endereco, emp, numero, venc, valor, dias in linhas:
        print(f"\n{nome} - {telefone} - {endereco}")
        print(f"  Empréstimo {emp}, parcela {numero}: R$ {valor:.2f}, venceu {venc:%d/%m/%Y} ({dias} dias de atraso)")


def registrar_pagamento(cobrador_id):
    with pg, pg.cursor() as cur:
        cur.execute("""
            SELECT p.id, p.emprestimo_id, p.numero, p.vencimento, p.valor, c.nome
            FROM parcelas p
            JOIN emprestimos e ON e.id = p.emprestimo_id
            JOIN clientes c ON c.id = e.cliente_id
            WHERE c.cobrador_id = %s AND p.status = 'PENDENTE'
            ORDER BY p.vencimento
        """, (cobrador_id,))
        parcelas = cur.fetchall()
    p = escolher(parcelas, lambda x: f"{x[5]} - empréstimo {x[1]}, parcela {x[2]} - "
                                     f"R$ {x[4]:.2f} - vence {x[3]:%d/%m/%Y}")
    if not p:
        return
    # transação: marcar a parcela e quitar o empréstimo acontecem juntos ou nenhum acontece
    with pg, pg.cursor() as cur:
        cur.execute("UPDATE parcelas SET status = 'PAGA', pago_em = NOW(), recebido_por = %s WHERE id = %s",
                    (cobrador_id, p[0]))
        cur.execute("SELECT COUNT(*) FROM parcelas WHERE emprestimo_id = %s AND status = 'PENDENTE'", (p[1],))
        if cur.fetchone()[0] == 0:
            cur.execute("UPDATE emprestimos SET status = 'QUITADO' WHERE id = %s", (p[1],))
            print("Era a última parcela: empréstimo QUITADO!")
    print("Pagamento registrado.")


def escolher_emprestimo(cobrador_id):
    with pg, pg.cursor() as cur:
        cur.execute("""
            SELECT e.id, e.cliente_id, c.nome, e.valor_principal, e.status
            FROM emprestimos e
            JOIN clientes c ON c.id = e.cliente_id
            WHERE c.cobrador_id = %s
            ORDER BY e.id
        """, (cobrador_id,))
        emprestimos = cur.fetchall()
    return escolher(emprestimos, lambda e: f"Empréstimo {e[0]} - {e[2]} - R$ {e[3]:.2f} - {e[4]}")


def registrar_ocorrencia(cobrador_id):
    e = escolher_emprestimo(cobrador_id)
    if not e:
        return
    doc = {
        "emprestimo_id": e[0],
        "cliente_id": e[1],
        "cobrador_id": cobrador_id,
        "tipo": input("Tipo (VISITA, LIGACAO, WHATSAPP, PROMESSA_PAGAMENTO, RECUSA): ").strip().upper(),
        "data": datetime.now(),
        "observacao": input("Observação: ").strip(),
    }
    # só a promessa tem valor e data prometida: formato variável, por isso fica no MongoDB
    if doc["tipo"] == "PROMESSA_PAGAMENTO":
        valor = ler_float("Valor prometido: ")
        try:
            data = datetime.strptime(input("Data prometida (dd/mm/aaaa): ").strip(), "%d/%m/%Y")
        except ValueError:
            print("Data inválida.")
            return
        doc["promessa"] = {"valor": valor, "data": data}
    try:
        mongo.ocorrencias_cobranca.insert_one(doc)
        print("Ocorrência registrada.")
    except WriteError as erro:
        mostrar_erro_validacao(erro)


def buscar_ocorrencias(emprestimo_id, limite=0):
    # usa o índice { emprestimo_id: 1, data: -1 }
    return list(mongo.ocorrencias_cobranca.find({"emprestimo_id": emprestimo_id})
                .sort("data", -1).limit(limite))


def descrever_ocorrencia(o):
    texto = f"{o['data']:%d/%m/%Y %H:%M} - {o['tipo']} - {o.get('observacao', '')}"
    if "promessa" in o:
        texto += f" (prometeu R$ {o['promessa']['valor']:.2f} para {o['promessa']['data']:%d/%m/%Y})"
    return texto


def ver_ocorrencias(cobrador_id):
    e = escolher_emprestimo(cobrador_id)
    if not e:
        return
    ocorrencias = buscar_ocorrencias(e[0])
    if not ocorrencias:
        print("Nenhuma ocorrência registrada.")
    for o in ocorrencias:
        print(descrever_ocorrencia(o))


def apagar_ocorrencia(cobrador_id):
    e = escolher_emprestimo(cobrador_id)
    if not e:
        return
    o = escolher(buscar_ocorrencias(e[0]), descrever_ocorrencia)
    if o:
        mongo.ocorrencias_cobranca.delete_one({"_id": o["_id"]})
        print("Ocorrência apagada.")
