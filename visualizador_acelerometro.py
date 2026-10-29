#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Visualizador de Acelerômetro
============================
Carrega um CSV de acelerômetro (colunas ax, ay, az e, de preferência, t_us),
mostra os gráficos em abas e exporta um relatório em PDF.

Dependências:  pip install pandas numpy matplotlib
(No Linux, o Tkinter vem de um pacote do sistema: python3-tk / tk.)

Uso:  python visualizador_acelerometro.py [arquivo.csv]
"""
import gc
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# --------------------------------------------------------------------------
# Configurações gerais
# --------------------------------------------------------------------------
EIXOS = ("ax", "ay", "az")
CORES = {"ax": "#e4572e", "ay": "#12a594", "az": "#3b5bdb", "mag": "#343a40"}
FUNDO_ESCALA = 8.0          # o sensor dos exemplos satura em ±8 g
LIMITE_SAT = FUNDO_ESCALA * 0.999
A4_PAISAGEM = (11.69, 8.27)

# Nomes alternativos aceitos para as colunas
ALIAS = {"x": "ax", "y": "ay", "z": "az", "acc_x": "ax", "acc_y": "ay", "acc_z": "az"}
# Coluna de tempo -> fator para converter em segundos
ESCALA_TEMPO = {"t_us": 1e-6, "time_us": 1e-6, "t_ms": 1e-3, "time_ms": 1e-3,
                "t_s": 1.0, "time_s": 1.0, "tempo_s": 1.0, "t": 1.0}

matplotlib.rcParams.update({
    "axes.grid": True, "grid.alpha": 0.25, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False,
    "font.size": 10, "axes.titlesize": 11, "figure.facecolor": "white",
})


# --------------------------------------------------------------------------
# Formatação (padrão brasileiro)
# --------------------------------------------------------------------------
def num(v, casas=3):
    return f"{v:.{casas}f}".replace(".", ",")


def inteiro(n):
    return f"{int(n):,}".replace(",", ".")


def duracao_txt(seg):
    total = int(round(seg))
    m, s = divmod(total, 60)
    return f"{m} min {s} s" if m else f"{num(seg, 1)} s"


# --------------------------------------------------------------------------
# Dados
# --------------------------------------------------------------------------
class Dados:
    def __init__(self, nome, t, x, y, z, tem_tempo):
        self.nome, self.t, self.tem_tempo = nome, t, tem_tempo
        self.eixo = {"ax": x, "ay": y, "az": z}
        self.mag = np.sqrt(x ** 2 + y ** 2 + z ** 2)
        self.n = len(t)
        self.duracao = float(t[-1] - t[0]) if tem_tempo else 0.0
        self.fs = (self.n - 1) / self.duracao if tem_tempo and self.duracao > 0 else None
        self.dt_ms = np.diff(t) * 1000.0 if tem_tempo else None

    def saturadas(self, eixo):
        return int((np.abs(self.eixo[eixo]) >= LIMITE_SAT).sum())

    def cartoes(self):
        c = [("Amostras", inteiro(self.n))]
        if self.tem_tempo:
            c.append(("Duração", duracao_txt(self.duracao)))
            if self.fs:
                c.append(("Taxa média", f"{num(self.fs, 0)} Hz"))
            c.append(("Intervalo típico", f"{num(np.median(self.dt_ms), 2)} ms"))
        return c

    def tabela(self):
        linhas = []
        for nome, v in [("ax", self.eixo["ax"]), ("ay", self.eixo["ay"]),
                        ("az", self.eixo["az"]), ("|a|", self.mag)]:
            sat = inteiro(self.saturadas(nome)) if nome in EIXOS else "—"
            linhas.append((nome, num(v.min()), num(v.max()), num(v.mean()),
                           num(v.std()), sat))
        return linhas


COLUNAS_TABELA = ("Eixo", "Mín (g)", "Máx (g)", "Média (g)", "Desvio (g)", "Saturadas")
NOTA_UNIDADE = ("Unidade assumida: g (1 g ≈ 9,81 m/s²). Amostras com valor absoluto "
                f"≥ {num(LIMITE_SAT, 2)} g são contadas como saturadas (fundo de escala ±{num(FUNDO_ESCALA, 0)} g).")


def carregar_csv(caminho):
    try:
        df = pd.read_csv(caminho)
    except Exception:
        df = pd.read_csv(caminho, sep=None, engine="python")
    df.columns = [ALIAS.get(str(c).strip().lower(), str(c).strip().lower()) for c in df.columns]

    faltando = [c for c in EIXOS if c not in df.columns]
    if faltando:
        raise ValueError("Colunas obrigatórias não encontradas: " + ", ".join(faltando) +
                         "\n\nColunas do arquivo: " + ", ".join(map(str, df.columns)))

    col_t = next((c for c in ESCALA_TEMPO if c in df.columns), None)
    usar = list(EIXOS) + ([col_t] if col_t else [])
    df = df[usar].apply(pd.to_numeric, errors="coerce").dropna()
    if len(df) < 16:
        raise ValueError("O arquivo tem poucas linhas válidas para gerar gráficos.")

    if col_t:
        t = df[col_t].to_numpy(float) * ESCALA_TEMPO[col_t]
        ordem = np.argsort(t, kind="stable")
        df, t = df.iloc[ordem], t[ordem]
        t = t - t[0]
    else:
        t = np.arange(len(df), dtype=float)
    x, y, z = (df[c].to_numpy(float) for c in EIXOS)
    return Dados(os.path.basename(caminho), t, x, y, z, bool(col_t))


# --------------------------------------------------------------------------
# Utilidades de gráfico
# --------------------------------------------------------------------------
def envelope(t, y, x0, x1, buckets):
    """Reduz a série ao intervalo [x0, x1] mantendo mínimos e máximos de cada
    faixa — assim picos nunca somem, mesmo com centenas de milhares de pontos."""
    if x0 > x1:
        x0, x1 = x1, x0
    i0 = max(int(np.searchsorted(t, x0, "left")) - 1, 0)
    i1 = min(int(np.searchsorted(t, x1, "right")) + 1, len(t))
    tt, yy = t[i0:i1], y[i0:i1]
    if len(tt) <= buckets * 2:
        return tt, yy
    b = len(tt) // buckets
    m = b * buckets
    T, Y = tt[:m].reshape(-1, b), yy[:m].reshape(-1, b)
    i_min, i_max = Y.argmin(1), Y.argmax(1)
    ini, fim = np.minimum(i_min, i_max), np.maximum(i_min, i_max)
    lin = np.arange(len(Y))
    xs, ys = np.empty(2 * len(Y)), np.empty(2 * len(Y))
    xs[0::2], ys[0::2] = T[lin, ini], Y[lin, ini]
    xs[1::2], ys[1::2] = T[lin, fim], Y[lin, fim]
    return xs, ys


class SeriesTempo:
    """Linhas no tempo que se redesenham com mais detalhe quando há zoom."""

    def __init__(self, buckets=1500):
        self.itens, self.buckets, self._conectados = [], buckets, set()

    def add(self, ax, t, y, **kw):
        xs, ys = envelope(t, y, t[0], t[-1], self.buckets)
        (linha,) = ax.plot(xs, ys, **kw)
        self.itens.append((linha, t, y))
        if ax not in self._conectados:
            ax.callbacks.connect("xlim_changed", self._atualizar)
            self._conectados.add(ax)
        ax.set_xlim(t[0], t[-1])
        return linha

    def _atualizar(self, ax):
        x0, x1 = ax.get_xlim()
        for linha, t, y in self.itens:
            linha.set_data(*envelope(t, y, x0, x1, self.buckets))


def limites(v, total):
    """Limites de exibição. Por padrão ignora os 0,05 % mais extremos para que
    glitches de saturação não achatem o sinal. Retorna (lo, hi, nº fora)."""
    if total:
        lo, hi = float(v.min()), float(v.max())
    else:
        lo, hi = (float(p) for p in np.percentile(v, [0.05, 99.95]))
    pad = (hi - lo) * 0.12 or 0.1
    lo, hi = lo - pad, hi + pad
    return lo, hi, int(((v < lo) | (v > hi)).sum())


def nota_escala(fig, fora, total):
    if fora and not total:
        fig.supxlabel(f"Escala ajustada ao sinal típico — {inteiro(fora)} amostra(s) extrema(s) "
                      "ficam fora da vista (a opção “Mostrar picos extremos” do aplicativo exibe tudo).",
                      fontsize=8, color="#777")


def mensagem(fig, texto):
    fig.text(0.5, 0.5, texto, ha="center", va="center", fontsize=13, color="#666")


def rotulo_tempo(d):
    return "Tempo (s)" if d.tem_tempo else "Amostra"


def espectro(v, fs):
    """Espectro de amplitude médio (método de Welch, janela de Hann)."""
    n = len(v)
    nper = int(2 ** np.floor(np.log2(max(64, min(8192, n // 8)))))
    janelas = np.lib.stride_tricks.sliding_window_view(v, nper)[:: nper // 2]
    janelas = janelas - janelas.mean(axis=1, keepdims=True)
    w = np.hanning(nper)
    pot = (np.abs(np.fft.rfft(janelas * w, axis=1)) ** 2).mean(axis=0)
    return np.fft.rfftfreq(nper, 1 / fs), 2 * np.sqrt(pot) / w.sum(), nper


# --------------------------------------------------------------------------
# Gráficos (cada função desenha numa Figure; servem para a tela e para o PDF)
# --------------------------------------------------------------------------
def fig_eixos(fig, d, total):
    axs = fig.subplots(3, 1, sharex=True)
    grupo, fora = SeriesTempo(), 0
    for ax, e in zip(axs, EIXOS):
        v = d.eixo[e]
        grupo.add(ax, d.t, v, color=CORES[e], lw=0.7)
        lo, hi, f = limites(v, total)
        ax.set_ylim(lo, hi)
        ax.set_ylabel(f"{e} (g)")
        fora += f
    axs[-1].set_xlabel(rotulo_tempo(d))
    nota_escala(fig, fora, total)
    fig._grupo = grupo      # mantém as séries vivas (callbacks usam referência fraca)


def fig_magnitude(fig, d, total):
    ax = fig.subplots()
    grupo = SeriesTempo()
    grupo.add(ax, d.t, d.mag, color=CORES["mag"], lw=0.7, label="|a| = √(ax² + ay² + az²)")
    ax.axhline(1.0, color="#e03131", ls="--", lw=1, label="1 g (gravidade)")
    lo, hi, fora = limites(d.mag, total)
    ax.set_ylim(min(lo, 0), hi)
    ax.set_xlabel(rotulo_tempo(d))
    ax.set_ylabel("Magnitude (g)")
    ax.legend(loc="upper right", frameon=False)
    nota_escala(fig, fora, total)
    fig._grupo = grupo


def fig_distribuicao(fig, d, total):
    axs = fig.subplots(1, 3)
    fora = 0
    for ax, e in zip(axs, EIXOS):
        v = d.eixo[e]
        lo, hi, f = limites(v, total)
        fora += f
        ax.hist(v, bins=80, range=(lo, hi), color=CORES[e], alpha=0.85)
        ax.axvline(v.mean(), color="#212529", ls="--", lw=1)
        ax.set_xlabel(f"{e} (g)")
        ax.set_title(f"média {num(v.mean(), 2)} g · desvio {num(v.std(), 2)} g")
    axs[0].set_ylabel("Nº de amostras")
    nota_escala(fig, fora, total)


def fig_espectro(fig, d, total):
    if not d.fs or d.n < 128:
        return mensagem(fig, "Espectro indisponível:\né preciso ter coluna de tempo e amostras suficientes.")
    ax = fig.subplots()
    for e in EIXOS:
        f, a, nper = espectro(d.eixo[e], d.fs)
        ax.plot(f[1:], a[1:], color=CORES[e], lw=0.9, label=e, alpha=0.9)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Frequência (Hz)")
    ax.set_ylabel("Amplitude (g)")
    ax.legend(frameon=False)
    ax.set_title(f"Resolução ≈ {num(d.fs / nper, 3)} Hz · máxima frequência = {num(d.fs / 2, 0)} Hz "
                 "· sem componente contínua (DC)", fontsize=9, color="#555")


def fig_amostragem(fig, d, total):
    if not d.tem_tempo:
        return mensagem(fig, "Sem coluna de tempo no arquivo.")
    ax1, ax2 = fig.subplots(1, 2, sharey=True, gridspec_kw={"width_ratios": [3, 1]})
    grupo = SeriesTempo()
    grupo.add(ax1, d.t[1:], d.dt_ms, color="#7048e8", lw=0.6)
    lo, hi, fora = limites(d.dt_ms, total)
    ax1.set_ylim(max(lo, 0), hi)
    ax1.set_xlabel("Tempo (s)")
    ax1.set_ylabel("Intervalo entre amostras (ms)")
    ax2.hist(d.dt_ms, bins=80, range=(max(lo, 0), hi), orientation="horizontal", color="#7048e8", alpha=0.85)
    med = float(np.median(d.dt_ms))
    ax2.axhline(med, color="#212529", ls="--", lw=1)
    ax2.set_xlabel("Nº de amostras")
    ax2.set_title(f"mediana {num(med, 2)} ms", fontsize=9)
    nota_escala(fig, fora, total)
    fig._grupo = grupo


ABAS = [("Eixos", "Aceleração por eixo", fig_eixos),
        ("Magnitude", "Magnitude da aceleração", fig_magnitude),
        ("Distribuição", "Distribuição dos valores", fig_distribuicao),
        ("Espectro", "Espectro de frequência", fig_espectro),
        ("Amostragem", "Regularidade da amostragem", fig_amostragem)]


def montar(fig, d, total, titulo, funcao):
    fig.suptitle(titulo, fontsize=14, weight="bold")
    funcao(fig, d, total)


# --------------------------------------------------------------------------
# Relatório em PDF
# --------------------------------------------------------------------------
def fig_capa(fig, d):
    ax = fig.add_subplot(111)
    ax.axis("off")
    ax.text(0, 0.98, "Relatório de dados do acelerômetro", fontsize=22, weight="bold", va="top")
    ax.text(0, 0.91, f"Gerado em {datetime.now():%d/%m/%Y às %H:%M}", fontsize=11, color="#555", va="top")
    y = 0.82
    info = [("Arquivo", d.nome)] + [(k, v) for k, v in d.cartoes()]
    for k, v in info:
        ax.text(0, y, k, fontsize=12, weight="bold", va="top")
        ax.text(0.2, y, v, fontsize=12, va="top")
        y -= 0.05
    tabela = ax.table(cellText=d.tabela(), colLabels=COLUNAS_TABELA, cellLoc="center",
                      bbox=[0, 0.1, 1, 0.3])
    tabela.auto_set_font_size(False)
    tabela.set_fontsize(11)
    for (lin, _), cel in tabela.get_celld().items():
        cel.set_edgecolor("#ced4da")
        if lin == 0:
            cel.set_facecolor("#e9ecef")
            cel.set_text_props(weight="bold")
    ax.text(0, 0.05, NOTA_UNIDADE, fontsize=8.5, color="#666", va="top", wrap=True)
    ax.set_ylim(0, 1)


def gerar_pdf(d, caminho, total=False):
    paginas = [("Resumo", None)] + [(t, f) for _, t, f in ABAS]
    meta = {"Title": f"Relatório do acelerômetro — {d.nome}", "Creator": "Visualizador de Acelerômetro"}
    with PdfPages(caminho, metadata=meta) as pdf:
        for i, (titulo, funcao) in enumerate(paginas, 1):
            fig = Figure(figsize=A4_PAISAGEM, layout="constrained")
            fig.get_layout_engine().set(rect=(0, 0.03, 1, 0.97))
            if funcao is None:
                fig_capa(fig, d)
            else:
                montar(fig, d, total, titulo, funcao)
            fig.text(0.015, 0.012, d.nome, fontsize=8, color="#888")
            fig.text(0.985, 0.012, f"Página {i} de {len(paginas)}", fontsize=8, color="#888", ha="right")
            pdf.savefig(fig)


# --------------------------------------------------------------------------
# Interface
# --------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Visualizador de Acelerômetro")
        self.geometry("1150x740")
        self.minsize(900, 600)
        self.dados = None
        self.tela = None
        self.var_total = tk.BooleanVar(value=False)
        self._estilos()
        self.bind("<Control-o>", lambda _e: self.escolher_arquivo())
        self.mostrar_inicio()

    # ---------- aparência ----------
    def _estilos(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        bg, azul = "#f4f6f9", "#2b6cb0"
        self.configure(bg=bg)
        s.configure("TFrame", background=bg)
        s.configure("TLabel", background=bg, foreground="#212529", font=("Helvetica", 11))
        s.configure("TCheckbutton", background=bg, font=("Helvetica", 10))
        s.configure("Titulo.TLabel", font=("Helvetica", 26, "bold"))
        s.configure("Sub.TLabel", font=("Helvetica", 13), foreground="#495057")
        s.configure("Dica.TLabel", font=("Helvetica", 10), foreground="#868e96")
        s.configure("Arquivo.TLabel", font=("Helvetica", 12, "bold"))
        s.configure("Cartao.TFrame", background="white", relief="solid", borderwidth=1, bordercolor="#dee2e6")
        s.configure("CartaoValor.TLabel", background="white", font=("Helvetica", 20, "bold"), foreground=azul)
        s.configure("CartaoTitulo.TLabel", background="white", font=("Helvetica", 10), foreground="#868e96")
        s.configure("TButton", font=("Helvetica", 11), padding=(12, 6))
        s.configure("Acento.TButton", font=("Helvetica", 14, "bold"), background=azul, foreground="white",
                    borderwidth=0, padding=(18, 10))
        s.map("Acento.TButton", background=[("active", "#2c5282"), ("pressed", "#2a4365")])
        s.configure("TNotebook", background=bg, borderwidth=0)
        s.configure("TNotebook.Tab", font=("Helvetica", 11), padding=(16, 7))
        s.configure("Treeview", rowheight=30, font=("Helvetica", 11), background="white", fieldbackground="white")
        s.configure("Treeview.Heading", font=("Helvetica", 11, "bold"), background="#e9ecef", padding=6)

    def _nova_tela(self):
        if self.tela is not None:
            self.tela.destroy()
        self.tela = ttk.Frame(self)
        self.tela.pack(fill="both", expand=True)
        return self.tela

    # ---------- tela inicial ----------
    def mostrar_inicio(self):
        self.dados = None
        tela = self._nova_tela()
        gc.collect()
        centro = ttk.Frame(tela)
        centro.place(relx=0.5, rely=0.45, anchor="center")
        ttk.Label(centro, text="Visualizador de Acelerômetro", style="Titulo.TLabel").pack()
        ttk.Label(centro, text="Carregue um arquivo CSV e veja os gráficos dos dados.",
                  style="Sub.TLabel").pack(pady=(8, 30))
        ttk.Button(centro, text="Selecionar arquivo CSV…", style="Acento.TButton",
                   command=self.escolher_arquivo).pack()
        self.lbl_status = ttk.Label(centro, text="", style="Sub.TLabel")
        self.lbl_status.pack(pady=(20, 0))
        ttk.Label(centro, style="Dica.TLabel", justify="center", wraplength=540,
                  text="O arquivo precisa ter as colunas ax, ay e az (aceleração em g) e, de preferência, "
                       "t_us (tempo em microssegundos).  Atalho: Ctrl+O").pack(pady=(30, 0))

    def escolher_arquivo(self):
        caminho = filedialog.askopenfilename(
            title="Selecione o arquivo CSV",
            filetypes=[("Arquivos CSV", "*.csv"), ("Todos os arquivos", "*.*")])
        if caminho:
            self.abrir(caminho)

    def abrir(self, caminho):
        if hasattr(self, "lbl_status") and self.lbl_status.winfo_exists():
            self.lbl_status.config(text="Carregando…")
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            dados = carregar_csv(caminho)
        except Exception as erro:
            self.config(cursor="")
            if hasattr(self, "lbl_status") and self.lbl_status.winfo_exists():
                self.lbl_status.config(text="")
            messagebox.showerror("Não foi possível abrir o arquivo", str(erro))
            return
        self.config(cursor="")
        self.dados = dados
        self.mostrar_resultado()

    # ---------- tela de resultados ----------
    def mostrar_resultado(self):
        tela = self._nova_tela()
        topo = ttk.Frame(tela, padding=(14, 12, 14, 6))
        topo.pack(fill="x")
        ttk.Button(topo, text="←  Novo arquivo", command=self.mostrar_inicio).pack(side="left")
        ttk.Label(topo, text=self.dados.nome, style="Arquivo.TLabel").pack(side="left", padx=16)
        ttk.Button(topo, text="Exportar PDF", command=self.exportar).pack(side="right")
        ttk.Checkbutton(topo, text="Mostrar picos extremos (escala total)", variable=self.var_total,
                        command=self._refazer_graficos).pack(side="right", padx=18)

        ttk.Label(tela, style="Dica.TLabel", padding=(16, 4),
                  text="Dica: use a lupa (zoom) e a mão (mover) da barra do gráfico; a casinha restaura a vista."
                  ).pack(side="bottom", fill="x")

        self.nb = ttk.Notebook(tela)
        self.nb.pack(fill="both", expand=True, padx=14, pady=(0, 4))
        self._abas = {}

        aba_resumo = ttk.Frame(self.nb)
        self.nb.add(aba_resumo, text="Resumo")
        self._montar_resumo(aba_resumo)
        for nome, titulo, funcao in ABAS:
            quadro = ttk.Frame(self.nb)
            self.nb.add(quadro, text=nome)
            self._abas[str(quadro)] = {"quadro": quadro, "titulo": titulo, "funcao": funcao, "pronta": False}
        self.nb.bind("<<NotebookTabChanged>>", lambda _e: self._construir_aba_atual())

    def _montar_resumo(self, aba):
        d = self.dados
        corpo = ttk.Frame(aba, padding=20)
        corpo.pack(fill="both", expand=True)
        cartoes = ttk.Frame(corpo)
        cartoes.pack(fill="x")
        for i, (titulo, valor) in enumerate(d.cartoes()):
            c = ttk.Frame(cartoes, style="Cartao.TFrame", padding=(18, 12))
            ttk.Label(c, text=valor, style="CartaoValor.TLabel").pack(anchor="w")
            ttk.Label(c, text=titulo, style="CartaoTitulo.TLabel").pack(anchor="w")
            c.grid(row=0, column=i, padx=(0, 14), sticky="ew")
            cartoes.columnconfigure(i, weight=1, uniform="c")

        tab = ttk.Treeview(corpo, columns=COLUNAS_TABELA, show="headings", height=4, selectmode="none")
        for col in COLUNAS_TABELA:
            tab.heading(col, text=col)
            tab.column(col, anchor="center", width=120)
        for linha in d.tabela():
            tab.insert("", "end", values=linha)
        tab.pack(fill="x", pady=(24, 10))
        ttk.Label(corpo, text=NOTA_UNIDADE, style="Dica.TLabel", wraplength=900, justify="left").pack(anchor="w")

    def _construir_aba_atual(self):
        info = self._abas.get(self.nb.select())
        if info and not info["pronta"]:
            self._construir_grafico(info)

    def _construir_grafico(self, info):
        quadro = info["quadro"]
        for w in quadro.winfo_children():
            w.destroy()
        self.config(cursor="watch")
        self.update_idletasks()
        fig = Figure(layout="constrained")
        montar(fig, self.dados, self.var_total.get(), info["titulo"], info["funcao"])
        canvas = FigureCanvasTkAgg(fig, master=quadro)
        barra = NavigationToolbar2Tk(canvas, quadro, pack_toolbar=False)
        barra.update()
        barra.pack(side="bottom", fill="x")
        canvas.get_tk_widget().pack(side="top", fill="both", expand=True)
        canvas.draw()
        info["pronta"] = True
        self.config(cursor="")

    def _refazer_graficos(self):
        for info in self._abas.values():
            info["pronta"] = False
            for w in info["quadro"].winfo_children():
                w.destroy()
        self._construir_aba_atual()

    # ---------- exportação ----------
    def exportar(self):
        base = os.path.splitext(self.dados.nome)[0]
        caminho = filedialog.asksaveasfilename(
            title="Salvar relatório em PDF", defaultextension=".pdf",
            initialfile=f"{base}_relatorio.pdf", filetypes=[("PDF", "*.pdf")])
        if not caminho:
            return
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            gerar_pdf(self.dados, caminho, self.var_total.get())
        except Exception as erro:
            self.config(cursor="")
            messagebox.showerror("Erro ao gerar o PDF", str(erro))
            return
        self.config(cursor="")
        messagebox.showinfo("Relatório salvo", f"O relatório foi salvo em:\n{caminho}")


if __name__ == "__main__":
    app = App()
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        app.after(150, lambda: app.abrir(sys.argv[1]))
    app.mainloop()
