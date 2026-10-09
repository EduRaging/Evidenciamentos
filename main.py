import sys


def principal() -> None:
    if "--autoteste" in sys.argv:
        from capturador.autoteste import executar as autoteste

        posicao = sys.argv.index("--autoteste") + 1
        if posicao >= len(sys.argv):
            sys.exit("Uso: --autoteste <arquivo de resultado>")
        sys.exit(autoteste(sys.argv[posicao]))

    from capturador.app import executar

    executar()


if __name__ == "__main__":
    principal()
