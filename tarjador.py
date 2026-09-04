# -*- coding: utf-8 -*-
"""
Tarjador de PDFs - tarja manual (desenhada) com remocao real do conteudo.

Fluxo: abre um PDF de input/ -> voce arrasta o mouse desenhando as tarjas ->
salva em output/. Ao salvar, o texto/imagem sob a tarja e REMOVIDO do arquivo
(nao e so um retangulo por cima), entao nao da para copiar o CPF depois.

Tudo roda localmente. Nada e enviado para lugar nenhum.
"""

import io
import math
import os
import re
import sys
import subprocess
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, ttk

try:
    import pymupdf as fitz
except ImportError:  # PyMuPDF antigo
    import fitz
from PIL import Image, ImageDraw, ImageTk

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE_DIR, "input")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

ZOOM_STEPS = [0.5, 0.65, 0.8, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]
DEFAULT_ZOOM_INDEX = 3
RASTER_DPI = 200  # qualidade das paginas quando o modo rasterizado esta ligado

BG = "#1e1e22"
PANEL = "#2a2a30"
FG = "#e8e8ea"
ACCENT = "#4a9eff"

# CPF: 000.000.000-00, 000 000 000 00 ou 11 digitos seguidos
CPF_RE = re.compile(r"\b\d{3}[.\s]?\d{3}[.\s]?\d{3}[-\s]?\d{2}\b")


