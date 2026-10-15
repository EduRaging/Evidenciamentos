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

## Aba "PDFs gerados"

A segunda aba da janela principal é o **registro dos PDFs** de todos os testes da pasta de
evidências: os de evidências (gerados ao finalizar) e os relatórios (por exemplo, os que a IA grava
pela extensão MCP). Do mais recente para o mais antigo, com data, teste, tipo e tamanho. A lista
se atualiza sozinha enquanto a aba está à vista (a cada ~6 s), então um relatório criado por fora
aparece sem fazer nada. O campo **Filtrar** ignora acentos e combina palavras ("relatorio despesa").

Selecione um PDF (ou clique com o botão direito) e use:

| Ação | O que faz |
|---|---|
| **Abrir (ler)** | abre no leitor de PDF padrão (também com dois cliques ou Enter) |
| **Mostrar na pasta** | abre o Explorador de Arquivos com o PDF selecionado |
| **Copiar caminho** | copia o caminho completo como texto |
| **Copiar arquivo** | copia o **arquivo** (não o texto): cole com Ctrl+V num e-mail, no Teams ou numa pasta |
| **Salvar cópia…** | grava uma cópia onde você escolher (baixar); o original fica no lugar |
| **Enviar por e-mail…** | abre uma mensagem nova com assunto e texto prontos e deixa o PDF copiado: cole (Ctrl+V) para anexar |

O padrão de e-mail do Windows (`mailto:`) não permite anexar arquivos, por isso o anexo é feito
colando o PDF já copiado.

## Prompt para IA (casos de teste e relatório)

O app não se conecta a nenhuma IA: ele monta um **prompt pronto** para o senhor enviar ao Claude
desktop (um clique abre a conversa com o texto preenchido) ou colar na IA que preferir (e que a
empresa aprove). Sem chave de API e sem custo, e sem tráfego de rede do app.

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
3. **Enviar ao Claude** abre o **Claude desktop** numa conversa nova **com o prompt já preenchido**:
   o senhor só confere e aperta Enter (o Claude apenas preenche a caixa; nada sai do computador
   antes disso). Com a extensão do Claude instalada (veja abaixo), a caixa **Claude com a extensão
   instalada** (marcada por padrão) faz o prompt mandar a IA ler as evidências direto da pasta e
   gravar o PDF lá, sem anexar nada; a janela mostra a pasta que a extensão precisa ter
   configurada. Sem a extensão, desmarque a caixa: o prompt volta ao formato de anexos.
   Se o prompt passar de ~12 mil caracteres (limite do link do Claude) ou o Claude desktop não
   estiver instalado, o app copia o prompt e avisa para colar (Ctrl+V).
   Para outra IA, use **Copiar prompt**, cole e **anexe o PDF** do teste (ele já traz as evidências
   numeradas e com data/hora; o prompt se refere a "Evidência N"). Se a IA não ler imagens dentro
   de PDF, anexe os PNGs numerados da pasta (**Abrir pasta do teste**).

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

**Instalar** (requer Python 3.11+). Use um ambiente à parte, `.venv-mcp`, para não mexer no
`.venv` do app:

```bash
python -m venv .venv-mcp
.venv-mcp\Scripts\python.exe -m pip install -r requirements-mcp.txt
```

**Testar sem interferir em nada** (nem na sua configuração do Claude, nem nos seus testes reais):

1. *Autoteste isolado, sem IA.* Cria um teste **fictício** numa pasta temporária, sobe o servidor
   e conversa com ele pelo protocolo MCP; apaga tudo no fim:

   ```bash
   .venv-mcp\Scripts\python.exe tools\testar_mcp.py
   ```

2. *Teste com o Claude de verdade, só com dados de exemplo.* Gere um teste fictício numa pasta
   separada e aponte o servidor para ela (`CAPTURADOR_PASTA_BASE`), de modo que o Claude nunca
   veja as suas evidências reais:

   ```bash
   .venv-mcp\Scripts\python.exe tools\testar_mcp.py --criar-exemplo "C:\Evidencias_TESTE"
   claude mcp add --env CAPTURADOR_PASTA_BASE="C:\Evidencias_TESTE" --transport stdio evidenciador-teste -- "<pasta do projeto>\.venv-mcp\Scripts\python.exe" "<pasta do projeto>\servidor_mcp.py"
   ```

   O registro fica no escopo `local` (padrão: só você, só neste projeto; não use `--scope project`,
   que grava um `.mcp.json` compartilhado). Ao terminar: `claude mcp remove evidenciador-teste`.
   No Claude desktop, faça uma cópia do `claude_desktop_config.json`, acrescente uma entrada
   com outro nome (ex.: `evidenciador-teste`, com `env` apontando para a pasta de exemplo) e
   remova-a depois.

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
`analisar_teste`. A pasta de evidências é **obrigatória e explícita**: vem da variável
`CAPTURADOR_PASTA_BASE` (ou, na extensão, do argumento `--pasta`). Sem ela o servidor **se recusa a
trabalhar** em vez de cair numa pasta padrão do app: numa versão anterior esse "plano B" fez a
extensão ler as evidências **reais** quando a configuração da extensão não chegou ao processo. Agora
`listar_testes` informa qual pasta está sendo lida (`pasta_base`) e `salvar_relatorio_pdf` devolve o
caminho completo do arquivo gerado.

### Extensão para o Claude desktop (`.mcpb`), uso pessoal

