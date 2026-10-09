# Capturador de Evidências

Ferramenta para Windows que tira prints e recortes de tela por atalho de teclado e, ao
final do teste, cria uma pasta com o nome do teste contendo as imagens e um PDF de evidências.

## Como obter e iniciar

Baixe o repositório (`git clone https://github.com/EduRaging/Evidenciamentos.git` ou *Code → Download ZIP*
no GitHub). **O `.exe` não vem no repositório**: ele é gerado a partir do código. Há dois caminhos:

| Quero | Faça |
|---|---|
| Usar agora, com Python | Dê dois cliques em `Iniciar.bat` |
| Ter um `.exe` portátil | Dê dois cliques em `build.bat` (veja [Gerar o executável](#gerar-o-executável-exe)) |

Os dois precisam de **Python 3.10+ e internet na primeira vez** (para instalar `Pillow` e
`reportlab`, e `pyinstaller` no caso do `build.bat`). O `Iniciar.bat` cria o ambiente `.venv` e abre
o app; nas próximas vezes abre direto.

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

## Gerar o executável (.exe)

Rode `build.bat` (precisa de Python 3.10+ e internet, só na máquina que gera). Ele cria um
ambiente próprio (`.venv-build`), roda os testes, gera `dist\CapturadorEvidencias.exe` e valida o
executável com um autoteste (`CapturadorEvidencias.exe --autoteste resultado.txt`, que confere
captura, interface, atalhos globais e geração do PDF dentro do próprio `.exe`).

O `.exe` gerado tem cerca de 20 MB e é portátil: basta copiá-lo para qualquer Windows e dar dois
cliques, **sem precisar de Python** na máquina onde ele vai rodar. A pasta `dist\` não é versionada
no Git.

O `.exe` não é assinado digitalmente. Alguns antivírus e o SmartScreen do Windows podem exibir
um aviso na primeira execução, o que é comum em executáveis novos que capturam a tela.

## Instalador

`installer\Capturador.iss` é o script do instalador (Inno Setup 6): instala só para o usuário
atual, cria atalho no Menu Iniciar, oferece atalho na Área de Trabalho e iniciar com o Windows, e
mantém configurações e evidências ao desinstalar. **Ainda não foi compilado nem testado.** Com o
Inno Setup 6 instalado, o `build.bat` já o detecta e gera `installer_output\Setup_CapturadorEvidencias_<versão>.exe`.

## Testes

```bash
python -m unittest discover -s tests -t .
```

Cobrem a conversão de atalhos, nomes de pasta, a sessão (criar, remover, retomar, finalizar) e a
geração do PDF.
