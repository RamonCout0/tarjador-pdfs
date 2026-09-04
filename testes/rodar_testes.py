# -*- coding: utf-8 -*-
"""
Bateria de testes do Tarjador.

    python3 testes/rodar_testes.py            # roda tudo
    python3 testes/rodar_testes.py --lista    # so lista os casos
    python3 testes/rodar_testes.py foto_normal

Cada caso que abre janela roda num processo separado (dois Tk() no mesmo
processo brigam pelas imagens do Tk). Num servidor sem tela, use:

    xvfb-run -a python3 testes/rodar_testes.py

Todos os CPFs aqui sao FICTICIOS, gerados para o teste.
"""

import io
import os
import shutil
import subprocess
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import pymupdf as fitz
from PIL import Image, ImageDraw, ImageFont

CPF_TXT = "111.222.333-44"
CPF_META = "555.666.777-88"
CPF_FORM = "999.888.777-66"
CPF_ANOT = "123.123.123-12"
CPF_IMG = "321.321.321-21"
MAGENTA = (255, 0, 255)


# --------------------------------------------------------------- utilidades
def _fonte(tam):
    for nome in ("arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(nome, tam)
        except Exception:
            continue
    return ImageFont.load_default()


def _app(tmp, rasterizar):
    """Cria a janela do Tarjador apontando input/output para uma pasta temporaria."""
    import tarjador
    from tkinter import messagebox
    messagebox.askyesno = lambda *a, **k: False
    messagebox.showinfo = lambda *a, **k: None
    messagebox.showerror = lambda *a, **k: print("   [ERRO]", a[1][:300])
    messagebox.showwarning = lambda *a, **k: print("   [AVISO]", a[1][:300])
    tarjador.INPUT_DIR = os.path.join(tmp, "input")
    tarjador.OUTPUT_DIR = os.path.join(tmp, "output")
    os.makedirs(tarjador.INPUT_DIR, exist_ok=True)
    os.makedirs(tarjador.OUTPUT_DIR, exist_ok=True)
    app = tarjador.Tarjador()
    app.rasterizar.set(rasterizar)
    app.update()
    return app, tarjador


def _salvar(app, tarjador, src, caixas, rasterizar):
    app.load_pdf(src)
    app.update()
    app.boxes.update(caixas)
    app.render()
    app.update()
    app.save()
    app.boxes.clear()
    app.on_close()
    saidas = sorted(os.listdir(tarjador.OUTPUT_DIR))
    assert saidas, "nada foi salvo"
    return os.path.join(tarjador.OUTPUT_DIR, saidas[0])


def _pixels_magenta(im):
    px = im.convert("RGB").load()
    return sum(1 for y in range(im.height) for x in range(im.width)
               if px[x, y][0] > 180 and px[x, y][1] < 80 and px[x, y][2] > 180)


# ------------------------------------------------------------------- casos
def caso_texto(tmp):
    """CPF em texto some; o resto do texto fica."""
    src = os.path.join(tmp, "texto.pdf")
    d = fitz.open()
    p = d.new_page()
    p.insert_text((72, 100), "Relatorio", fontsize=14)
    p.insert_text((72, 140), "Nome: Fulano de Tal", fontsize=12)
    p.insert_text((72, 160), "CPF: " + CPF_TXT, fontsize=12)
    p2 = d.new_page()
    p2.insert_text((72, 100), "Pagina 2 - CPF: " + CPF_META, fontsize=12)
    d.save(src)
    d.close()

    d = fitz.open(src)
    caixas = {0: [fitz.Rect(r) for r in d[0].search_for(CPF_TXT)],
              1: [fitz.Rect(r) for r in d[1].search_for(CPF_META)]}
    d.close()

    app, tarj = _app(tmp, False)
    out = _salvar(app, tarj, src, caixas, False)

    d = fitz.open(out)
    texto = "\n".join(p.get_text() for p in d)
    d.close()
    falhas = []
    if tarj.CPF_RE.findall(texto):
        falhas.append("sobrou CPF no texto: %s" % tarj.CPF_RE.findall(texto))
    if CPF_TXT.encode() in open(out, "rb").read():
        falhas.append("CPF nos bytes crus")
    if "Fulano de Tal" not in texto:
        falhas.append("apagou texto legitimo")
    return falhas


def _pdf_blindagem(tmp):
    """PDF com o CPF escondido em 5 lugares diferentes."""
    src = os.path.join(tmp, "blindagem.pdf")
    d = fitz.open()
    p = d.new_page()
    p.insert_text((72, 100), "Documento", fontsize=14)
    p.insert_text((72, 140), "CPF: " + CPF_TXT, fontsize=12)
    p.insert_text((72, 300), "Rodape que deve sobreviver", fontsize=10)
    p.draw_line(fitz.Point(70, 150), fitz.Point(300, 150), color=(1, 0, 0), width=2)

    w = fitz.Widget()
    w.field_name = "cpf_field"
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.rect = fitz.Rect(72, 175, 250, 195)
    w.field_value = CPF_FORM
    p.add_widget(w)
    p.add_text_annot(fitz.Point(80, 210), "CPF: " + CPF_ANOT)

    im = Image.new("RGB", (400, 60), "white")
    ImageDraw.Draw(im).text((10, 20), "CPF " + CPF_IMG, fill="black", font=_fonte(20))
    img = os.path.join(tmp, "cpf.png")
    im.save(img)
    p.insert_image(fitz.Rect(72, 230, 272, 260), filename=img)

    d.set_metadata({"title": "Ficha de " + CPF_META, "keywords": CPF_META})
    d.save(src)
    d.close()
    return src


def _caso_blindagem(tmp, rasterizar):
    src = _pdf_blindagem(tmp)
    app, tarj = _app(tmp, rasterizar)
    out = _salvar(app, tarj, src, {0: [fitz.Rect(65, 128, 320, 268)]}, rasterizar)

    d = fitz.open(out)
    texto = "\n".join(p.get_text() for p in d)
    meta = repr(d.metadata)
    anots = " ".join(repr(a.info) for p in d for a in p.annots())
    campos = " ".join(repr((w.field_name, w.field_value)) for p in d for w in p.widgets())
    pix = d[0].get_pixmap(clip=fitz.Rect(70, 133, 315, 263), dpi=100)
    cores = set(pix.pixel(x, y) for x in range(0, pix.width, 7)
                for y in range(0, pix.height, 7))
    rod = d[0].get_pixmap(clip=fitz.Rect(70, 290, 300, 310), dpi=100)
    rodape_visivel = len(set(rod.pixel(x, y) for x in range(0, rod.width, 3)
                             for y in range(0, rod.height, 3))) > 1
    d.close()
    bruto = open(out, "rb").read()

    falhas = []
    for cpf in (CPF_TXT, CPF_META, CPF_FORM, CPF_ANOT, CPF_IMG):
        if cpf in texto + meta + anots + campos:
            falhas.append("%s recuperavel pela API" % cpf)
        if cpf.encode() in bruto:
            falhas.append("%s nos bytes crus" % cpf)
    if cores != {(0, 0, 0)}:
        falhas.append("tarja nao renderiza preta: %s" % sorted(cores)[:4])
    if not rodape_visivel:
        falhas.append("apagou conteudo fora da tarja")
    if not rasterizar and not texto.strip():
        falhas.append("rasterizou sem precisar")
    return falhas


def caso_blindagem_normal(tmp):
    """Os 5 vetores, sem rasterizar."""
    return _caso_blindagem(tmp, False)


def caso_blindagem_raster(tmp):
    """Os 5 vetores, com rasterizacao ligada."""
    return _caso_blindagem(tmp, True)


def _pdf_foto(tmp, rot=0, marcador=False):
    foto = Image.new("RGB", (1200, 800), (205, 200, 190))
    d = ImageDraw.Draw(foto)
    for i in range(0, 1200, 13):
        d.line([(i, 0), (i, 800)], fill=(198, 193, 183))
    d.text((60, 90), "CARTEIRA DE IDENTIDADE", fill=(20, 20, 20), font=_fonte(36))
    if marcador:
        d.rectangle([50, 330, 780, 450], fill=MAGENTA)
    d.text((70, 350), CPF_IMG, fill=(0, 0, 0), font=_fonte(64))
    d.text((60, 640), "Rodape da foto", fill=(20, 20, 20), font=_fonte(36))
    jpg = os.path.join(tmp, "foto.jpg")
    foto.save(jpg, quality=95)

    src = os.path.join(tmp, "foto.pdf")
    doc = fitz.open()
    pg = doc.new_page()
    pg.insert_image(fitz.Rect(40, 40, 555, 383), filename=jpg, rotate=rot)
    pg.insert_text((40, 430), "Texto selecionavel", fontsize=11)
    doc.save(src)
    doc.close()
    return src


def _tarja_do_marcador(src):
    """Onde a faixa magenta cai na pagina, seguindo a matriz da imagem."""
    d = fitz.open(src)
    info = d[0].get_image_info(xrefs=True)[0]
    m = fitz.Matrix(info["transform"])
    u0, v0, u1, v1 = 50 / 1200., 330 / 800., 780 / 1200., 450 / 800.
    cantos = [fitz.Point(u0, v0) * m, fitz.Point(u1, v0) * m,
              fitz.Point(u0, v1) * m, fitz.Point(u1, v1) * m]
    d.close()
    return fitz.Rect(min(p.x for p in cantos), min(p.y for p in cantos),
                     max(p.x for p in cantos), max(p.y for p in cantos))


def _caso_foto(tmp, rasterizar, rot=0):
    src = _pdf_foto(tmp, rot=rot, marcador=True)
    tarja = _tarja_do_marcador(src)
    app, tarj = _app(tmp, rasterizar)
    out = _salvar(app, tarj, src, {0: [tarja]}, rasterizar)

    falhas = []
    d = fitz.open(out)
    # varre TODO objeto do arquivo, nao so as imagens ligadas a pagina
    for xref in range(1, d.xref_length()):
        try:
            base = d.extract_image(xref)
        except Exception:
            continue
        if not base:
            continue
        try:
            im = Image.open(io.BytesIO(base["image"]))
        except Exception:
            continue
        n = _pixels_magenta(im)
        if n:
            falhas.append("xref %d guardou %d pixels do marcador original" % (xref, n))
    pix = d[0].get_pixmap(clip=tarja + (2, 2, -2, -2), dpi=150)
    cores = set(pix.pixel(x, y) for x in range(0, pix.width, 4)
                for y in range(0, pix.height, 4))
    if cores != {(0, 0, 0)}:
        falhas.append("tarja nao renderiza preta: %s" % sorted(cores)[:4])
    texto = "\n".join(p.get_text() for p in d)
    d.close()
    if CPF_IMG.encode() in open(out, "rb").read():
        falhas.append("CPF nos bytes crus")
    if not rasterizar:
        if not texto.strip():
            falhas.append("rasterizou sem precisar - pintar a imagem deveria bastar")
        elif "Texto selecionavel" not in texto:
            falhas.append("perdeu o texto da pagina")
    return falhas


def caso_foto_normal(tmp):
    """CPF dentro de foto, pintando por dentro da imagem."""
    return _caso_foto(tmp, False)


def caso_foto_raster(tmp):
    """CPF dentro de foto, com rasterizacao ligada."""
    return _caso_foto(tmp, True)


def caso_foto_rot90(tmp):
    """Foto girada 90 graus na pagina."""
    return _caso_foto(tmp, False, rot=90)


def caso_foto_rot180(tmp):
    """Foto girada 180 graus na pagina."""
    return _caso_foto(tmp, False, rot=180)


def caso_foto_rot270(tmp):
    """Foto girada 270 graus na pagina."""
    return _caso_foto(tmp, False, rot=270)


def caso_salvar(tmp):
    """Nao sobrescreve arquivo existente; cria _2."""
    src = os.path.join(tmp, "dup.pdf")
    d = fitz.open()
    d.new_page().insert_text((72, 100), "CPF: " + CPF_TXT, fontsize=12)
    d.save(src)
    d.close()
    d = fitz.open(src)
    caixas = {0: [fitz.Rect(r) for r in d[0].search_for(CPF_TXT)]}
    d.close()

    import tarjador
    app, tarj = _app(tmp, False)
    app.load_pdf(src)
    app.update()
    app.boxes.update(caixas)
    app.save()
    app.save()
    app.boxes.clear()
    app.on_close()
    saidas = sorted(os.listdir(tarj.OUTPUT_DIR))
    falhas = []
    if len(saidas) != 2:
        falhas.append("esperava 2 arquivos, veio %s" % saidas)
    for nome in saidas:
        d = fitz.open(os.path.join(tarj.OUTPUT_DIR, nome))
        if tarjador.CPF_RE.findall("\n".join(p.get_text() for p in d)):
            falhas.append("%s ainda tem CPF" % nome)
        d.close()
    return falhas


def caso_interface(tmp):
    """Roda do mouse (inclusive Button-4/5 do X11), fonte e edicao de tarjas."""
    src = os.path.join(tmp, "ui.pdf")
    d = fitz.open()
    for i in range(3):
        d.new_page().insert_text((72, 100), "Pagina %d CPF: %s" % (i + 1, CPF_TXT), fontsize=14)
    d.save(src)
    d.close()

    app, _ = _app(tmp, False)
    app.load_pdf(src)
    app.update()
    falhas = []

    if not app.fonte_ui:
        falhas.append("nao resolveu a fonte do sistema")

    for ev in ("<Button-4>", "<Button-5>", "<Shift-Button-4>",
               "<Control-Button-5>", "<MouseWheel>"):
        if not app.canvas.bind(ev):
            falhas.append("falta binding para %s" % ev)

    class E:
        pass

    topo = app.canvas.yview()[0]
    app.on_wheel(app._roda(E(), -1))
    app.update()
    if app.canvas.yview()[0] <= topo:
        falhas.append("roda para baixo nao rolou")

    z = app.zoom
    app.on_ctrl_wheel(app._roda(E(), 1))
    app.update()
    if app.zoom <= z:
        falhas.append("Ctrl+roda nao deu zoom")

    # ida e volta das coordenadas
    for (cx, cy) in ((300, 200), (0, 0), (777, 555)):
        px, py = app.canvas_to_pdf(cx, cy)
        bx, by = app.pdf_to_canvas(px, py)
        if abs(bx - cx) > 1e-6 or abs(by - cy) > 1e-6:
            falhas.append("coordenada nao fecha em (%s,%s)" % (cx, cy))

    # desenhar, apagar com botao direito, desfazer
    ev = E()
    ev.x, ev.y = app.offset_x + 100, 150
    app.on_press(ev)
    ev2 = E()
    ev2.x, ev2.y = app.offset_x + 260, 175
    app.on_drag(ev2)
    app.on_release(ev2)
    app.update()
    if len(app.boxes.get(0, [])) != 1:
        falhas.append("arrastar o mouse nao criou a tarja")
    meio = E()
    meio.x, meio.y = app.offset_x + 180, 162
    app.on_right_click(meio)
    app.update()
    if app.boxes.get(0):
        falhas.append("botao direito nao apagou a tarja")

    app.detect_cpfs()
    app.update()
    if not app.boxes.get(0):
        falhas.append("Detectar CPFs nao achou nada")
    app.undo()
    app.update()

    app.boxes.clear()
    app.on_close()
    return falhas


CASOS = [
    ("texto", caso_texto),
    ("blindagem_normal", caso_blindagem_normal),
    ("blindagem_raster", caso_blindagem_raster),
    ("foto_normal", caso_foto_normal),
    ("foto_raster", caso_foto_raster),
    ("foto_rot90", caso_foto_rot90),
    ("foto_rot180", caso_foto_rot180),
    ("foto_rot270", caso_foto_rot270),
    ("salvar", caso_salvar),
    ("interface", caso_interface),
]


def rodar_um(nome):
    funcao = dict(CASOS)[nome]
    tmp = tempfile.mkdtemp(prefix="tarjador_teste_")
    try:
        falhas = funcao(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for f in falhas:
        print("   - %s" % f)
    return 1 if falhas else 0


def main():
    if "--lista" in sys.argv:
        for nome, funcao in CASOS:
            print("%-18s %s" % (nome, (funcao.__doc__ or "").strip().splitlines()[0]))
        return 0
    if len(sys.argv) > 1:
        return rodar_um(sys.argv[1])

    print("Bateria do Tarjador - %s" % sys.platform)
    print("Python %s | PyMuPDF %s" % (sys.version.split()[0], fitz.__doc__.split()[1]))
    if sys.platform.startswith("linux"):
        print("DISPLAY=%s" % os.environ.get("DISPLAY", "(vazio - use xvfb-run)"))
    print("-" * 58)
    ok = 0
    ruins = []
    for nome, _f in CASOS:
        # processo separado: dois Tk() no mesmo processo brigam entre si
        r = subprocess.run([sys.executable, os.path.abspath(__file__), nome],
                           capture_output=True, text=True)
        passou = r.returncode == 0
        print("%-6s %-18s" % ("OK" if passou else "FALHA", nome))
        if passou:
            ok += 1
        else:
            ruins.append(nome)
            saida = (r.stdout + r.stderr).strip()
            if saida:
                print("\n".join("       " + l for l in saida.splitlines()[-12:]))
    print("-" * 58)
    print("%d/%d passaram" % (ok, len(CASOS)))
    return 1 if ruins else 0


if __name__ == "__main__":
    sys.exit(main())
