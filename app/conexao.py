"""Conexões com o PostgreSQL e o MongoDB, criadas uma vez e importadas pelos outros arquivos."""
import os
import sys

import psycopg2
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

try:
    # autocommit fica desligado: cada função usa "with pg:" (commit no sucesso, rollback no erro)
    pg = psycopg2.connect(
        host=os.getenv("PG_HOST", "localhost"),
        port=os.getenv("PG_PORT", "5432"),
        dbname=os.getenv("PG_DB", "agiota"),
        user=os.getenv("PG_USER", "agiota"),
        password=os.getenv("PG_PASSWORD", "agiota"),
        connect_timeout=5,
    )
except Exception as e:
    # Exception e não só psycopg2.Error: no Windows em português a mensagem do servidor
    # pode vir com acento em outra codificação e virar UnicodeDecodeError
    print("Não foi possível conectar ao PostgreSQL. Ele está rodando? Confira host, porta e senha no .env.")
    print("Detalhe:", e)
    sys.exit(1)

try:
    cliente_mongo = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"),
                                serverSelectionTimeoutMS=5000)
    cliente_mongo.admin.command("ping")  # o MongoClient só conecta de verdade no primeiro comando
    mongo = cliente_mongo[os.getenv("MONGO_DB", "agiota")]
except Exception as e:
    print("Não foi possível conectar ao MongoDB. Ele está rodando? Confira o .env.")
    print("Detalhe:", e)
    sys.exit(1)


# ---------- Funções de entrada e mensagens usadas por todos os menus ----------

def ler_int(mensagem, padrao=None):
    """Lê um número inteiro. Enter vazio devolve o padrão (se houver)."""
    while True:
        texto = input(mensagem).strip()
        if texto == "" and padrao is not None:
            return padrao
        try:
            return int(texto)
        except ValueError:
            print("Digite um número inteiro.")


def ler_float(mensagem, padrao=None):
    """Lê um número com casas decimais (aceita vírgula). Enter vazio devolve o padrão."""
    while True:
        texto = input(mensagem).strip().replace(",", ".")
        if texto == "" and padrao is not None:
            return padrao
        try:
            return float(texto)
        except ValueError:
            print("Digite um número.")


def escolher(itens, descrever):
    """Mostra a lista numerada e devolve o item escolhido (ou None).
    Usado para o usuário nunca precisar digitar um ObjectId."""
    if not itens:
        print("Nenhum registro encontrado.")
        return None
    for i, item in enumerate(itens, start=1):
        print(f"{i} - {descrever(item)}")
    n = ler_int("Escolha o número (0 para voltar): ")
    if 1 <= n <= len(itens):
        return itens[n - 1]
    return None


def mostrar_erro_validacao(e):
    """Mostra quais campos o $jsonSchema do MongoDB recusou (vem em e.details['errInfo'])."""
    print("\nO MongoDB recusou o documento (validação $jsonSchema).")
    try:
        regras = e.details["errInfo"]["details"]["schemaRulesNotSatisfied"]
        for regra in regras:
            for campo in regra.get("propertiesNotSatisfied", []):
                print(f"  - campo inválido: {campo['propertyName']}")
            for campo in regra.get("missingProperties", []):
                print(f"  - campo obrigatório faltando: {campo}")
    except (KeyError, TypeError):
        print("Detalhe:", e)
