"""Menu principal. Executar a partir da raiz do projeto: python app/main.py"""
import admin
import cliente
import cobrador
import demonstracoes


def main():
    while True:
        print("\n===== SISTEMA DO AGIOTA =====")
        print("1 - Sou cliente")
        print("2 - Sou o agiota (admin)")
        print("3 - Sou cobrador")
        print("4 - Demonstrações para a apresentação")
        print("0 - Sair")
        opcao = input("Opção: ").strip()
        try:
            if opcao == "1":
                cliente.menu()
            elif opcao == "2":
                admin.menu()
            elif opcao == "3":
                cobrador.menu()
            elif opcao == "4":
                demonstracoes.menu()
            elif opcao == "0":
                break
            else:
                print("Opção inválida.")
        except Exception as e:
            # rede de segurança: nenhum stack trace aparece durante a apresentação
            print(f"\nErro inesperado: {e}")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        pass
    print("Até logo!")
