"""Guarda login/senha do SIGA no Gerenciador de Credenciais do Windows (via keyring)."""
import keyring

SERVICO = "SIGA-arcoconsultoria"
CHAVE_USUARIO = "__usuario__"


def salvar(usuario: str, senha: str) -> None:
    keyring.set_password(SERVICO, CHAVE_USUARIO, usuario)
    keyring.set_password(SERVICO, usuario, senha)


def carregar():
    """Retorna (usuario, senha) ou None se nada salvo."""
    usuario = keyring.get_password(SERVICO, CHAVE_USUARIO)
    if not usuario:
        return None
    senha = keyring.get_password(SERVICO, usuario)
    if senha is None:
        return None
    return usuario, senha


def apagar() -> None:
    usuario = keyring.get_password(SERVICO, CHAVE_USUARIO)
    for chave in filter(None, [usuario, CHAVE_USUARIO]):
        try:
            keyring.delete_password(SERVICO, chave)
        except keyring.errors.PasswordDeleteError:
            pass
