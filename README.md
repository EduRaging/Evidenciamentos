# Capturador de Evidências

Ferramenta para Windows que tira prints e recortes de tela por atalho de teclado e, ao
final do teste, cria uma pasta com o nome do teste contendo as imagens e um PDF de evidências.

## Como iniciar

Dê dois cliques em `Iniciar.bat`. Na primeira vez ele cria o ambiente (`.venv`) e instala as
dependências (`Pillow` e `reportlab`); precisa de Python 3.10+ e internet nessa etapa.

## Como usar

1. (Opcional) digite o **nome do teste** na janela. Dá para deixar em branco e informar só no final.
2. Com o app aberto ou minimizado, use os atalhos em qualquer programa:

   | Atalho padrão | Ação |
   |---|---|
   | `Ctrl+Shift+F9` | Captura a **tela inteira** (monitor onde está o mouse) |
   | `Ctrl+Shift+F8` | **Recorta uma área**: arraste com o mouse; `Esc` ou botão direito cancela |
   | `Ctrl+Shift+F7` | Mostra / oculta a janela do app |

   Todos os atalhos podem ser trocados em **Configurações…** (clique em *Alterar…* e pressione a
   nova combinação).
3. **Finalizar e gerar PDF** cria, dentro da pasta base (padrão: `Documentos\Evidencias`):

   ```
   2026-10-09_1432 - Nome do teste\
       01_tela.png
       02_recorte.png
       Evidencias - Nome do teste.pdf
   ```

   O PDF tem uma capa (nome, data, testador, quantidade) e uma evidência por página, com
   data/hora e tipo (tela inteira ou recorte).

## Detalhes úteis

- A janela do app **não aparece nos prints** e o aviso de captura não rouba o foco, então menus e
  listas abertos no sistema testado continuam abertos (requer Windows 10 versão 2004 ou superior).
- As capturas ficam guardadas em `%APPDATA%\CapturadorEvidencias\em_andamento` até você finalizar.
  Se fechar o app antes, ele oferece continuar de onde parou na próxima vez.
- Em **Configurações…** dá para definir a pasta base e o nome do testador (sai na capa do PDF).
- Erros inesperados ficam em `%APPDATA%\CapturadorEvidencias\capturador.log`.
- Só uma instância roda por vez.

## Limitações conhecidas

- Só Windows.
- A tela inteira e o recorte usam o monitor onde está o cursor; um recorte não atravessa dois monitores.
- O cursor do mouse não aparece nos prints.
- Um atalho já usado por outro programa não é registrado; o app avisa e você escolhe outro.

## Testes

```bash
python -m unittest discover -s tests -t .
```

Cobrem a conversão de atalhos, nomes de pasta, a sessão (criar, remover, retomar, finalizar) e a
geração do PDF.
