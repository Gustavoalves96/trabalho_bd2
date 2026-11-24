"""Funcionalidades que usam os dois bancos juntos."""
from datetime import datetime, timedelta

import psycopg2
from bson import ObjectId
from pymongo.errors import PyMongoError

from cliente import mostrar_solicitacao
from conexao import escolher, ler_float, ler_int, mongo, pg


def aprovar_solicitacao(admin_id):
    """Mongo (lê a solicitação) -> Postgres (cria cliente, empréstimo e parcelas) -> Mongo (marca APROVADA)."""
    pendentes = list(mongo.solicitacoes.find({"status": "PENDENTE"}).sort("criado_em", 1))
    s = escolher(pendentes, lambda x: f"{x['criado_em']:%d/%m/%Y} - {x['nome']} - R$ {x['valor_solicitado']:.2f}")
    if not s:
        return
    print(f"\n{s['nome']} - CPF {s['cpf']} - {s['telefone']} - {s['endereco']}")
    print(f"Renda declarada: {s.get('renda_declarada', 'não informada')}")
    mostrar_solicitacao(s)

    valor = ler_float(f"\nValor aprovado (Enter = {s['valor_solicitado']}): ", s["valor_solicitado"])
    juros = ler_float("Juros ao mês em % (Enter = 20): ", 20)
    qtd = ler_int(f"Quantidade de parcelas (Enter = {s['parcelas_desejadas']}): ", s["parcelas_desejadas"])
    with pg, pg.cursor() as cur:
        cur.execute("SELECT id, nome FROM funcionarios WHERE papel = 'COBRADOR' ORDER BY id")
        cobradores = cur.fetchall()
    print("Cobrador responsável pelo cliente (vale só se o cliente for novo):")
    cobrador = escolher(cobradores, lambda f: f[1])
    if not cobrador:
        return

    # Juros simples: total = valor * (1 + juros/100 * parcelas)
    total = valor * (1 + juros / 100 * qtd)
    valor_parcela = round(total / qtd, 2) if qtd > 0 else 0

    try:
        # Uma transação: cliente, empréstimo e parcelas são gravados juntos ou nada é gravado
        with pg, pg.cursor() as cur:
            cur.execute("SELECT id FROM clientes WHERE cpf = %s", (s["cpf"],))
            linha = cur.fetchone()
            if linha:
                cliente_id = linha[0]
            else:
                cur.execute("""
                    INSERT INTO clientes (nome, cpf, telefone, endereco, cobrador_id)
                    VALUES (%s, %s, %s, %s, %s) RETURNING id
                """, (s["nome"], s["cpf"], s["telefone"], s["endereco"], cobrador[0]))
                cliente_id = cur.fetchone()[0]

            cur.execute("""
                INSERT INTO emprestimos (cliente_id, aprovado_por, solicitacao_id, valor_principal, juros_mes, qtd_parcelas)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING id, data_emprestimo
            """, (cliente_id, admin_id, str(s["_id"]), valor, juros, qtd))
            emprestimo_id, data_emprestimo = cur.fetchone()

            for n in range(1, qtd + 1):
                # a diferença de centavos fica na última parcela
                valor_n = valor_parcela if n < qtd else round(total - valor_parcela * (qtd - 1), 2)
                cur.execute("""
                    INSERT INTO parcelas (emprestimo_id, numero, vencimento, valor)
                    VALUES (%s, %s, %s, %s)
                """, (emprestimo_id, n, data_emprestimo + timedelta(days=30 * n), valor_n))
    except psycopg2.Error as e:
        print("O PostgreSQL recusou a aprovação, nada foi gravado:", e)
        return
    print(f"Empréstimo nº {emprestimo_id} criado: {qtd}x de R$ {valor_parcela:.2f} (total R$ {total:.2f}).")

    # Não existe transação entre dois bancos diferentes. Por isso a ordem foi escolhida:
    # primeiro grava no banco que guarda o dinheiro (Postgres), depois atualiza o Mongo.
    try:
        mongo.solicitacoes.update_one({"_id": s["_id"]},
                                      {"$set": {"status": "APROVADA", "emprestimo_id": emprestimo_id}})
        print("Solicitação marcada como APROVADA no MongoDB.")
    except PyMongoError as e:
        print(f"ATENÇÃO: o empréstimo {emprestimo_id} foi criado, mas a solicitação não foi atualizada no MongoDB: {e}")


