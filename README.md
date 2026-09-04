# Tarjador de PDFs

Você abre um PDF, arrasta o mouse desenhando as tarjas por cima dos CPFs, salva.
Tudo roda na sua máquina — nenhum arquivo sai daqui.

## Usar

1. Jogue os PDFs na pasta `input/`
2. Abra o programa:
   - **Windows:** dois cliques em `Tarjador.bat`
   - **Linux / macOS:** `./tarjador.sh` (na primeira vez, `chmod +x tarjador.sh`)
3. Duplo clique no arquivo na lista da esquerda
4. Arraste o mouse sobre cada CPF (a tarja preta aparece na hora)
5. **SALVAR EM OUTPUT** → sai em `output/nome_tarjado.pdf`

O original em `input/` nunca é alterado. Se o nome de saída já existir, ele cria
`_2`, `_3`, e assim por diante — nada é sobrescrito.

## A tarja não é removível

Não é um retângulo preto colado por cima — isso é o erro clássico de vazamento
de documento, porque o texto continua lá embaixo e sai num Ctrl+C. Aqui, ao
salvar, o conteúdo é **destruído no arquivo**. Especificamente:

| Onde o CPF pode estar escondido | O que o programa faz |
|---|---|
| Texto sob a tarja | Removido (`apply_redactions`) |
| **CPF dentro de foto / documento escaneado** | **Pixels pintados de preto dentro da própria imagem** (ver abaixo) |
| Vetores/linhas encostando na tarja | Removidos |
| Campo de formulário | O campo é apagado antes de salvar |
| Comentário / anotação / link | Apagados |
| Miniatura embutida da página (`/Thumb`) | Apagada |
| Metadados (título, assunto, palavras-chave) e XMP | Zerados |
| Revisões antigas e objetos órfãos do PDF | Descartados (`garbage=4`, `clean`) |

### CPF em foto: a parte que mais importa

Este é o caso mais perigoso, e a armadilha é traiçoeira. Se você só desenha a
tarja por cima de uma foto, o PDF continua guardando **o arquivo de imagem
original inteiro** lá dentro. A página *parece* preta, mas quem extrair as
imagens do PDF (uma linha de código) vê a foto sem tarja nenhuma.

Pior: a opção do PyMuPDF que deveria apagar só os pixels tarjados
(`PDF_REDACT_IMAGE_PIXELS`) **não funciona** na versão atual — testei
isoladamente e a imagem sai intacta. E a alternativa apagaria a foto inteira.

Então o programa faz na mão, e de forma irreversível:

1. localiza onde a tarja cai **dentro** da imagem (invertendo a matriz de
   posicionamento, então rotação e espelhamento não enganam);
2. abre os pixels da imagem, **pinta a região de preto sólido**, destruindo os
   pixels originais;
3. reescreve o arquivo de imagem dentro do PDF (`replace_image`).

Os bytes da foto original deixam de existir no arquivo — não ficam escondidos
embaixo do preto. A página continua com o texto selecionável.

**Por que preto e não borrão:** desfoque e pixelização são *reversíveis*.
Existem ataques que reconstroem o número a partir do borrão, e um CPF é o alvo
ideal para isso — poucos dígitos, alfabeto conhecido, formato fixo. Preto
sólido não tem o que reconstruir.

Se por algum motivo a imagem não puder ser reescrita (formato exótico, imagem
sem referência própria), o programa **rasteriza aquela página** automaticamente
em vez de salvar algo inseguro.

### Rasterizar páginas tarjadas (checkbox, ligado por padrão)

Camada extra: converte a página tarjada inteira em imagem chapada de 200 DPI.
Numa página assim não existe objeto de texto nenhum — nem invisível, nem em
codificação exótica, nem num canto do PDF que ninguém lembrou de olhar.

Custo: a página fica visualmente idêntica, mas **não dá mais para selecionar ou
buscar texto nela**, e o arquivo cresce (no teste, 107 KB contra 37 KB).

**Não é necessário para fotos** — elas já são pintadas por dentro. Desmarque
sem medo se quiser manter o texto selecionável; o modo normal foi testado
contra todos os vetores da tabela acima, incluindo CPF dentro de foto, e
passou.

### Conferência automática

Depois de salvar, o programa reabre o arquivo gerado e verifica:

- se sobrou texto sob alguma tarja;
- **extrai as imagens do arquivo salvo e olha os pixels sob cada tarja** — se o
  mais claro passar de 40 (de 255), acusa;
- se ainda há CPFs **não tarjados** no resto do documento.

Se achar qualquer coisa, ele avisa em vez de dizer que deu certo.

## O que ele não faz por você

A tarja é sua responsabilidade: o programa garante que o que você cobriu some
de verdade, não que você cobriu tudo. Passe o olho em todas as páginas antes de
enviar — principalmente em documento escaneado, onde o "Detectar CPFs" não
enxerga nada.

**Uma foto repetida em várias páginas é o mesmo objeto dentro do PDF.** Se você
tarjar ela numa página, ela sai tarjada em todas. Isso é o lado seguro do erro
(o CPF é o mesmo, afinal), mas vale conferir se não atrapalha em algum
documento.

## Controles

| Ação | Como |
|---|---|
| Desenhar tarja | Arrastar com o botão esquerdo |
| Apagar uma tarja | Botão **direito** em cima dela |
| Desfazer | `Ctrl+Z` |
| Limpar a página inteira | Botão "Limpar pagina" |
| Trocar de página | Botões `<` `>` ou `Page Up` / `Page Down` |
| Zoom | Botões `-` `+` ou `Ctrl` + roda do mouse |
| Rolar | Roda do mouse (`Shift` + roda = horizontal) |
| Salvar | `Ctrl+S` ou o botão azul |
| Abrir outro PDF | `Ctrl+O` |

