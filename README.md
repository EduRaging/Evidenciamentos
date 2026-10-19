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
3. **Finalizar teste** cria, dentro da pasta base (padrão: `Documentos\Evidencias`):

   ```
   2026-10-09_1432 - Nome do teste\
       01_tela.png
       02_recorte.png
       Evidencias - Nome do teste.pdf
   ```

   O PDF tem uma capa (nome, data, testador, quantidade) e uma evidência por página, com
   data/hora e tipo (tela inteira ou recorte).

## Aba "Meus testes"

A segunda aba da janela principal lista **um item por teste** da pasta de evidências, do mais
recente para o mais antigo, com a data, o nome e um ✓ em cada tipo de PDF: **Evid.** (o PDF de
evidências, que o app gera ao finalizar), **Relat.** (o relatório de testes que o Claude grava pela
extensão) e **Sug.** (as sugestões de casos de teste, também do Claude); "✓ 2" quando há mais de
um do mesmo tipo. A lista se atualiza sozinha enquanto a aba está à vista (a cada ~6 s), mantendo a seleção,
então um relatório criado por fora aparece sem fazer nada. O campo de busca ignora acentos e
combina palavras ("relatorio despesa"), olhando também os nomes dos PDFs.

Só dois botões ficam à vista, e o resto está em **Mais ▾** (ou no clique direito):

| Botão / ação | O que faz |
|---|---|
| **Enviar ao Claude** | abre a janela do prompt para os testes selecionados (veja abaixo) |
| **Abrir PDF** | abre o relatório mais recente do teste (ou o de evidências, se não houver relatório; as sugestões nunca abrem por aqui); também com dois cliques ou Enter |
| **Mais ▾ › Evidências / Relatório / Sugestões** | para cada PDF do teste: Abrir, **Copiar arquivo** (cole com Ctrl+V num e-mail, no Teams ou numa pasta), **Salvar cópia…**, **Enviar por e-mail…** e Copiar caminho |
| **Mais ▾ › Mostrar a pasta do teste** | abre o Explorador de Arquivos com o PDF selecionado |
| **Mais ▾ › Arquivar teste…** | move a pasta para `_arquivo`, dentro da pasta de evidências, **sem apagar nada** (para desfazer, mova a pasta de volta). O teste sai da lista e do alcance do Claude (ele ignora pastas que começam com `_`). Funciona com vários testes de uma vez; se um PDF ou imagem estiver aberto em outro programa, o Windows recusa e o app avisa |
| **Mais ▾ › Abrir a pasta dos arquivados** | abre `_arquivo` |

O padrão de e-mail do Windows (`mailto:`) não permite anexar arquivos, por isso o anexo é feito
colando o PDF já copiado.

**Enviar ao Claude** — com **Ctrl** ou **Shift** o senhor seleciona **vários testes** (até 12 por
vez). O Claude lê as **imagens** da pasta de cada teste pela extensão (não o conteúdo dos PDFs). O
prompt pede **um relatório por teste, salvo na pasta do próprio teste** (não um consolidado, e com
as sugestões num segundo PDF, veja abaixo), um teste por vez, e ao final uma tabela com o status
sugerido e o caminho de cada PDF. Os detalhes
(sistema/ambiente, objetivo, critérios e observações) valem para todos os testes selecionados.
Testes sem imagens são ignorados com aviso. Com vários testes só existe o modo "Claude com a
extensão" (com anexos não dá para misturar testes), e o Claude pode pedir permissão para gravar
cada PDF (dois por teste, com as sugestões ligadas). Se o texto não couber no limite de ~12 mil caracteres do link, o app copia o prompt
para colar.

## A janela "Capturar"

O nome do teste, os dois botões de captura (com os atalhos) e, logo abaixo, as **evidências da
sessão com miniatura**, numeradas, com o tipo e a hora. Enquanto não há nenhuma, a área mostra um
convite em vez de uma tabela vazia. Duplo clique (ou Enter) abre a imagem; **Delete** (ou o clique
direito) remove a selecionada. A ação principal é **Finalizar teste**, que mostra quantas
evidências entram e só liga quando há ao menos uma; **Descartar** e **Configurações** são
secundárias. Ao finalizar, a janela de conclusão oferece **Criar ciclo de testes** como ação principal
(veja a próxima seção) e, ao lado, **Relatório com o Claude…**.

