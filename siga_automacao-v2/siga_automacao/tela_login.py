"""Janela simples para digitar login e senha do SIGA."""
import tkinter as tk
from tkinter import ttk


def pedir_credenciais(usuario_inicial: str = "", erro: str = ""):
    """Mostra a janela. Retorna (usuario, senha, lembrar) ou None se cancelar."""
    resultado = {}

    root = tk.Tk()
    root.title("SIGA - Login")
    root.resizable(False, False)
    root.attributes("-topmost", True)

    frm = ttk.Frame(root, padding=20)
    frm.grid()

    ttk.Label(frm, text="Acesso ao SIGA", font=("Segoe UI", 13, "bold")).grid(
        column=0, row=0, columnspan=2, pady=(0, 12))

    ttk.Label(frm, text="Login:").grid(column=0, row=1, sticky="w")
    var_user = tk.StringVar(value=usuario_inicial)
    ent_user = ttk.Entry(frm, textvariable=var_user, width=30)
    ent_user.grid(column=1, row=1, pady=4)

    ttk.Label(frm, text="Senha:").grid(column=0, row=2, sticky="w")
    var_senha = tk.StringVar()
    ent_senha = ttk.Entry(frm, textvariable=var_senha, show="•", width=30)
    ent_senha.grid(column=1, row=2, pady=4)

    var_lembrar = tk.BooleanVar(value=True)
    ttk.Checkbutton(frm, text="Lembrar neste computador (login automático)",
                    variable=var_lembrar).grid(column=0, row=3, columnspan=2, sticky="w", pady=6)

    lbl_msg = ttk.Label(frm, text=erro, foreground="red", wraplength=300)
    lbl_msg.grid(column=0, row=4, columnspan=2)

    def confirmar(_=None):
        u, s = var_user.get().strip(), var_senha.get()
        if not u or not s:
            lbl_msg.config(text="Preencha login e senha.")
            return
        resultado.update(usuario=u, senha=s, lembrar=var_lembrar.get())
        root.destroy()

    botoes = ttk.Frame(frm)
    botoes.grid(column=0, row=5, columnspan=2, pady=(10, 0))
    ttk.Button(botoes, text="Entrar", command=confirmar).grid(column=0, row=0, padx=4)
    ttk.Button(botoes, text="Cancelar", command=root.destroy).grid(column=1, row=0, padx=4)

    root.bind("<Return>", confirmar)
    root.bind("<Escape>", lambda _: root.destroy())
    (ent_senha if usuario_inicial else ent_user).focus_set()

    root.update_idletasks()
    x = (root.winfo_screenwidth() - root.winfo_width()) // 2
    y = (root.winfo_screenheight() - root.winfo_height()) // 3
    root.geometry(f"+{x}+{y}")
    root.mainloop()

    if not resultado:
        return None
    return resultado["usuario"], resultado["senha"], resultado["lembrar"]