As tarjas de todas as páginas ficam guardadas até você salvar — dá para
percorrer o documento inteiro e salvar tudo de uma vez, num arquivo só.

## Botão "Detectar CPFs"

Atalho opcional: procura no texto da página o que tem cara de CPF
(`000.000.000-00`, `000 000 000 00` ou 11 dígitos seguidos) e já desenha as
tarjas. Elas são tarjas comuns — dá para apagar com o botão direito se pegar
algo errado.

Dois cuidados:

- **Não funciona em PDF digitalizado** (imagem sem camada de texto). Nesse caso
  a mensagem avisa e você tarja na mão.
- É um auxílio, não uma garantia. **Confira a página antes de salvar** — o CPF
  pode estar escrito num formato que o padrão não pega, ou dentro de uma imagem.

## Requisitos

Python 3.8+ com `tkinter`, `PyMuPDF` e `Pillow`. O mesmo `tarjador.py` roda nos
três sistemas — os lançadores só cuidam da instalação.

**Windows** — `Tarjador.bat` instala sozinho na primeira vez.

**Linux** — o `tkinter` não vem pelo pip, é pacote da distro. O `tarjador.sh`
detecta e diz o comando certo para a sua:

```bash
sudo apt install python3-tk     # Debian/Ubuntu (dnf, pacman, zypper e apk também são reconhecidos)
chmod +x tarjador.sh
./tarjador.sh
```

Nas distros que marcam o Python como *externally managed* (PEP 668), o pip do
sistema recusa instalar. O script percebe isso e cria um `.venv` local
automaticamente, com `--system-site-packages` para enxergar o `tkinter` da
distro. Não precisa fazer nada — e da segunda vez em diante ele já usa o `.venv`
direto.

**macOS** — `./tarjador.sh` também funciona; se faltar o tkinter, ele sugere
`brew install python-tk`.

Instalação manual, em qualquer sistema:

```bash
python3 -m pip install -r requirements.txt
python3 tarjador.py
```

### Notas de portabilidade

Três coisas que o código trata explicitamente por causa das diferenças entre
sistemas — anotadas aqui para quem for mexer:

| Diferença | Tratamento |
|---|---|
| Roda do mouse | Windows e macOS mandam `<MouseWheel>`; o X11 do Linux manda `Button-4`/`Button-5`. Sem a tradução, rolagem e `Ctrl`+zoom não responderiam no Linux. |
| Fonte da interface | "Segoe UI" só existe no Windows. Usa a fonte padrão do sistema, resolvida em tempo de execução. |
| Largura dos textos | A opção "Rasterizar" fica na barra lateral, não na barra de cima: a fonte do Linux é mais larga e o texto era cortado quando disputava espaço com os botões. |
| Abrir a pasta `output/` | `os.startfile` no Windows, `open` no macOS, `xdg-open` no Linux. |

⚠️ **O `tarjador.sh` precisa estar com terminações de linha LF.** Se o arquivo
passar por algum lugar que converta para CRLF (um zip no Windows, um editor
mal configurado), o Linux reclama de `bad interpreter` e o script nem roda.
Conserta com `sed -i 's/\r$//' tarjador.sh` ou `dos2unix tarjador.sh`.

## Testes

```bash
python3 testes/rodar_testes.py          # roda tudo
python3 testes/rodar_testes.py --lista  # lista os casos
```

Num Linux sem tela (servidor, container), a interface precisa de um display
falso: `xvfb-run -a python3 testes/rodar_testes.py`.

Os testes são auto-contidos — geram os próprios PDFs em pasta temporária e não
encostam no seu `input/`/`output/`. Os CPFs usados são fictícios.

| Caso | O que prova |
|---|---|
| `texto` | CPF em texto some do arquivo; o resto do texto fica |
| `blindagem_normal` / `_raster` | Os 5 esconderijos de uma vez: texto, metadado, campo de formulário, anotação e imagem |
| `foto_normal` | **O principal:** varre todos os objetos do PDF salvo atrás de sobras da foto original, e confere que não rasterizou à toa |
| `foto_raster` | O mesmo, com a rasterização ligada |
| `foto_rot90/180/270` | O mapeamento dentro da imagem aguenta rotação |
| `salvar` | Não sobrescreve arquivo existente |
| `interface` | Roda do mouse (inclusive `Button-4/5` do X11), fonte, coordenadas, desenhar/apagar/desfazer |

O truque do teste de foto: o CPF é desenhado sobre uma faixa **magenta puro**.
Depois de salvar, qualquer pixel magenta que apareça em qualquer objeto do
arquivo denuncia uma cópia sobrevivente da imagem original.

**Onde eles rodaram:**

| Ambiente | Resultado |
|---|---|
| Windows 11, Python 3.12 | 10/10 |
| Ubuntu 26.04 (WSL2), Python 3.14, X11 via Xvfb | 10/10 |

No Linux foi validado o caminho completo, não só a lógica de tarja: o
`tarjador.sh` detectando a falta do `tkinter` e saindo com código 1, o fallback
do PEP 668 criando o `.venv` sozinho, a interface subindo sob X11, e os eventos
`Button-4/5` disparados de verdade com `event_generate` (rolagem, `Ctrl`+zoom e
arrasto do mouse desenhando a tarja).