## Ciclos de teste (o roteirizador)

Um **ciclo** é uma *rodada de testes*. O senhor **só fornece as telas**, capturadas e finalizadas do
jeito de sempre; daí em diante é **automático**, até a hora de executar e evidenciar o ciclo de novo.

1. Ao finalizar um teste, clique em **Criar ciclo de testes** (ou, em **Meus testes**, selecione
   o(s) teste(s) e use **Mais ▾ › Criar ciclo de testes**). O ciclo nasce sem formulário: o nome
   vem do teste ("Ciclo - Login no ERP") e as telas viram as **telas de referência**.
2. O **app chama o Claude sozinho** (sem abrir o Claude desktop, sem prompt, sem Enter). Na aba
   **Ciclos** o ciclo mostra "gerando…" enquanto o Claude trabalha (alguns minutos); o app continua
   livre para capturar, e dá para cancelar em **Mais ▾**.
3. Quando termina, o roteiro aparece ("5 casos") com um aviso; **Ver roteiro** abre a janela com os
   casos e a definição do ciclo, e **Salvar o roteiro em PDF** gera um documento formal (feito pelo
   app, não pela IA) na pasta do ciclo.

**Como o app chama o Claude.** Ele roda o **Claude Code que já vem com o Claude desktop** (em
`%APPDATA%\Claude\claude-code`), em modo **não interativo e restrito**: só a ferramenta `Read`, sem
MCP, sem skills, sem ler as suas configurações, sem sessão salva, com tudo o que pediria permissão
negado e com teto de gasto. Ele roda numa **pasta temporária** que tem só **cópias reduzidas das telas**
(no máximo 40; PNGs de verdade, nada mais do teste), apagada ao fim. A IA devolve **só um JSON**; **o
app valida e grava** o roteiro (a IA não escreve arquivo nenhum). Não usa chave de API: usa a **conta do
Claude Code** do senhor, que precisa estar conectada **uma vez** (`claude auth login`; o app oferece
abrir o login na primeira vez).

**Autorização.** As telas **saem do computador** nesse momento. Na primeira geração o app pergunta se
pode enviá-las (e lembra de dados sensíveis e da política da empresa); a resposta fica salva e dá para
**revogá-la** em **Mais ▾**. Sem a autorização, sem o Claude Code ou sem o login, nada é enviado e o
app oferece o plano B: **Pedir o roteiro no Claude desktop (manual)**, que abre o pedido preenchido e
exige o Enter do senhor (e a extensão, veja abaixo).

**O que o Claude entrega**, no padrão do CTFL 4.0 (o programa do BSTQB):
- **Casos de teste** atômicos, cada um com ID (CT-01…), título, objetivo, **técnica** (partição de
  equivalência, valor limite, tabela de decisão, transição de estado, cenário, adivinhação de erros
  etc.), **prioridade por risco**, pré-condições, dados de teste (fictícios), **passos com a ação e
  o resultado esperado de cada um**, pós-condições, rastreio e as telas que o motivaram. Quando a
  regra não aparece nas telas, o caso vem marcado "resultado esperado a confirmar".
