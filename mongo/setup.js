// Banco não relacional do sistema de agiotagem (fictício, trabalho acadêmico).
// Guarda os dados de formato variável: solicitações (garantias diferentes) e o diário de cobrança.
// Rodar com: mongosh agiota mongo/setup.js   (no Docker roda sozinho na primeira subida)

// apaga antes para o script poder ser rodado de novo sem erro
db.solicitacoes.drop();
db.ocorrencias_cobranca.drop();

// Mesmo pattern do telefone usado em solicitacoes e referencias: (53) 99123-4567
const PATTERN_TELEFONE = "^\\([0-9]{2}\\) 9[0-9]{4}-[0-9]{4}$";

db.createCollection("solicitacoes", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["nome", "cpf", "telefone", "endereco", "valor_solicitado",
                 "parcelas_desejadas", "status", "criado_em"],
      properties: {
        nome: { bsonType: "string", minLength: 3, maxLength: 100 },
        // CPF com pontuação: 123.456.789-00
        cpf: { bsonType: "string", pattern: "^[0-9]{3}\\.[0-9]{3}\\.[0-9]{3}-[0-9]{2}$" },
        telefone: { bsonType: "string", pattern: PATTERN_TELEFONE },
        endereco: { bsonType: "string", minLength: 5 },
        // "number" aceita int e double (o Python manda 2000 como int e 2000.0 como double)
        valor_solicitado: { bsonType: "number", minimum: 100, maximum: 50000 },
        parcelas_desejadas: { bsonType: "int", minimum: 1, maximum: 24 },
        renda_declarada: { bsonType: "number", minimum: 0 },
        status: { enum: ["PENDENTE", "APROVADA", "RECUSADA"] },
        garantias: {
          bsonType: "array",
          items: {
            bsonType: "object",
            required: ["tipo", "descricao"],
            properties: {
              tipo: { enum: ["VEICULO", "CELULAR", "ELETRONICO", "JOIA", "OUTRO"] },
              descricao: { bsonType: "string" },
              valor_estimado: { bsonType: "number", minimum: 0 },
              // placa antiga (ABC-1234) ou Mercosul (ABC1D23)
              placa: { bsonType: "string", pattern: "^[A-Z]{3}-?[0-9][A-Z0-9][0-9]{2}$" },
              // IMEI: exatamente 15 dígitos
              imei: { bsonType: "string", pattern: "^[0-9]{15}$" }
            }
          }
        },
        referencias: {
          bsonType: "array",
          items: {
            bsonType: "object",
            required: ["nome", "telefone"],
            properties: {
              nome: { bsonType: "string" },
              telefone: { bsonType: "string", pattern: PATTERN_TELEFONE },
              parentesco: { bsonType: "string" }
            }
          }
        },
        criado_em: { bsonType: "date" },
        emprestimo_id: { bsonType: ["int", "null"] },   // id do empréstimo no PostgreSQL
        motivo_recusa: { bsonType: ["string", "null"] }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});

