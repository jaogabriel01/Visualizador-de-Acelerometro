# Visualizador de Acelerômetro

Aplicativo desktop em Python para carregar arquivos CSV de acelerômetro, visualizar os dados em gráficos e exportar um relatório em PDF. A interface é simples: escolha o arquivo, navegue pelas abas e, se quiser, exporte o relatório.

## Funcionalidades

- **Carregamento de CSV** com um clique (ou `Ctrl+O`). Aceita arquivos grandes: os exemplos testados têm de 79 mil a 586 mil amostras.
- **Resumo dos dados:** número de amostras, duração, taxa média de amostragem, intervalo típico entre amostras e uma tabela com mínimo, máximo, média, desvio-padrão e amostras saturadas de cada eixo e da magnitude.
- **Gráficos em abas:**
  | Aba | O que mostra |
  |---|---|
  | **Eixos** | `ax`, `ay` e `az` ao longo do tempo, em painéis separados |
  | **Magnitude** | \|a\| = √(ax² + ay² + az²) ao longo do tempo, com a referência de 1 g |
  | **Distribuição** | Histograma de cada eixo, com a média marcada |
  | **Espectro** | Espectro de amplitude por frequência (método de Welch, janela de Hann, sem componente contínua) |
  | **Amostragem** | Intervalo entre amostras no tempo e seu histograma, útil para checar a regularidade da coleta |
- **Zoom fluido:** a barra de cada gráfico oferece zoom, mover, restaurar a vista e salvar como imagem. Séries longas são reduzidas por mínimo e máximo, então os picos não desaparecem, e o gráfico ganha detalhe conforme você amplia.
- **Escala inteligente:** por padrão, os 0,05 % de valores mais extremos ficam fora da escala para que ruídos de saturação não achatem o sinal. Uma nota no gráfico informa quantas amostras ficaram fora da vista. A caixa **"Mostrar picos extremos (escala total)"** exibe tudo.
- **Exportação em PDF:** relatório A4 paisagem com uma capa de resumo e todos os gráficos, com o nome do arquivo e a numeração de páginas.
- **Voltar ao início:** o botão **"← Novo arquivo"** devolve à tela inicial para carregar outro CSV sem reabrir o programa.

## Requisitos

- Python 3.9 ou superior
- Bibliotecas: `pandas`, `numpy`, `matplotlib`
- Tkinter (já incluído no Python do Windows e do macOS; no Linux é um pacote do sistema)

```bash
pip install pandas numpy matplotlib
```

No Linux, instale o Tkinter se ele não estiver disponível:

```bash
# Debian / Ubuntu
sudo apt install python3-tk

# Arch / CachyOS
sudo pacman -S tk
```

## Como usar

```bash
python visualizador_acelerometro.py
```

Também é possível abrir um arquivo direto:

```bash
python visualizador_acelerometro.py caminho/do/arquivo.csv
```

1. Na tela inicial, clique em **Selecionar arquivo CSV…**.
2. Veja o **Resumo** e navegue pelas abas de gráficos.
3. Use a barra de ferramentas do gráfico para ampliar trechos de interesse.
4. Clique em **Exportar PDF** para salvar o relatório com todos os gráficos.
5. Clique em **← Novo arquivo** para carregar outro CSV.

## Formato do CSV

O arquivo precisa ter cabeçalho e as colunas de aceleração `ax`, `ay` e `az`. A coluna de tempo é opcional, mas necessária para o espectro e para a análise de amostragem.

```csv
idx,t_us,ax,ay,az
0,578,-0.2532,0.4890,-0.0615
1,1345,-0.1492,0.3438,-0.0762
2,2325,-0.1975,0.4070,0.0264
```

- **Colunas de aceleração:** `ax`, `ay`, `az` (também são aceitos `x`, `y`, `z` e `acc_x`, `acc_y`, `acc_z`).
- **Colunas de tempo reconhecidas:** `t_us` (microssegundos), `t_ms` (milissegundos) e `t_s` (segundos). Outros nomes aceitos: `time_us`, `time_ms`, `time_s`, `tempo_s` e `t` (em segundos).
- **Sem coluna de tempo:** os gráficos usam o número da amostra no eixo horizontal, e as abas de espectro e amostragem ficam indisponíveis.
- Colunas extras (como `idx`) são ignoradas e linhas com valores inválidos são descartadas.

## Observações

- **Unidade:** os valores são tratados como **g** (1 g ≈ 9,81 m/s²).
- **Saturação:** amostras com valor absoluto igual ou maior que 7,99 g são contadas como saturadas, considerando o fundo de escala de ±8 g dos sensores dos exemplos. Para outro sensor, ajuste as constantes `FUNDO_ESCALA` e `LIMITE_SAT` no início do código.
- **Espectro:** a taxa de amostragem usada é a média calculada a partir do tempo do arquivo. Pequenas variações no intervalo entre amostras não são corrigidas por reamostragem.

## Tecnologias

- [Python](https://www.python.org/)
- [Tkinter](https://docs.python.org/3/library/tkinter.html) para a interface
- [Matplotlib](https://matplotlib.org/) para os gráficos e para o PDF
- [NumPy](https://numpy.org/) e [pandas](https://pandas.pydata.org/) para leitura e cálculo
- [Claude Sonnet 5.5](https://claude.ai/)

---