- A **definição do ciclo** que o senhor não preencheu: objetivo, escopo, riscos e os **critérios de
  entrada e de saída**. O que o senhor preencher sempre vale mais; o que faltar vem da IA e, nos
  critérios, do padrão do CTFL. A janela marca a origem de cada parte ("proposto pela IA", "padrão
  do CTFL").
- **Dúvidas e hipóteses** a confirmar.

**Ajustes opcionais.** O botão **+ Novo ciclo** (aba Ciclos) permite escolher várias telas e, em
**Ajustar parâmetros**, informar tipo de rodada (funcional, regressão, confirmação de correção ou
fumaça), sistema, versão, ambiente, testador, período, objetivo, escopo e critérios.

**Onde fica:** `<pasta de evidências>\_ciclos\<data> - <nome>\` com o `ciclo.json` (parâmetros) e um
`roteiro-001.json` por geração (gerar de novo cria o 002; nada é sobrescrito). A pasta começa com `_`
de propósito: o registro de testes e a leitura do Claude a ignoram.

**Segurança.** O roteiro é um **rascunho da IA**: revise antes de executar. O app **valida tudo ao
gravar e de novo ao ler** (tipos, tamanhos, IDs únicos, textos de uma linha sem caracteres de controle
ou de direção, nomes de pasta simples); um roteiro adulterado é pulado, e nada inválido é gravado.
Como a IA só tem `Read` numa pasta com imagens, texto escondido numa tela no máximo distorce o roteiro:
não alcança arquivos, comandos nem a rede. **Atenção à rede:** neste fluxo o app **inicia um processo
(o Claude Code) que se conecta à Anthropic**; a medição de "zero conexões externas" abaixo vale para o
app e a extensão sem esse fluxo, e a TI precisa saber disso. O modo restrito foi aceito pelo Claude Code
instalado (versão 2.1.299), mas o caminho de sucesso real depende do login do senhor e **ainda não foi
exercitado com o Claude de verdade**.

**Plano B (manual) e a extensão.** Pelo Claude desktop, a extensão ganhou a ferramenta `salvar_casos`,
que só grava `roteiro-NNN.json` dentro de `_ciclos\<ciclo>`, só em pasta com `ciclo.json` válido, com
criação exclusiva, trava, teto de 30 roteiros e a mesma validação estrita. Exige **reinstalar a
extensão** (`dist\CapturadorEvidencias.mcpb`); se a instalada for antiga, o app avisa antes de pedir.

**Próximas etapas (ainda não feitas):** execução guiada do ciclo (passo a passo, com a evidência
ligada ao passo e o resultado de cada caso), relatório de execução do ciclo com a checagem dos
critérios de saída e as métricas do CTFL.
## Prompt para IA (casos de teste e relatório)

O app não se conecta a nenhuma IA: ele monta um **prompt pronto** para o senhor enviar ao Claude
desktop (um clique abre a conversa com o texto preenchido) ou colar na IA que preferir (e que a
empresa aprove). Sem chave de API e sem custo, e sem tráfego de rede do app (a exceção é a geração automática do roteiro dos ciclos, que usa o Claude Code; veja a seção Ciclos).

1. Ao finalizar um teste, clique em **Enviar ao Claude…** (ou, na aba **Meus testes**, selecione o(s)
   teste(s) e use **Enviar ao Claude**; na janela do prompt, **Trocar…** escolhe outro teste).
2. A janela abre **só com o essencial**: o(s) teste(s), uma linha-resumo do que o Claude vai gerar
   e o botão **Enviar ao Claude** (mais **Copiar prompt**). O resto fica recolhido e abrir uma
   seção fecha as outras: **Alterar** (as opções abaixo), **Adicionar detalhes do teste** (sistema/
   ambiente, objetivo, critérios de aceite e observações, tudo opcional) e **Ver o texto que será
   enviado** (a prévia, que atualiza enquanto o senhor digita). Em **Alterar** o senhor escolhe o que
   a IA deve gerar: casos de teste, relatório de execução ou os dois. A caixa **Pedir a entrega em PDF** (marcada por padrão) faz o
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
   **Dois PDFs, cada um com o seu assunto.** Com a entrega em PDF e as sugestões ligadas (o padrão),
   o resultado sai separado: o **Relatório de testes** (casos executados e relatório de execução,
   com as imagens anexadas ao final) e as **Sugestões de casos de teste** (os casos sugeridos, as
   perguntas ao testador e, se a automação estiver marcada, a tabela de avaliação; sem repetir as
   imagens). Cada um fica na pasta do teste e aparece em coluna própria em **Meus testes**. Sem as
   sugestões, ou sem a entrega em PDF, volta a ser um documento só.
   A caixa **Avaliar o que é automatizável e gerar código Playwright (Python)** (desmarcada por
   padrão) pede à IA uma **tabela que deixa claro, para cada caso (executados e sugeridos), se dá
   para automatizar** (Sim, Parcial ou Não), por quê, o que falta (URL, login, dados) e a
   estabilidade esperada, com a soma no fim. "Não" só com motivo concreto (julgamento visual,
   CAPTCHA, código por SMS/e-mail, terceiros, impressão/arquivo, resultado ambíguo, exploratório);
   na dúvida, "Parcial". Se as telas não forem de uma aplicação web, a IA avisa que o Playwright
   não se aplica e não gera código. Para os casos "Sim" e "Parcial" ela gera `conftest.py` e
   `test_*.py` com **pytest-playwright**: seletores pelo que o usuário vê (`get_by_role`,
   `get_by_label`, `get_by_text`), sem esperas fixas, valores limite e partições como
   `@pytest.mark.parametrize`, ID do caso e evidência na docstring, e `# NÃO VERIFICADO` em tudo
   que ela só adivinhou pela imagem (confira com `playwright codegen`). URL, usuário e senha
   **nunca** vão no código (variáveis `BASE_URL`, `TESTE_USUARIO`, `TESTE_SENHA`), os dados são
   fictícios e testes que alteram dados levam o marcador `altera_dados`. A tabela entra no
   relatório em PDF; o código vem no chat, em blocos por arquivo. **É rascunho a revisar antes de
   rodar** (um texto escondido numa imagem poderia tentar influenciar o código), só em homologação.
3. **Enviar ao Claude** abre o **Claude desktop** numa conversa nova **com o prompt já preenchido**:
   o senhor só confere e aperta Enter (o Claude apenas preenche a caixa; nada sai do computador
   antes disso). Com a extensão do Claude instalada (veja abaixo), a caixa **Claude com a extensão
   instalada** (marcada por padrão) faz o prompt mandar a IA ler as evidências direto da pasta e
   gravar o PDF lá, sem anexar nada. A janela confere, nos arquivos do Claude desktop, se a
   extensão está instalada, **ativada** (Configurações > Extensões) e lendo a **mesma pasta** do
   teste; se não estiver, mostra um aviso em vermelho e pergunta antes de enviar (sem isso o
   Claude responde que não tem as ferramentas). Sem a extensão, desmarque a caixa: o prompt volta
   ao formato de anexos.
   Se o prompt passar de ~12 mil caracteres (limite do link do Claude) ou o Claude desktop não
   estiver instalado, o app copia o prompt e avisa para colar (Ctrl+V).
   Para outra IA, use **Copiar prompt**, cole e **anexe o PDF** do teste (ele já traz as evidências
   numeradas e com data/hora; o prompt se refere a "Evidência N"). Se a IA não ler imagens dentro
   de PDF, anexe os PNGs numerados da pasta do teste (**Mais ▾ › Mostrar a pasta do teste**, na aba Meus testes).

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
| `salvar_casos` | grava o roteiro de testes (os casos) de um **ciclo** em `_ciclos\<ciclo>\roteiro-NNN.json` (veja "Ciclos de teste") |

Há também o prompt `analisar_teste`, com as instruções completas (mesmas regras do prompt colado,
inclusive as sugestões de casos adicionais ISTQB/BSTQB; `sugerir_casos=false` as desliga), e o prompt
`gerar_roteiro`, que pede o roteiro de testes de um ciclo.

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
  novos nela e, para os ciclos, `roteiro-NNN.json` novos em `_ciclos`, sem sobrescrever. O
  confinamento foi testado com `..`, caminhos absolutos, nomes adulterados no `evidencias.json` e
  links simbólicos. (A ferramenta `salvar_casos` e a validação do roteiro entraram depois da revisão
  independente de segurança: eles seguem os mesmos padrões, com testes próprios, mas **não foram
  revisados por terceiros**.)
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