O botão **+ Adicionar → conector personalizado** do Claude só aceita servidor **remoto com URL
pública** (o Claude conecta pela nuvem da Anthropic, não pelo seu computador), então não serve
para ler uma pasta local. O equivalente local é uma **extensão `.mcpb`**: o mesmo servidor, num
pacote que o Claude desktop instala com dois cliques, sem editar JSON.

```bash
.venv-build\Scripts\python.exe tools\empacotar_mcpb.py
```

Gera `dist\CapturadorEvidencias.mcpb` (cerca de 24 MB, com as dependências embutidas). Para
instalar, dê dois cliques no arquivo: o Claude desktop abre o diálogo de instalação e pergunta a
**pasta das evidências** (a mesma do app); o Claude só enxerga o que estiver dentro dela. Depois é
só conversar no chat: *"Analise o teste mais recente e gere o relatório em PDF"*.

- Validado com o validador oficial (`npx @anthropic-ai/mcpb validate`) e executado como processo
  pelo Python do sistema **sem** o pacote `mcp` instalado
  (`python tools\testar_mcp.py --bundle <pasta extraída>`).
- Limitações: só Windows; o pacote carrega dependências compiladas e só roda com a **mesma versão
  do Python** em que foi empacotado (3.14), então refaça o pacote se o Python mudar; usa o
  comando `python` do PATH; não é assinado, então o Claude pode exibir um aviso.
- Se não iniciar, veja `%APPDATA%\Claude\logs\mcp-server-*.log`. Em contas de equipe/empresa, o
  administrador pode restringir extensões.
- Instalada e usada no Claude desktop: leu uma pasta de evidências, listou os testes e fez a análise.

#### Segurança da extensão

A extensão é um processo local com as **permissões do seu usuário** (a documentação da Anthropic
não descreve isolamento; trate-a como um programa comum). O que foi feito para reduzir o risco:

- **Código próprio**: sem rede e sem execução de comandos (conferido por busca nos módulos
  empacotados). Lê só os PNGs dos testes dentro da pasta configurada e escreve só PDF/`.md`
  novos nela, sem sobrescrever. O confinamento foi testado com `..`, caminhos absolutos, nomes
  adulterados no `evidencias.json` e links simbólicos.
- **Dependências**: 32 pacotes de terceiros, **travados com hash** em `requirements-mcpb.lock` e
  instalados só como pacotes prontos (`--only-binary`), sem compilar nada. Um pacote adulterado
  no PyPI é recusado: testado trocando todos os hashes, o `pip` falhou e não instalou nada.
  `pip-audit` não achou vulnerabilidades conhecidas nessas versões.
- **Integridade**: o empacotador grava o SHA-256 em `dist\CapturadorEvidencias.mcpb.sha256`.
- **Pasta obrigatória**: sem pasta configurada o servidor **recusa** trabalhar. Antes havia um padrão
  que apontava para as evidências reais e foi aceito sem querer; ele foi removido. A ferramenta
  `listar_testes` informa qual pasta está sendo lida (pergunte ao Claude: *"qual pasta você está
  lendo?"*).
- **Revisão independente do código** (um revisor que não participou da escrita), com correções e
  testes de regressão em `tests\test_revisao_seguranca.py`:
  - o Markdown do relatório não trava mais com texto adversarial (tempo linear; 0,01 s em 200 mil
    caracteres);
  - imagens: só PNG de verdade e com limite de pixels (um arquivo "bomba" ou de outro formato é
    recusado);
  - gravação do relatório com criação exclusiva e trava: duas gravações simultâneas não se
    sobrescrevem (testado com 6 chamadas ao mesmo tempo);
  - pasta de teste que é atalho/junção para fora da pasta de evidências é recusada;
  - `evidencias.json` adulterado: tamanho máximo, número máximo de evidências e texto saneado
    (caracteres de controle e de inversão de direção);
  - o servidor roda com o Python em modo isolado (`-I -B`).
- O empacotador confere, antes de gerar o `.mcpb`, que o servidor importa a partir do pacote (um
  módulo esquecido na lista derrubaria a extensão), e um teste cobre essa lista.

Para **atualizar as dependências** (num ambiente com `pip-tools` e `pip-audit`):

```bash
pip-compile --generate-hashes --strip-extras --output-file requirements-mcpb.lock requirements-mcp.txt
pip-audit -r requirements-mcpb.lock --no-deps --disable-pip
```

e depois reempacote. O que **não** some, e o que fazer:

1. **Os dados vão para a IA.** Os prints chegam à Anthropic pelo chat. Confirme com a TI se isso é
   permitido (LGPD/política), mascare dados sensíveis e comece pela pasta de exemplo.
2. **Texto dentro dos prints pode tentar instruir a IA** (injeção de prompt). A extensão limita
   o estrago (só cria PDFs na pasta dos testes), mas, com outros conectores ligados na mesma
   conversa (Drive, Gmail...), o risco cresce: analise evidências numa conversa só com esta
   extensão e não use "sempre permitir" na ferramenta que grava o PDF.
3. **Instale só o `.mcpb` que você mesmo gerou** e confira o SHA-256. Nunca instale um `.mcpb` de
   terceiros sem revisar o código.
4. **Política da empresa**: administradores de contas de equipe/empresa podem restringir
   extensões; instalar uma extensão local numa máquina corporativa pode exigir aval da TI.

**Estado**: protótipo em uso pessoal. Testado pelo protocolo com um cliente MCP (handshake,
ferramentas, imagem, PDF, recusa de caminhos fora da pasta) e usado no Claude desktop, mas **não
incluído no `.exe`** (um `.exe` sem janela não tem stdio; empacotar pede um executável de console
à parte).

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