class Tarjador(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tarjador de PDFs")
        self.geometry("1280x860")
        self.configure(bg=BG)
        self.minsize(900, 600)

        self.doc = None
        self.path = None
        self.page_index = 0
        self.zoom_index = DEFAULT_ZOOM_INDEX
        self.boxes = {}          # {pagina: [fitz.Rect em pontos do PDF]}
        self.undo_stack = []     # [(pagina, rect)]
        self.photo = None
        self.page_origin = (0.0, 0.0)
        self.offset_x = 0        # centraliza a pagina quando sobra espaco
        self.drag_start = None
        self.temp_rect_id = None
        self._resize_job = None
        self._last_canvas_w = 0
        self.rasterizar = tk.BooleanVar(value=True)

        self._build_ui()
        self._bind_keys()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh_file_list()
        self._set_status("Escolha um PDF na lista da esquerda ou clique em 'Abrir PDF...'")

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        # fonte padrao do sistema: "Segoe UI" so existe no Windows
        self.fonte_ui = tkfont.nametofont("TkDefaultFont").actual("family")
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TButton", padding=(10, 6), background="#3a3a42",
                        foreground=FG, borderwidth=0, focuscolor=PANEL)
        style.map("TButton",
                  background=[("active", "#4a4a54"), ("pressed", "#2f2f37")],
                  foreground=[("disabled", "#77777f")])
        style.configure("Save.TButton", padding=(14, 7), background=ACCENT,
                        foreground="#ffffff", borderwidth=0, font=(self.fonte_ui, 9, "bold"))
        style.map("Save.TButton", background=[("active", "#5cb0ff"), ("pressed", "#3a86e0")])
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("Panel.TLabel", background=PANEL, foreground=FG)
        style.configure("TSeparator", background="#44444c")
        style.configure("Panel.TCheckbutton", background=PANEL, foreground=FG,
                        focuscolor=PANEL)
        style.map("Panel.TCheckbutton",
                  background=[("active", PANEL)], foreground=[("active", FG)])

        # ---- barra de ferramentas
        bar = ttk.Frame(self, style="Panel.TFrame")
        bar.pack(side="top", fill="x")

        ttk.Button(bar, text="Abrir PDF...", command=self.open_dialog).pack(
            side="left", padx=(8, 14), pady=8)

        ttk.Button(bar, text="<", width=3, command=self.prev_page).pack(side="left")
        self.page_label = ttk.Label(bar, text="-", style="Panel.TLabel", width=12, anchor="center")
        self.page_label.pack(side="left", padx=4)
        ttk.Button(bar, text=">", width=3, command=self.next_page).pack(side="left")

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=12, pady=8)

        ttk.Button(bar, text="-", width=3, command=lambda: self.change_zoom(-1)).pack(side="left")
        self.zoom_label = ttk.Label(bar, text="100%", style="Panel.TLabel", width=6, anchor="center")
        self.zoom_label.pack(side="left", padx=2)
        ttk.Button(bar, text="+", width=3, command=lambda: self.change_zoom(1)).pack(side="left")

        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=12, pady=8)

        ttk.Button(bar, text="Desfazer", command=self.undo).pack(side="left", padx=2)
        ttk.Button(bar, text="Limpar pagina", command=self.clear_page).pack(side="left", padx=2)
        ttk.Button(bar, text="Detectar CPFs", command=self.detect_cpfs).pack(side="left", padx=2)

        self.save_btn = ttk.Button(bar, text="SALVAR EM OUTPUT", style="Save.TButton",
                                   command=self.save)
        self.save_btn.pack(side="right", padx=10, pady=8)

        # ---- corpo
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)

        side = ttk.Frame(body, style="Panel.TFrame", width=250)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        ttk.Label(side, text="  PDFs em  input/", style="Panel.TLabel",
                  font=(self.fonte_ui, 10, "bold")).pack(anchor="w", pady=(10, 6))

        # de baixo para cima: a lista fica com o espaco que sobrar.
        # A opcao mora aqui, e nao na barra de cima, porque la ela disputava
        # espaco com os botoes e o texto era cortado em fontes mais largas.
        ttk.Button(side, text="Atualizar lista", command=self.refresh_file_list).pack(
            side="bottom", fill="x", padx=8, pady=8)
        raster_chk = ttk.Checkbutton(side, text="Rasterizar paginas tarjadas",
                                     variable=self.rasterizar, style="Panel.TCheckbutton")
        raster_chk.pack(side="bottom", anchor="w", padx=8, pady=(6, 2))
        ttk.Separator(side, orient="horizontal").pack(side="bottom", fill="x", padx=8, pady=(8, 0))
        self._tooltip(raster_chk,
                      "Transforma cada pagina tarjada em imagem ao salvar.\n"
                      "Nao sobra nenhum objeto de texto na pagina - nem invisivel.\n"
                      "Em troca: o arquivo fica maior e nao da para selecionar\n"
                      "texto nessas paginas.\n\n"
                      "Nao e necessario para foto: a area tarjada ja e pintada\n"
                      "de preto DENTRO do arquivo de imagem, apagando os pixels\n"
                      "originais. Isto aqui e so uma camada extra de garantia.")

        self.listbox = tk.Listbox(side, bg=BG, fg=FG, selectbackground=ACCENT,
                                  highlightthickness=0, borderwidth=0, activestyle="none")
        self.listbox.pack(fill="both", expand=True, padx=8)
        self.listbox.bind("<Double-Button-1>", self.open_from_list)
        self.listbox.bind("<Return>", self.open_from_list)

        canvas_wrap = ttk.Frame(body)
        canvas_wrap.pack(side="left", fill="both", expand=True)

        self.canvas = tk.Canvas(canvas_wrap, bg="#131316", highlightthickness=0, cursor="crosshair")
        vbar = ttk.Scrollbar(canvas_wrap, orient="vertical", command=self.canvas.yview)
        hbar = ttk.Scrollbar(canvas_wrap, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        vbar.pack(side="right", fill="y")
        hbar.pack(side="bottom", fill="x")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Button-3>", self.on_right_click)
        # Windows/macOS mandam <MouseWheel>; o X11 (Linux) manda Button-4/5
        self.canvas.bind("<MouseWheel>", self.on_wheel)
        self.canvas.bind("<Shift-MouseWheel>", self.on_shift_wheel)
        self.canvas.bind("<Control-MouseWheel>", self.on_ctrl_wheel)
        for botao, passo in (("<Button-4>", 1), ("<Button-5>", -1)):
            self.canvas.bind(botao, lambda e, p=passo: self.on_wheel(self._roda(e, p)))
            self.canvas.bind("<Shift-%s>" % botao[1:-1],
                             lambda e, p=passo: self.on_shift_wheel(self._roda(e, p)))
            self.canvas.bind("<Control-%s>" % botao[1:-1],
                             lambda e, p=passo: self.on_ctrl_wheel(self._roda(e, p)))
        self.canvas.bind("<Configure>", self.on_canvas_resize)

        self.status = ttk.Label(self, text="", anchor="w", background=PANEL, foreground="#b9b9c0")
        self.status.pack(side="bottom", fill="x", ipady=5)

    def _bind_keys(self):
        self.bind("<Control-z>", lambda e: self.undo())
        self.bind("<Control-s>", lambda e: self.save())
        self.bind("<Control-o>", lambda e: self.open_dialog())
        self.bind("<Next>", lambda e: self.next_page())
        self.bind("<Prior>", lambda e: self.prev_page())

    def _set_status(self, msg):
        self.status.config(text="  " + msg)

    def _tooltip(self, widget, texto):
        janela = {}

        def mostrar(_e):
            if janela:
                return
            x = widget.winfo_rootx()
            y = widget.winfo_rooty() + widget.winfo_height() + 4
            top = tk.Toplevel(self)
            top.wm_overrideredirect(True)
            top.wm_geometry("+%d+%d" % (x, y))
            tk.Label(top, text=texto, justify="left", background="#3a3a42", foreground=FG,
                     relief="solid", borderwidth=1, padx=8, pady=6).pack()
            janela["w"] = top

        def esconder(_e):
            if janela:
                janela.pop("w").destroy()

        widget.bind("<Enter>", mostrar)
        widget.bind("<Leave>", esconder)

    # -------------------------------------------------------------- arquivo
    def refresh_file_list(self):
        self.listbox.delete(0, tk.END)
        os.makedirs(INPUT_DIR, exist_ok=True)
        pdfs = sorted(f for f in os.listdir(INPUT_DIR) if f.lower().endswith(".pdf"))
        for f in pdfs:
            self.listbox.insert(tk.END, f)
        if not pdfs:
            self.listbox.insert(tk.END, "(vazio - coloque PDFs aqui)")

    def open_from_list(self, _event=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        name = self.listbox.get(sel[0])
        full = os.path.join(INPUT_DIR, name)
        if os.path.isfile(full):
            self.load_pdf(full)

    def open_dialog(self):
        path = filedialog.askopenfilename(
            title="Abrir PDF", initialdir=INPUT_DIR,
            filetypes=[("PDF", "*.pdf"), ("Todos os arquivos", "*.*")])
        if path:
            self.load_pdf(path)

    def load_pdf(self, path):
        if self.doc and self._pending_count() and not messagebox.askyesno(
                "Descartar tarjas?",
                "Ha tarjas nao salvas no PDF atual. Abrir outro arquivo e descarta-las?"):
            return
        try:
            doc = fitz.open(path)
        except Exception as exc:
            messagebox.showerror("Erro ao abrir", "Nao foi possivel abrir o PDF:\n%s" % exc)
            return
        if doc.needs_pass:
            messagebox.showerror("PDF protegido", "Este PDF exige senha e nao pode ser aberto.")
            doc.close()
            return
        if self.doc:
            self.doc.close()
        self.doc = doc
        self.path = path
        self.page_index = 0
        self.boxes = {}
        self.undo_stack = []
        self.title("Tarjador de PDFs - " + os.path.basename(path))
        self.render()
        self._set_status(
            "Arraste o mouse sobre o CPF para tarjar. Botao direito em cima de uma tarja apaga ela.")

    # ------------------------------------------------------------ navegacao
    def next_page(self):
        if self.doc and self.page_index < self.doc.page_count - 1:
            self.page_index += 1
            self.render()

    def prev_page(self):
        if self.doc and self.page_index > 0:
            self.page_index -= 1
            self.render()

    def change_zoom(self, delta):
        new = max(0, min(len(ZOOM_STEPS) - 1, self.zoom_index + delta))
        if new != self.zoom_index:
            self.zoom_index = new
            self.render()

    def _roda(self, event, passo):
        """Traduz o evento de roda do X11 para o formato do <MouseWheel>."""
        event.delta = 120 * passo
        return event

    def on_wheel(self, event):
        self.canvas.yview_scroll(-1 * (event.delta // 120), "units")

    def on_shift_wheel(self, event):
        self.canvas.xview_scroll(-1 * (event.delta // 120), "units")
        return "break"

    def on_ctrl_wheel(self, event):
        self.change_zoom(1 if event.delta > 0 else -1)
        return "break"

    @property
    def zoom(self):
        return ZOOM_STEPS[self.zoom_index]

    # ------------------------------------------------------------ renderizar
    def render(self):
        self.canvas.delete("all")
        if not self.doc:
            self.page_label.config(text="-")
            return

        page = self.doc[self.page_index]
        matrix = fitz.Matrix(self.zoom, self.zoom)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        self.photo = ImageTk.PhotoImage(img)

        self.page_origin = (page.rect.x0, page.rect.y0)
        canvas_w = max(self.canvas.winfo_width(), 1)
        self.offset_x = max(0, (canvas_w - pix.width) // 2)
        self._last_canvas_w = canvas_w
        self.canvas.create_image(self.offset_x, 0, anchor="nw", image=self.photo, tags="page")
        self.canvas.configure(scrollregion=(0, 0, max(canvas_w, pix.width), pix.height))

        for rect in self.boxes.get(self.page_index, []):
            x0, y0 = self.pdf_to_canvas(rect.x0, rect.y0)
            x1, y1 = self.pdf_to_canvas(rect.x1, rect.y1)
            self.canvas.create_rectangle(x0, y0, x1, y1, fill="black",
                                         outline="#ff3b30", width=1, tags="box")

        self.page_label.config(text="%d / %d" % (self.page_index + 1, self.doc.page_count))
        self.zoom_label.config(text="%d%%" % int(self.zoom * 100))
        self._update_status_counts()

    def _update_status_counts(self):
        n_page = len(self.boxes.get(self.page_index, []))
        n_total = self._pending_count()
        self._set_status("%d tarja(s) nesta pagina - %d no documento inteiro" % (n_page, n_total))

    def _pending_count(self):
        return sum(len(v) for v in self.boxes.values())

    # ------------------------------------------------------- coordenadas
    def canvas_to_pdf(self, cx, cy):
        return ((cx - self.offset_x) / self.zoom + self.page_origin[0],
                cy / self.zoom + self.page_origin[1])

    def pdf_to_canvas(self, px, py):
        return ((px - self.page_origin[0]) * self.zoom + self.offset_x,
                (py - self.page_origin[1]) * self.zoom)

    def on_canvas_resize(self, event):
        """Recentraliza a pagina quando a janela muda de tamanho (com atraso,
        para nao re-renderizar a cada pixel do arrasto)."""
        if not self.doc or event.width == self._last_canvas_w:
            return
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(120, self.render)

    def _event_xy(self, event):
        return (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))

    # ------------------------------------------------------------- desenho
    def on_press(self, event):
        if not self.doc:
            return
        self.drag_start = self._event_xy(event)

    def on_drag(self, event):
        if not self.drag_start:
            return
        x, y = self._event_xy(event)
        if self.temp_rect_id:
            self.canvas.delete(self.temp_rect_id)
        self.temp_rect_id = self.canvas.create_rectangle(
            self.drag_start[0], self.drag_start[1], x, y,
            fill="black", stipple="gray50", outline=ACCENT, width=1)

    def on_release(self, event):
        if not self.drag_start:
            return
        x0, y0 = self.drag_start
        x1, y1 = self._event_xy(event)
        self.drag_start = None
        if self.temp_rect_id:
            self.canvas.delete(self.temp_rect_id)
            self.temp_rect_id = None
        if abs(x1 - x0) < 4 or abs(y1 - y0) < 4:
            return  # clique solto, nao e uma tarja
        p0 = self.canvas_to_pdf(min(x0, x1), min(y0, y1))
        p1 = self.canvas_to_pdf(max(x0, x1), max(y0, y1))
        self.add_box(fitz.Rect(p0[0], p0[1], p1[0], p1[1]))

    def add_box(self, rect, rerender=True):
        lst = self.boxes.setdefault(self.page_index, [])
        lst.append(rect)
        self.undo_stack.append((self.page_index, rect))
        if rerender:
            self.render()

    def on_right_click(self, event):
        """Botao direito em cima de uma tarja remove ela."""
        if not self.doc:
            return
        px, py = self.canvas_to_pdf(*self._event_xy(event))
        lst = self.boxes.get(self.page_index, [])
        for i in range(len(lst) - 1, -1, -1):
            if lst[i].contains(fitz.Point(px, py)):
                removida = lst.pop(i)
                for j in range(len(self.undo_stack) - 1, -1, -1):
                    if self.undo_stack[j][0] == self.page_index and self.undo_stack[j][1] == removida:
                        del self.undo_stack[j]
                        break
                self.render()
                return

    def undo(self):
        if not self.undo_stack:
            return
        page, rect = self.undo_stack.pop()
        lst = self.boxes.get(page, [])
        for i in range(len(lst) - 1, -1, -1):
            if lst[i] == rect:
                del lst[i]
                break
        self.page_index = page
        self.render()

    def clear_page(self):
        if self.boxes.get(self.page_index):
            self.boxes[self.page_index] = []
            self.undo_stack = [u for u in self.undo_stack if u[0] != self.page_index]
            self.render()

    # --------------------------------------------------- deteccao opcional
    def detect_cpfs(self):
        """Sugere tarjas sobre tudo que tem cara de CPF na pagina atual.

        E so um atalho: as tarjas entram como qualquer outra e podem ser
        apagadas com o botao direito. Nao funciona em PDF digitalizado
        (imagem sem camada de texto)."""
        if not self.doc:
            return
        page = self.doc[self.page_index]
        encontrados = {m.group(0) for m in CPF_RE.finditer(page.get_text())}
        adicionadas = 0
        for termo in encontrados:
            for rect in page.search_for(termo):
                r = fitz.Rect(rect) + (-1, -1, 1, 1)
                if any(r.intersects(b) for b in self.boxes.get(self.page_index, [])):
                    continue
                self.add_box(r, rerender=False)
                adicionadas += 1
        self.render()
        if adicionadas:
            self._set_status(
                "%d possivel(is) CPF(s) tarjado(s) automaticamente. Confira antes de salvar."
                % adicionadas)
        elif encontrados:
            self._set_status(
                "Os %d CPF(s) desta pagina ja estao cobertos pelas tarjas que voce desenhou."
                % len(encontrados))
        else:
            self._set_status(
                "Nenhum CPF no texto desta pagina (PDF digitalizado? tarje manualmente).")

    # ---------------------------------------------------------------- salvar
    def _limpar_anotacoes(self, page, rects):
        """Remove anotacoes, campos de formulario e links que encostam na tarja.

        apply_redactions mexe no conteudo da pagina, mas o valor de um campo de
        formulario ou o texto de um comentario vive fora dele - e sobreviveria."""
        try:
            for annot in list(page.annots()):
                if any(fitz.Rect(annot.rect).intersects(r) for r in rects):
                    page.delete_annot(annot)
        except Exception:
            pass
        try:
            for widget in list(page.widgets()):
                if any(fitz.Rect(widget.rect).intersects(r) for r in rects):
                    page.delete_widget(widget)
        except Exception:
            pass
        try:
            for link in page.get_links():
                if any(fitz.Rect(link["from"]).intersects(r) for r in rects):
                    page.delete_link(link)
        except Exception:
            pass

    def _imagens_sob_tarja(self, page, rects):
        """Onde cada tarja cai DENTRO de cada imagem da pagina.

        Devolve {xref: [(u0, v0, u1, v1), ...]} em fracao da imagem (0 a 1), ou
        None se alguma imagem atingida nao puder ser localizada com seguranca.

        Isso importa porque o PyMuPDF nao consegue zerar so o pedaco tarjado de
        uma imagem (PDF_REDACT_IMAGE_PIXELS nao tem efeito na versao atual, e a
        alternativa apagaria a foto inteira). Entao a gente localiza a regiao na
        propria imagem e reescreve o arquivo dela - ver _pintar_imagem."""
        try:
            infos = list(page.get_image_info(xrefs=True))
        except Exception:
            return None
        alvos = {}
        for info in infos:
            try:
                bbox = fitz.Rect(info["bbox"])
            except Exception:
                return None
            atingidas = [r for r in rects if bbox.intersects(r)]
            if not atingidas:
                continue
            xref = info.get("xref") or 0
            if not xref:
                return None  # imagem sem xref proprio: nao da para reescrever
            try:
                inverso = ~fitz.Matrix(info["transform"])
            except Exception:
                return None
            for r in atingidas:
                # os 4 cantos da tarja no espaco da imagem (quadrado unitario),
                # com bounding box - assim rotacao/espelhamento so aumentam a
                # area pintada, nunca deixam sobrar pedaco
                cantos = [fitz.Point(r.x0, r.y0) * inverso, fitz.Point(r.x1, r.y0) * inverso,
                          fitz.Point(r.x0, r.y1) * inverso, fitz.Point(r.x1, r.y1) * inverso]
                us = [p.x for p in cantos]
                vs = [p.y for p in cantos]
                u0, u1 = max(0.0, min(us)), min(1.0, max(us))
                v0, v1 = max(0.0, min(vs)), min(1.0, max(vs))
                if u1 > u0 and v1 > v0:
                    alvos.setdefault(xref, []).append((u0, v0, u1, v1))
        return alvos

    def _pintar_imagem(self, doc, page, xref, fracoes):
        """Pinta de preto as regioes tarjadas dentro do arquivo de imagem.

        Preto solido, nao borrado: desfoque e pixelizacao sao reversiveis, e
        num CPF - 11 digitos de alfabeto conhecido - a reconstrucao e viavel."""
        try:
            pix = fitz.Pixmap(doc, xref)
            if pix.colorspace is None or pix.n - pix.alpha > 3:
                pix = fitz.Pixmap(fitz.csRGB, pix)   # CMYK/separacao -> RGB
            canais = pix.n - pix.alpha
            modo = "RGBA" if pix.alpha else ("L" if canais == 1 else "RGB")
            im = Image.frombytes(modo, (pix.width, pix.height), pix.samples)
            preto = 0 if modo == "L" else ((0, 0, 0, 255) if modo == "RGBA" else (0, 0, 0))
            desenho = ImageDraw.Draw(im)
            largura, altura = im.size
            for (u0, v0, u1, v1) in fracoes:
                # arredonda sempre PARA FORA e ainda sobra 2px de folga: melhor
                # pintar um fio a mais do que deixar franja do original na borda
                desenho.rectangle((math.floor(u0 * largura) - 2, math.floor(v0 * altura) - 2,
                                   math.ceil(u1 * largura) + 2, math.ceil(v1 * altura) + 2),
                                  fill=preto)
            buffer = io.BytesIO()
            if modo == "RGB":
                im.save(buffer, format="JPEG", quality=92)   # foto: nao incha o arquivo
            else:
                im.save(buffer, format="PNG")
            page.replace_image(xref, stream=buffer.getvalue())
            return True
        except Exception:
            return False   # quem chamou rasteriza a pagina como plano B

    def _tarjar_imagens(self, doc, page, rects):
        """True se toda imagem sob a tarja foi reescrita com sucesso."""
        alvos = self._imagens_sob_tarja(page, rects)
        if alvos is None:
            return False
        return all(self._pintar_imagem(doc, page, xref, fracoes)
                   for xref, fracoes in alvos.items())

    def _apagar_miniatura(self, doc, page):
        """Apaga a miniatura embutida da pagina (/Thumb).

        Alguns geradores de PDF guardam uma previa da pagina inteira num objeto
        separado. Ela nao e afetada pela tarja e mostraria a foto original."""
        try:
            if doc.xref_get_key(page.xref, "Thumb")[0] != "null":
                doc.xref_set_key(page.xref, "Thumb", "null")
        except Exception:
            pass

    def _rasterizar(self, doc, paginas):
        """Troca as paginas tarjadas por uma imagem chapada delas.

        Ultima linha de defesa: numa pagina que virou imagem nao existe mais
        objeto de texto nenhum para alguem tentar recuperar."""
        novo = fitz.open()
        for i in range(doc.page_count):
            origem = doc[i]
            if i in paginas:
                pix = origem.get_pixmap(dpi=RASTER_DPI, alpha=False)
                nova = novo.new_page(width=origem.rect.width, height=origem.rect.height)
                nova.insert_image(nova.rect, pixmap=pix)
            else:
                novo.insert_pdf(doc, from_page=i, to_page=i)
        return novo

    LIMITE_PRETO = 40   # 0 e preto puro; folga para reompressao JPEG

    def _conferir_imagens(self, doc, page, rects, page_index):
        """Extrai as imagens do arquivo salvo e olha os pixels sob a tarja.

        E a prova real de que a foto foi reescrita: nao adianta a pagina
        renderizar preta se o arquivo de imagem embaixo continua original."""
        alvos = self._imagens_sob_tarja(page, rects)
        if alvos is None:
            return ["pagina %d: nao consegui localizar as imagens para conferir"
                    % (page_index + 1)]
        problemas = []
        for xref, fracoes in alvos.items():
            try:
                pix = fitz.Pixmap(doc, xref)
                if pix.colorspace is None or pix.n - pix.alpha > 3:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                canais = pix.n - pix.alpha
                modo = "RGBA" if pix.alpha else ("L" if canais == 1 else "RGB")
                im = Image.frombytes(modo, (pix.width, pix.height), pix.samples).convert("RGB")
                largura, altura = im.size
                for (u0, v0, u1, v1) in fracoes:
                    caixa = (int(u0 * largura) + 2, int(v0 * altura) + 2,
                             int(u1 * largura) - 2, int(v1 * altura) - 2)
                    if caixa[2] <= caixa[0] or caixa[3] <= caixa[1]:
                        continue   # tarja menor que 4px na imagem: nada a conferir
                    claro = max(canal[1] for canal in im.crop(caixa).getextrema())
                    if claro > self.LIMITE_PRETO:
                        problemas.append(
                            "pagina %d: a imagem ainda guarda o conteudo original sob a "
                            "tarja (pixel mais claro %d de 255)" % (page_index + 1, claro))
                        break
            except Exception as exc:
                problemas.append("pagina %d: nao consegui conferir uma imagem (%s)"
                                 % (page_index + 1, exc))
        return problemas

    def _conferir(self, caminho, rasterizadas):
        """Reabre o arquivo salvo e confere se sobrou algo sob as tarjas."""
        problemas = []
        doc = fitz.open(caminho)
        try:
            for page_index, rects in self.boxes.items():
                if not rects or page_index >= doc.page_count:
                    continue
                page = doc[page_index]
                for r in rects:
                    resto = page.get_text("text", clip=r).strip()
                    if resto:
                        problemas.append("pagina %d: sobrou texto sob a tarja (%r)"
                                         % (page_index + 1, resto[:40]))
                if page_index not in rasterizadas:
                    problemas += self._conferir_imagens(doc, page, rects, page_index)
            texto_todo = "\n".join(p.get_text() for p in doc)
            restantes = set(CPF_RE.findall(texto_todo))
            if restantes:
                problemas.append("ainda ha %d texto(s) com formato de CPF em outras partes "
                                 "do documento (nao tarjados)" % len(restantes))
        finally:
            doc.close()
        return problemas

    def save(self):
        if not self.doc:
            return
        if self._pending_count() == 0:
            messagebox.showinfo("Nada para tarjar", "Voce ainda nao desenhou nenhuma tarja.")
            return

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        stem = os.path.splitext(os.path.basename(self.path))[0]
        out = os.path.join(OUTPUT_DIR, stem + "_tarjado.pdf")
        n = 2
        while os.path.exists(out):
            out = os.path.join(OUTPUT_DIR, "%s_tarjado_%d.pdf" % (stem, n))
            n += 1

        paginas = {p for p, rects in self.boxes.items() if rects}
        falhou_imagem = set()
        doc = None
        rasterizado = None
        try:
            doc = fitz.open(self.path)
            for page_index in sorted(paginas):
                rects = self.boxes[page_index]
                page = doc[page_index]
                self._limpar_anotacoes(page, rects)
                # pinta de preto dentro do proprio arquivo de imagem; se nao
                # der, a pagina inteira e rasterizada mais abaixo
                if not self._tarjar_imagens(doc, page, rects):
                    falhou_imagem.add(page_index)
                for r in rects:
                    page.add_redact_annot(r, fill=(0, 0, 0))
                # texto e vetores; imagem ja foi tratada acima (IMAGE_NONE para
                # o apply_redactions nao apagar a foto inteira)
                page.apply_redactions(
                    text=fitz.PDF_REDACT_TEXT_REMOVE,
                    images=fitz.PDF_REDACT_IMAGE_NONE,
                    graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED)
                self._apagar_miniatura(doc, page)

            # rasterizar e o plano B: so quando nao deu para pintar a imagem
            raster = paginas if self.rasterizar.get() else falhou_imagem
            if raster:
                rasterizado = self._rasterizar(doc, raster)
                final = rasterizado
            else:
                final = doc

            # metadados e XMP podem carregar o CPF no titulo/assunto/palavras-chave
            final.set_metadata({})
            try:
                final.del_xml_metadata()
            except Exception:
                pass
            # garbage=4 + clean descartam objetos orfaos e revisoes antigas do PDF
            final.save(out, garbage=4, deflate=True, clean=True)
        except Exception as exc:
            messagebox.showerror("Erro ao salvar", "Nao foi possivel salvar:\n%s" % exc)
            return
        finally:
            if rasterizado is not None:
                rasterizado.close()
            if doc is not None:
                doc.close()

        problemas = self._conferir(out, raster)
        self._set_status("Salvo em output/" + os.path.basename(out))

        if problemas:
            messagebox.showwarning(
                "Salvo, mas confira",
                "Salvo em:\n%s\n\nA conferencia automatica encontrou:\n\n- %s\n\n"
                "Abra o arquivo e confirme antes de enviar para alguem."
                % (out, "\n- ".join(problemas)))
            return

        if raster == paginas:
            modo = ("Todas as %d pagina(s) tarjada(s) viraram imagem: nao sobrou nenhum\n"
                    "objeto de texto nem imagem original nelas." % len(paginas))
        elif raster:
            modo = ("Em %d pagina(s) nao deu para reescrever a imagem, entao elas viraram\n"
                    "imagem chapada. Nas outras %d, o texto e os vetores foram removidos e\n"
                    "as fotos foram pintadas de preto por dentro."
                    % (len(raster), len(paginas) - len(raster)))
        else:
            modo = ("Texto e vetores sob as tarjas removidos do arquivo, e as fotos\n"
                    "pintadas de preto por dentro do proprio arquivo de imagem.\n"
                    "O texto das paginas continua selecionavel.")
        if messagebox.askyesno(
                "Salvo e conferido",
                "PDF tarjado salvo em:\n%s\n\n%s\n\nConferencia automatica: nada sobrou sob "
                "as tarjas.\n\nAbrir a pasta output?" % (out, modo)):
            self.open_output_folder()

    def on_close(self):
        """Avisa sobre tarjas nao salvas e solta o arquivo de input."""
        if self._pending_count() and not messagebox.askyesno(
                "Sair sem salvar?",
                "Ha %d tarja(s) que voce ainda nao salvou. Sair mesmo assim?"
                % self._pending_count()):
            return
        if self.doc:
            self.doc.close()
            self.doc = None
        self.destroy()

    def open_output_folder(self):
        try:
            if sys.platform.startswith("win"):
                os.startfile(OUTPUT_DIR)
            elif sys.platform == "darwin":
                subprocess.run(["open", OUTPUT_DIR], check=False)
            else:
                subprocess.run(["xdg-open", OUTPUT_DIR], check=False)
        except Exception:
            pass


def main():
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    Tarjador().mainloop()


if __name__ == "__main__":
    main()