def ficha_devedor():
    """Postgres (cliente, empréstimo, parcelas) + Mongo (ocorrências, promessa e garantias)."""
    with pg, pg.cursor() as cur:
        cur.execute("SELECT e.id, c.nome, e.status FROM emprestimos e JOIN clientes c ON c.id = e.cliente_id ORDER BY e.id")
        escolhido = escolher(cur.fetchall(), lambda e: f"Empréstimo {e[0]} - {e[1]} - {e[2]}")
    if not escolhido:
        return
    emprestimo_id = escolhido[0]

    with pg, pg.cursor() as cur:
        cur.execute("""
            SELECT c.nome, c.cpf, c.telefone, c.endereco, f.nome AS cobrador,
                   e.valor_principal, e.juros_mes, e.qtd_parcelas, e.status, e.solicitacao_id
            FROM emprestimos e
            JOIN clientes c ON c.id = e.cliente_id
            JOIN funcionarios f ON f.id = c.cobrador_id
            WHERE e.id = %s
        """, (emprestimo_id,))
        nome, cpf, telefone, endereco, cobrador, valor, juros, qtd, status, solicitacao_id = cur.fetchone()
        cur.execute("""
            SELECT numero, vencimento, valor,
                   CASE WHEN status = 'PENDENTE' AND vencimento < CURRENT_DATE
                        THEN 'ATRASADA' ELSE status END
            FROM parcelas WHERE emprestimo_id = %s ORDER BY numero
        """, (emprestimo_id,))
        parcelas = cur.fetchall()
        cur.execute("""
            SELECT COALESCE(SUM(valor) FILTER (WHERE status = 'PAGA'), 0),
                   COALESCE(SUM(valor) FILTER (WHERE status = 'PENDENTE'), 0),
                   COUNT(*) FILTER (WHERE status = 'PENDENTE' AND vencimento < CURRENT_DATE)
            FROM parcelas WHERE emprestimo_id = %s
        """, (emprestimo_id,))
        pago, em_aberto, atrasadas = cur.fetchone()

    print(f"\n========== FICHA DO DEVEDOR - EMPRÉSTIMO {emprestimo_id} ==========")
    print("[PostgreSQL]")
    print(f"Cliente: {nome}  CPF: {cpf}  Tel: {telefone}")
    print(f"Endereço: {endereco}")
    print(f"Cobrador: {cobrador}")
    print(f"Valor: R$ {valor:.2f}  Juros: {juros}% ao mês  Parcelas: {qtd}  Status: {status}")
    for numero, venc, valor_p, situacao in parcelas:
        print(f"  {numero:>2}  {venc:%d/%m/%Y}  R$ {valor_p:>9.2f}  {situacao}")
    print(f"Total pago: R$ {pago:.2f}  Em aberto: R$ {em_aberto:.2f}  Parcelas atrasadas: {atrasadas}")

    print("\n[MongoDB] Últimas 5 ocorrências de cobrança")
    ocorrencias = list(mongo.ocorrencias_cobranca.find({"emprestimo_id": emprestimo_id}).sort("data", -1).limit(5))
    if not ocorrencias:
        print("  Nenhuma ocorrência.")
    for o in ocorrencias:
        print(f"  {o['data']:%d/%m/%Y} - {o['tipo']} - {o.get('observacao', '')}")
    promessa = mongo.ocorrencias_cobranca.find_one(
        {"emprestimo_id": emprestimo_id, "tipo": "PROMESSA_PAGAMENTO"}, sort=[("data", -1)])
    if promessa:
        p = promessa["promessa"]
        print(f"  Última promessa: R$ {p['valor']:.2f} para {p['data']:%d/%m/%Y}")

    print("\n[MongoDB] Garantias da solicitação original")
    # o _id do Mongo foi guardado como texto no Postgres; aqui volta a ser ObjectId
    solicitacao = mongo.solicitacoes.find_one({"_id": ObjectId(solicitacao_id)}) if solicitacao_id else None
    if not solicitacao or not solicitacao.get("garantias"):
        print("  Nenhuma garantia registrada.")
    else:
        for g in solicitacao["garantias"]:
            extra = g.get("placa") or g.get("imei") or ""
            print(f"  {g['tipo']} - {g['descricao']} {extra} (R$ {g.get('valor_estimado', 0):.2f})")


def relatorio_cobradores():
    """Postgres (recebido e comissão no mês) + Mongo (ocorrências do mês por tipo)."""
    with pg, pg.cursor() as cur:
        cur.execute("""
            SELECT f.id, f.nome, COALESCE(SUM(p.valor), 0) AS recebido,
                   COALESCE(SUM(p.valor), 0) * f.comissao_pct / 100 AS comissao
            FROM funcionarios f
            LEFT JOIN parcelas p ON p.recebido_por = f.id
                                AND p.pago_em >= date_trunc('month', CURRENT_DATE)
            WHERE f.papel = 'COBRADOR'
            GROUP BY f.id, f.nome, f.comissao_pct
            ORDER BY f.id
        """)
        cobradores = cur.fetchall()

    inicio_mes = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    resultado = mongo.ocorrencias_cobranca.aggregate([
        {"$match": {"data": {"$gte": inicio_mes}}},
        {"$group": {"_id": {"cobrador": "$cobrador_id", "tipo": "$tipo"}, "qtd": {"$sum": 1}}},
    ])
    contagem = {(r["_id"]["cobrador"], r["_id"]["tipo"]): r["qtd"] for r in resultado}

    tipos = ["VISITA", "LIGACAO", "WHATSAPP", "PROMESSA_PAGAMENTO", "RECUSA"]
    print(f"\nRelatório de {inicio_mes:%m/%Y}")
    print(f"{'Cobrador':<22}{'Recebido':>11}{'Comissão':>10} | {'Visita':>6}{'Ligação':>8}{'Whats':>6}{'Promessa':>9}{'Recusa':>7}")
    for id_, nome, recebido, comissao in cobradores:
        qtds = [contagem.get((id_, t), 0) for t in tipos]
        print(f"{nome[:21]:<22}{recebido:>11.2f}{comissao:>10.2f} | "
              f"{qtds[0]:>6}{qtds[1]:>8}{qtds[2]:>6}{qtds[3]:>9}{qtds[4]:>7}")
