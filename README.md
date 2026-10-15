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

Na primeira execução o `Iniciar.bat` também cria, na própria pasta do projeto, o atalho
**Capturador de Evidências** com o ícone do app, que abre o programa sem janela de console. Dali em
diante use o atalho (pode fixá-lo na barra de tarefas). Para colocá-lo na Área de Trabalho:

```bash
powershell -ExecutionPolicy Bypass -File tools\criar_atalho.ps1 -AreaDeTrabalho
```

O atalho aponta para esta pasta; se o projeto for movido, apague-o e rode o `Iniciar.bat` de novo.

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

## Prompt para IA (casos de teste e relatório)

O app não se conecta a nenhuma IA: ele monta um **prompt pronto** para o senhor colar na IA que
preferir (e que a empresa aprove). Sem chave de API e sem custo.

1. Ao finalizar um teste, clique em **Preparar prompt para IA…** (ou use o botão de mesmo nome na
   janela principal, que abre o último teste; **Trocar…** escolhe outro, inclusive testes antigos).
2. Preencha o que souber: sistema/ambiente, objetivo, critérios de aceite e observações. A prévia
   do prompt atualiza enquanto o senhor digita. Escolha o que a IA deve gerar: casos de teste,
   relatório de execução ou os dois. A caixa **Pedir a entrega em PDF** (marcada por padrão) faz o
   prompt pedir que a IA devolva o resultado já como **arquivo PDF para baixar**, com capa e as
   imagens das evidências quando ela conseguir. Se a IA não gerar arquivos, o prompt manda que ela
   avise e entregue o conteúdo em Markdown, pronto para converter em PDF.
   A caixa **Sugerir casos de teste adicionais (técnicas ISTQB/BSTQB)** (também marcada por
   padrão) pede à IA que, **só quando as evidências derem base**, proponha casos extras usando as
   técnicas do currículo ISTQB/BSTQB nível Foundation (CTFL 4.0): partição de equivalência, análise
   de valor limite, tabela de decisão, transição de estado, adivinhação de erros, teste
   exploratório e checklist, além de cenários de ponta a ponta, teste combinatório e permissões.
   Os casos sugeridos vêm identificados (`CS-01`…), com técnica, prioridade por risco e a evidência
   que motivou a ideia, e **sempre marcados como "não executado"**, separados do que foi testado.
   As técnicas de caixa-branca ficam de fora, porque o testador só vê a tela.
3. **Copiar prompt**, cole na IA e **anexe o PDF** do teste (ele já traz as evidências numeradas
   e com data/hora; o prompt se refere a "Evidência N"). Se a IA não ler imagens dentro de PDF,
   anexe os PNGs numerados da pasta (**Abrir pasta do teste**).

O prompt manda a IA se basear só no que está visível, escrever "não evidenciado" quando não der
para confirmar, citar o número da evidência, não reproduzir dados pessoais e **sugerir** o status
(Aprovado, Reprovado ou Inconclusivo) sem decidir sozinha. O texto também fica salvo na pasta do
teste como `Prompt para IA.txt` (cole na IA antes de fechar o app, ou abra esse arquivo).

Antes de anexar, confira se as evidências não têm dados pessoais ou sensíveis. A qualidade da
resposta depende da IA escolhida e deve ser revisada por quem executou o teste.

## Servidor MCP (protótipo)

Em vez de colar o prompt e anexar arquivos, o app pode ser conectado direto a uma IA que fale
**MCP** (Model Context Protocol), como o Claude Desktop ou o Claude Code. A IA então **lê as
evidências sozinha** e **grava o relatório em PDF dentro da pasta do teste**, gerado no seu
computador (com as imagens anexadas), sem depender de a IA gerar arquivos.

| Ferramenta | O que faz |
|---|---|
| `listar_testes` | lista os testes finalizados mais recentes |
| `obter_teste` | dados do teste e a lista numerada de evidências |
| `ver_evidencia` | devolve a imagem de uma evidência para a IA olhar (reduzida a no máximo 1568 px) |
| `salvar_relatorio_pdf` | grava o relatório (Markdown) em PDF + `.md` na pasta do teste |

Há também o prompt `analisar_teste`, com as instruções completas (mesmas regras do prompt colado,
inclusive as sugestões de casos adicionais ISTQB/BSTQB; `sugerir_casos=false` as desliga).

**Segurança**: toda ferramenta recebe só o *nome da pasta* do teste, sempre resolvido dentro da
pasta de evidências; nada fora dela é lido ou escrito, e nenhum arquivo é sobrescrito (o segundo
relatório com o mesmo título vira `(2)`). As leituras são marcadas como somente leitura. O PDF
sai com o aviso "Rascunho gerado por IA… revisão do testador necessária".

**Instalar** (usa o mesmo `.venv`; requer Python 3.11+):

```bash
.venv\Scripts\python.exe -m pip install -r requirements-mcp.txt
```

**Registrar no Claude Code**:

```bash
claude mcp add --transport stdio evidenciador -- "<pasta do projeto>\.venv\Scripts\python.exe" "<pasta do projeto>\servidor_mcp.py"
```

**Registrar no Claude desktop**: em `%APPDATA%\Claude\claude_desktop_config.json`, e reiniciar o app:

```json
{
  "mcpServers": {
    "evidenciador": {
      "command": "<pasta do projeto>\\.venv\\Scripts\\python.exe",
      "args": ["<pasta do projeto>\\servidor_mcp.py"]
    }
  }
}
```

Depois, peça algo como: *"Analise o teste mais recente e gere o relatório em PDF"*, ou use o prompt
`analisar_teste`. Por padrão o servidor lê a pasta de evidências definida nas Configurações do app
(`CAPTURADOR_PASTA_BASE` a substitui).

**Estado**: protótipo. Testado de ponta a ponta pelo protocolo com um cliente MCP (handshake,
ferramentas, imagem, PDF, recusa de caminhos fora da pasta), mas **ainda não** com o Claude
Desktop/Claude Code de verdade, e **não incluído no `.exe`** (um `.exe` sem janela não tem
stdio; empacotar pede um executável de console à parte).

## Detalhes úteis

- A janela do app **não aparece nos prints** e o aviso de captura não rouba o foco, então menus e
  listas abertos no sistema testado continuam abertos (requer Windows 10 versão 2004 ou superior).
- As capturas ficam guardadas em `%APPDATA%\CapturadorEvidencias\em_andamento` até você finalizar.
  Se fechar o app antes, ele oferece continuar de onde parou na próxima vez.
- Em **Configurações…** dá para definir a pasta base e o nome do testador (sai na capa do PDF).
- Erros inesperados ficam em `%APPDATA%\CapturadorEvidencias\capturador.log`.
- Cada teste finalizado guarda um `evidencias.json` na pasta, usado para preparar o prompt de IA.
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
