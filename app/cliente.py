"""Menu do cliente: solicitações no MongoDB e parcelas no PostgreSQL."""
from datetime import datetime

import psycopg2
from pymongo.errors import PyMongoError, WriteError

from conexao import escolher, ler_float, ler_int, mongo, mostrar_erro_validacao, pg


def menu():
    # o cliente se identifica pelo CPF (sem senha)
    cpf = input("Informe seu CPF (000.000.000-00): ").strip()
    while True:
        print("\n--- CLIENTE ---")
        print("1 - Fazer solicitação de empréstimo")
        print("2 - Acompanhar minhas solicitações")
        print("3 - Alterar valor ou parcelas de uma solicitação pendente")
        print("4 - Cancelar solicitação pendente")
        print("5 - Ver minhas parcelas")
        print("0 - Voltar")
        opcao = input("Opção: ").strip()
        if opcao == "1":
            fazer_solicitacao(cpf)
        elif opcao == "2":
            acompanhar_solicitacoes(cpf)
        elif opcao == "3":
            alterar_solicitacao(cpf)
        elif opcao == "4":
            cancelar_solicitacao(cpf)
        elif opcao == "5":
            ver_parcelas(cpf)
        elif opcao == "0":
            return


def fazer_solicitacao(cpf):
    # Sem validação no Python de propósito: quem recusa CPF, telefone, placa e valores é o $jsonSchema
    doc = {
        "nome": input("Nome completo: ").strip(),
        "cpf": cpf,
        "telefone": input("Telefone ((53) 99999-9999): ").strip(),
        "endereco": input("Endereço: ").strip(),
        "valor_solicitado": ler_float("Valor desejado: "),
        "parcelas_desejadas": ler_int("Quantidade de parcelas: "),
        "status": "PENDENTE",
        "garantias": [],
        "referencias": [],
        "criado_em": datetime.now(),
        "emprestimo_id": None,
        "motivo_recusa": None,
    }
    renda = input("Renda mensal (Enter para não informar): ").strip()
    if renda:  # campo opcional: só entra no documento se for informado
        try:
            doc["renda_declarada"] = float(renda.replace(",", "."))
        except ValueError:
            print("Renda ignorada: não é um número.")

    while input("Adicionar garantia? (s/n): ").strip().lower() == "s":
        garantia = {
            "tipo": input("Tipo (VEICULO, CELULAR, ELETRONICO, JOIA, OUTRO): ").strip().upper(),
            "descricao": input("Descrição: ").strip(),
            "valor_estimado": ler_float("Valor estimado: "),
        }
        # cada tipo de garantia tem campos diferentes: por isso ela fica no MongoDB
        if garantia["tipo"] == "VEICULO":
            garantia["placa"] = input("Placa (ABC-1234 ou ABC1D23): ").strip().upper()
        elif garantia["tipo"] == "CELULAR":
            garantia["imei"] = input("IMEI (15 dígitos): ").strip()
        doc["garantias"].append(garantia)

    while input("Adicionar referência? (s/n): ").strip().lower() == "s":
        doc["referencias"].append({
            "nome": input("Nome da referência: ").strip(),
            "telefone": input("Telefone da referência: ").strip(),
            "parentesco": input("Parentesco: ").strip(),
        })

    try:
        resultado = mongo.solicitacoes.insert_one(doc)
        print(f"Solicitação enviada! Código: {resultado.inserted_id}")
    except WriteError as e:
        mostrar_erro_validacao(e)
    except PyMongoError as e:
        print("Erro ao falar com o MongoDB:", e)


