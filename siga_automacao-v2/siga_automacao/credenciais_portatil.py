"""Credenciais SIGA criptografadas com DPAPI por conta do Windows; sem keyring externo."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import json

ARQUIVO=Path(__file__).resolve().parent/'credenciais_siga_protegidas.dat'
class BLOB(ctypes.Structure):
    _fields_=[('cbData',wintypes.DWORD),('pbData',ctypes.POINTER(ctypes.c_byte))]

def blob(b):
    buf=ctypes.create_string_buffer(b)
    return BLOB(len(b),ctypes.cast(buf,ctypes.POINTER(ctypes.c_byte))),buf

def proteger(data):
    entrada,keep=blob(data); saida=BLOB()
    api=ctypes.windll.crypt32
    ctypes.windll.kernel32.LocalFree.argtypes=[ctypes.c_void_p]
    ctypes.windll.kernel32.LocalFree.restype=ctypes.c_void_p
    if not api.CryptProtectData(ctypes.byref(entrada),None,None,None,None,0,ctypes.byref(saida)):
        raise ctypes.WinError()
    try: return ctypes.string_at(saida.pbData,saida.cbData)
    finally: ctypes.windll.kernel32.LocalFree(saida.pbData)

def desproteger(data):
    entrada,keep=blob(data); saida=BLOB()
    api=ctypes.windll.crypt32
    ctypes.windll.kernel32.LocalFree.argtypes=[ctypes.c_void_p]
    ctypes.windll.kernel32.LocalFree.restype=ctypes.c_void_p
    if not api.CryptUnprotectData(ctypes.byref(entrada),None,None,None,None,0,ctypes.byref(saida)):
        raise ctypes.WinError()
    try:return ctypes.string_at(saida.pbData,saida.cbData)
    finally:ctypes.windll.kernel32.LocalFree(saida.pbData)

def salvar(usuario,senha):
    ARQUIVO.write_bytes(proteger(json.dumps([usuario,senha]).encode('utf8')))

def carregar():
    if not ARQUIVO.exists():return None
    return tuple(json.loads(desproteger(ARQUIVO.read_bytes()).decode('utf8')))

def apagar():
    ARQUIVO.unlink(missing_ok=True)