db.createCollection("ocorrencias_cobranca", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["emprestimo_id", "cliente_id", "cobrador_id", "tipo", "data"],
      properties: {
        // ids que apontam para o PostgreSQL
        emprestimo_id: { bsonType: "int" },
        cliente_id: { bsonType: "int" },
        cobrador_id: { bsonType: "int" },
        tipo: { enum: ["VISITA", "LIGACAO", "WHATSAPP", "PROMESSA_PAGAMENTO", "RECUSA"] },
        data: { bsonType: "date" },
        observacao: { bsonType: "string", maxLength: 500 },
        // só existe nas promessas de pagamento
        promessa: {
          bsonType: "object",
          required: ["valor", "data"],
          properties: {
            valor: { bsonType: "number", minimum: 1 },
            data: { bsonType: "date" }
          }
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});

// Índices
// A tela principal do agiota é a fila de pendentes em ordem de chegada:
// filtra por status e ordena por criado_em. O índice composto atende o filtro
// e a ordenação sem varrer a coleção inteira.
db.solicitacoes.createIndex({ status: 1, criado_em: 1 });
// O cliente acompanha e cancela a própria solicitação informando o CPF.
db.solicitacoes.createIndex({ cpf: 1 });
// A ficha do devedor busca as ocorrências de um empréstimo, das mais recentes para as mais antigas.
db.ocorrencias_cobranca.createIndex({ emprestimo_id: 1, data: -1 });

// ---------- Dados de exemplo ----------
// NumberInt: no mongosh todo número é double; os campos "int" precisam de NumberInt.
function diasAtras(dias) { return new Date(Date.now() - dias * 24 * 60 * 60 * 1000); }

db.solicitacoes.insertMany([
  // as duas aprovadas são a origem dos empréstimos 1 e 2 do PostgreSQL (solicitacao_id)
  {
    _id: ObjectId("650000000000000000000001"),
    nome: "Carlos Pereira", cpf: "111.222.333-44", telefone: "(53) 98111-2233",
    endereco: "Rua XV de Novembro, 500, Centro, Pelotas",
    valor_solicitado: 1000, parcelas_desejadas: NumberInt(5), renda_declarada: 2200,
    status: "APROVADA",
    garantias: [{ tipo: "ELETRONICO", descricao: "Notebook Dell", valor_estimado: 2500 }],
    referencias: [{ nome: "Joana Pereira", telefone: "(53) 98000-1111", parentesco: "esposa" }],
    criado_em: diasAtras(102), emprestimo_id: NumberInt(1), motivo_recusa: null
  },
  {
    _id: ObjectId("650000000000000000000002"),
    nome: "Ana Souza", cpf: "222.333.444-55", telefone: "(53) 98222-3344",
    endereco: "Av. Bento Goncalves, 1200, Centro, Pelotas",
    valor_solicitado: 2000, parcelas_desejadas: NumberInt(4),
    status: "APROVADA",
    garantias: [{ tipo: "JOIA", descricao: "Aliança de ouro 18k", valor_estimado: 1800 }],
    referencias: [],
    criado_em: diasAtras(97), emprestimo_id: NumberInt(2), motivo_recusa: null
  },
  // pendentes: uma com veículo, uma com celular, uma sem garantia
  {
    nome: "João da Silva", cpf: "123.456.789-00", telefone: "(53) 99123-4567",
    endereco: "Rua das Flores, 100, Laranjal, Pelotas",
    valor_solicitado: 2000, parcelas_desejadas: NumberInt(10), renda_declarada: 1800,
    status: "PENDENTE",
    garantias: [
      { tipo: "VEICULO", descricao: "Gol 2012", placa: "IOK-4B21", valor_estimado: 25000 }
    ],
    referencias: [{ nome: "Maria da Silva", telefone: "(53) 98888-7777", parentesco: "mãe" }],
    criado_em: diasAtras(3), emprestimo_id: null, motivo_recusa: null
  },
  {
    nome: "Paula Mendes", cpf: "987.654.321-00", telefone: "(53) 99777-6655",
    endereco: "Rua Andrade Neves, 45, Centro, Pelotas",
    valor_solicitado: 800, parcelas_desejadas: NumberInt(4),
    status: "PENDENTE",
    garantias: [
      { tipo: "CELULAR", descricao: "iPhone 11", imei: "356789012345678", valor_estimado: 1500 }
    ],
    referencias: [],
    criado_em: diasAtras(2), emprestimo_id: null, motivo_recusa: null
  },
  {
    nome: "Roberto Alves", cpf: "555.666.777-88", telefone: "(53) 99444-3322",
    endereco: "Av. Fernando Osorio, 2000, Tres Vendas, Pelotas",
    valor_solicitado: 500, parcelas_desejadas: NumberInt(2), renda_declarada: 1500,
    status: "PENDENTE",
    criado_em: diasAtras(1), emprestimo_id: null, motivo_recusa: null
  },
  {
    nome: "Marcos Dias", cpf: "666.777.888-99", telefone: "(53) 99555-1122",
    endereco: "Rua Lobo da Costa, 10, Centro, Pelotas",
    valor_solicitado: 30000, parcelas_desejadas: NumberInt(24), renda_declarada: 900,
    status: "RECUSADA",
    criado_em: diasAtras(10), emprestimo_id: null,
    motivo_recusa: "Renda incompatível com o valor pedido e sem garantia"
  }
]);

db.ocorrencias_cobranca.insertMany([
  { emprestimo_id: NumberInt(1), cliente_id: NumberInt(1), cobrador_id: NumberInt(2),
    tipo: "LIGACAO", data: diasAtras(8), observacao: "Não atendeu" },
  { emprestimo_id: NumberInt(1), cliente_id: NumberInt(1), cobrador_id: NumberInt(2),
    tipo: "VISITA", data: diasAtras(5), observacao: "Ninguém em casa, deixei recado com o vizinho" },
  { emprestimo_id: NumberInt(1), cliente_id: NumberInt(1), cobrador_id: NumberInt(2),
    tipo: "PROMESSA_PAGAMENTO", data: diasAtras(2), observacao: "Disse que paga na sexta, depois que receber",
    promessa: { valor: 400, data: diasAtras(-3) } },
  { emprestimo_id: NumberInt(2), cliente_id: NumberInt(2), cobrador_id: NumberInt(3),
    tipo: "WHATSAPP", data: diasAtras(30), observacao: "Mandei lembrete da parcela 2" },
  { emprestimo_id: NumberInt(2), cliente_id: NumberInt(2), cobrador_id: NumberInt(3),
    tipo: "RECUSA", data: diasAtras(1), observacao: "Disse que não vai pagar este mês" }
]);
