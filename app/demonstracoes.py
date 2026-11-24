"""Itens para mostrar na apresentação, um por opção."""
import json
import re
from datetime import datetime

import psycopg2
from pymongo.errors import PyMongoError, WriteError

from conexao import mongo, pg


def menu():
    while True:
        print("\n--- DEMONSTRAÇÕES ---")
        print("1 - Testar conexões")
        print("2 - Inserir solicitação inválida")
        print("3 - Mostrar o $jsonSchema")
        print("4 - Testar as expressões regulares")
        print("5 - Mostrar índices e o uso deles")
        print("0 - Voltar")
        opcao = input("Opção: ").strip()
        try:
            if opcao == "1":
                testar_conexoes()
            elif opcao == "2":
                inserir_invalida()
            elif opcao == "3":
                mostrar_schema()
            elif opcao == "4":
                testar_regex()
            elif opcao == "5":
                mostrar_indices()
            elif opcao == "0":
                return
        except psycopg2.Error as e:
            print("Erro no PostgreSQL:", e)
        except PyMongoError as e:
            print("Erro no MongoDB:", e)


def testar_conexoes():
    print("\n[PostgreSQL]")
    with pg, pg.cursor() as cur:
        cur.execute("SELECT version()")
        print(cur.fetchone()[0])
        for tabela in ["funcionarios", "clientes", "emprestimos", "parcelas"]:
            # nome da tabela vem desta lista fixa, não do usuário
            cur.execute(f"SELECT COUNT(*) FROM {tabela}")
            print(f"  {tabela}: {cur.fetchone()[0]} registros")
    print("\n[MongoDB]")
    print("Versão:", mongo.command("buildInfo")["version"])
    for colecao in ["solicitacoes", "ocorrencias_cobranca"]:
        print(f"  {colecao}: {mongo[colecao].count_documents({})} documentos")


def inserir_invalida():
    doc = {
        "nome": "Fulano Invalido",
        "cpf": "12345678900",          # sem pontuação: falha no pattern
        "telefone": "(53) 99123-4567",
        "valor_solicitado": 1000000,   # acima do maximum (50000)
        "parcelas_desejadas": 10,
        "status": "TALVEZ",            # fora do enum
        "criado_em": datetime.now(),
        # sem o campo obrigatório "endereco"
    }
    print("Tentando inserir:")
    print(json.dumps(doc, indent=2, default=str, ensure_ascii=False))
    try:
        mongo.solicitacoes.insert_one(doc)
        print("Inseriu?! O validador não está ativo.")
    except WriteError as e:
        print("\nRECUSADO pelo MongoDB:", e.details.get("errmsg"))
        print("Regras que falharam (errInfo):")
        print(json.dumps(e.details["errInfo"], indent=2, default=str, ensure_ascii=False))


def mostrar_schema():
    # lê o validador de volta do próprio banco, provando que está gravado lá
    info = mongo.command("listCollections", filter={"name": "solicitacoes"})
    colecao = info["cursor"]["firstBatch"][0]
    schema = colecao["options"]["validator"]["$jsonSchema"]
    print(json.dumps(schema, indent=2, ensure_ascii=False))
    print("\nPatterns (expressões regulares) usados:")
    print("  cpf:      ", schema["properties"]["cpf"]["pattern"])
    print("  telefone: ", schema["properties"]["telefone"]["pattern"])
    garantia = schema["properties"]["garantias"]["items"]["properties"]
    print("  placa:    ", garantia["placa"]["pattern"])
    print("  imei:     ", garantia["imei"]["pattern"])
    print(f"\nvalidationLevel: {colecao['options']['validationLevel']}, "
          f"validationAction: {colecao['options']['validationAction']}")


def testar_regex():
    # mesmos patterns do mongo/setup.js, testados com re.fullmatch no Python
    testes = {
        "CPF  ^[0-9]{3}\\.[0-9]{3}\\.[0-9]{3}-[0-9]{2}$": (
            r"^[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2}$",
            ["123.456.789-00", "12345678900", "123.456.789-0", "abc.def.ghi-jk"]),
        "Telefone  ^\\([0-9]{2}\\) 9[0-9]{4}-[0-9]{4}$": (
            r"^\([0-9]{2}\) 9[0-9]{4}-[0-9]{4}$",
            ["(53) 99123-4567", "53 99123-4567", "(53) 3222-1111", "(53) 89123-4567"]),
        "Placa  ^[A-Z]{3}-?[0-9][A-Z0-9][0-9]{2}$": (
            r"^[A-Z]{3}-?[0-9][A-Z0-9][0-9]{2}$",
            ["IOK-4521", "IOK4B21", "IOK-4B21", "iok-4521", "IO-4521"]),
    }
    for titulo, (pattern, valores) in testes.items():
        print(f"\n{titulo}")
        for valor in valores:
            casou = "casa    " if re.fullmatch(pattern, valor) else "NÃO casa"
            print(f"  {casou}  {valor}")
    print("\nLeitura das partes:")
    print("  ^ e $      = início e fim: o texto inteiro precisa seguir o formato")
    print("  [0-9]{3}   = exatamente 3 dígitos")
    print("  \\.  \\(  \\) = ponto e parênteses literais (sem a barra teriam outro significado)")
    print("  9          = o celular sempre começa com 9")
    print("  -?         = hífen opcional (placa antiga ABC-1234 e Mercosul ABC1D23)")
    print("  [A-Z0-9]   = uma letra ou um dígito (a posição que mudou no Mercosul)")


def mostrar_indices():
    for colecao in ["solicitacoes", "ocorrencias_cobranca"]:
        print(f"\nÍndices de {colecao}:")
        for indice in mongo[colecao].list_indexes():
            print(f"  {indice['name']}: {dict(indice['key'])}")

    print("\nexplain() da fila de pendentes: find({status: 'PENDENTE'}).sort({criado_em: 1})")
    plano = mongo.solicitacoes.find({"status": "PENDENTE"}).sort("criado_em", 1).explain()
    estagio = plano["queryPlanner"]["winningPlan"]
    # desce pelos estágios até o último (o que de fato lê os dados)
    caminho = []
    while estagio:
        caminho.append(estagio["stage"] + (f" ({estagio['indexName']})" if "indexName" in estagio else ""))
        estagio = estagio.get("inputStage")
    print("  Plano vencedor:", " <- ".join(caminho))
    if any(c.startswith("IXSCAN") for c in caminho):
        print("  IXSCAN: usou o índice, sem varrer a coleção e sem ordenar em memória.")
    else:
        print("  COLLSCAN: varreu a coleção inteira.")