def mostrar_solicitacao(s):
    print(f"\nPedido de {s['criado_em']:%d/%m/%Y %H:%M} - {s['status']}")
    print(f"  Valor: R$ {s['valor_solicitado']:.2f} em {s['parcelas_desejadas']}x")
    for g in s.get("garantias", []):
        extra = g.get("placa") or g.get("imei") or ""
        print(f"  Garantia: {g['tipo']} - {g['descricao']} {extra} (R$ {g.get('valor_estimado', 0):.2f})")
    for r in s.get("referencias", []):
        print(f"  Referência: {r['nome']} {r['telefone']} ({r.get('parentesco', '')})")
    if s.get("motivo_recusa"):
        print(f"  Motivo da recusa: {s['motivo_recusa']}")
    if s.get("emprestimo_id"):
        print(f"  Empréstimo gerado: nº {s['emprestimo_id']}")


def acompanhar_solicitacoes(cpf):
    try:
        # usa o índice { cpf: 1 }
        solicitacoes = list(mongo.solicitacoes.find({"cpf": cpf}).sort("criado_em", -1))
    except PyMongoError as e:
        print("Erro ao falar com o MongoDB:", e)
        return
    if not solicitacoes:
        print("Nenhuma solicitação para este CPF.")
    for s in solicitacoes:
        mostrar_solicitacao(s)


def escolher_pendente(cpf):
    try:
        pendentes = list(mongo.solicitacoes.find({"cpf": cpf, "status": "PENDENTE"}).sort("criado_em", 1))
    except PyMongoError as e:
        print("Erro ao falar com o MongoDB:", e)
        return None
    return escolher(pendentes, lambda s: f"{s['criado_em']:%d/%m/%Y} - R$ {s['valor_solicitado']:.2f} "
                                         f"em {s['parcelas_desejadas']}x")


def alterar_solicitacao(cpf):
    s = escolher_pendente(cpf)
    if not s:
        return
    novo_valor = ler_float(f"Novo valor (Enter mantém {s['valor_solicitado']}): ", s["valor_solicitado"])
    novas_parcelas = ler_int(f"Novas parcelas (Enter mantém {s['parcelas_desejadas']}): ", s["parcelas_desejadas"])
    try:
        # o filtro com status PENDENTE impede alterar uma solicitação já analisada
        mongo.solicitacoes.update_one(
            {"_id": s["_id"], "status": "PENDENTE"},
            {"$set": {"valor_solicitado": novo_valor, "parcelas_desejadas": novas_parcelas}},
        )
        print("Solicitação alterada.")
    except WriteError as e:
        mostrar_erro_validacao(e)  # o validador também vale para updates
    except PyMongoError as e:
        print("Erro ao falar com o MongoDB:", e)


def cancelar_solicitacao(cpf):
    s = escolher_pendente(cpf)
    if not s:
        return
    try:
        mongo.solicitacoes.delete_one({"_id": s["_id"], "status": "PENDENTE"})
        print("Solicitação cancelada.")
    except PyMongoError as e:
        print("Erro ao falar com o MongoDB:", e)


def ver_parcelas(cpf):
    sql = """
        SELECT e.id, p.numero, p.vencimento, p.valor,
               CASE WHEN p.status = 'PENDENTE' AND p.vencimento < CURRENT_DATE
                    THEN 'ATRASADA' ELSE p.status END AS situacao
        FROM clientes c
        JOIN emprestimos e ON e.cliente_id = c.id
        JOIN parcelas p ON p.emprestimo_id = e.id
        WHERE c.cpf = %s
        ORDER BY e.id, p.numero
    """
    try:
        with pg, pg.cursor() as cur:
            cur.execute(sql, (cpf,))
            linhas = cur.fetchall()
    except psycopg2.Error as e:
        print("Erro ao consultar o PostgreSQL:", e)
        return
    if not linhas:
        print("Nenhuma parcela encontrada para este CPF.")
        return
    print(f"\n{'Empr.':<6}{'Nº':<4}{'Vencimento':<12}{'Valor':>10}  Situação")
    for emp, numero, venc, valor, situacao in linhas:
        print(f"{emp:<6}{numero:<4}{venc:%d/%m/%Y}  {valor:>10.2f}  {situacao}")
