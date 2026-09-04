#!/usr/bin/env bash
# Lancador do Tarjador de PDFs no Linux e no macOS.
# Equivalente ao Tarjador.bat do Windows.
#
#   chmod +x tarjador.sh     (so na primeira vez)
#   ./tarjador.sh
set -euo pipefail

# ---- vai para a pasta do script (resolvendo link simbolico quando da)
ALVO="$0"
if command -v readlink >/dev/null 2>&1 && readlink -f "$0" >/dev/null 2>&1; then
    ALVO="$(readlink -f "$0")"   # readlink -f nao existe no macOS antigo
fi
cd "$(cd "$(dirname "$ALVO")" && pwd)"

VENV=".venv/bin/python"
tem_deps() { "$1" -c "import tkinter, pymupdf, PIL" >/dev/null 2>&1; }

# ---- ja existe um ambiente local pronto? usa e pronto
if [ -x "$VENV" ] && tem_deps "$VENV"; then
    exec "$VENV" tarjador.py "$@"
fi

PY=""
for candidato in python3 python; do
    if command -v "$candidato" >/dev/null 2>&1 &&
       "$candidato" -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" 2>/dev/null
    then
        PY="$candidato"
        break
    fi
done
if [ -z "$PY" ]; then
    echo "Python 3.8 ou mais novo nao encontrado. Instale o Python 3 e rode de novo." >&2
    exit 1
fi

# ---- tkinter nao se instala com pip: vem em pacote do sistema
if ! "$PY" -c "import tkinter" >/dev/null 2>&1; then
    echo "Falta o tkinter (a interface grafica), que nao vem pelo pip." >&2
    if   command -v apt    >/dev/null 2>&1; then echo "  sudo apt install python3-tk" >&2
    elif command -v dnf    >/dev/null 2>&1; then echo "  sudo dnf install python3-tkinter" >&2
    elif command -v pacman >/dev/null 2>&1; then echo "  sudo pacman -S tk" >&2
    elif command -v zypper >/dev/null 2>&1; then echo "  sudo zypper install python3-tk" >&2
    elif command -v apk    >/dev/null 2>&1; then echo "  sudo apk add python3-tkinter" >&2
    elif command -v brew   >/dev/null 2>&1; then echo "  brew install python-tk" >&2
    else echo "  procure por 'python3-tk' ou 'python3-tkinter' no seu sistema" >&2
    fi
    exit 1
fi

# ---- PyMuPDF e Pillow
if ! "$PY" -c "import pymupdf, PIL" >/dev/null 2>&1; then
    echo "Instalando dependencias (so na primeira vez)..."
    # --user falha nas distros que marcam o Python como "externally managed"
    # (PEP 668). Nesse caso caimos para um venv local, que sempre funciona.
    if "$PY" -m pip install --user -r requirements.txt >/dev/null 2>&1; then
        echo "Pronto."
    else
        echo "O pip do sistema esta bloqueado; criando ambiente local em .venv ..."
        # --system-site-packages para o venv enxergar o tkinter do sistema
        if ! "$PY" -m venv --system-site-packages .venv; then
            echo "Falhou ao criar o .venv. Instale o pacote python3-venv e tente de novo." >&2
            exit 1
        fi
        "$VENV" -m pip install --upgrade pip >/dev/null
        "$VENV" -m pip install -r requirements.txt
        PY="$VENV"
    fi
fi

exec "$PY" tarjador.py "$@"
