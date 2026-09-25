#!/usr/bin/env python3
"""Gestisce le credenziali METEOHUB di StormShift nel Windows Credential Manager."""

from __future__ import annotations

import argparse
import ctypes
import getpass
from ctypes import POINTER, Structure, byref, cast, wintypes


CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
EMAIL_TARGET = "StormShift/METEOHUB_EMAIL"
KEY_TARGET = "StormShift/METEOHUB_ARCO_ACCESS_KEY"
# Sono SOLO i nomi delle voci nel Credential Manager: i valori veri (email e
# ARCO Access Key) li salva "python stormshift_meteohub_secrets.py set" e non
# devono mai comparire nel codice.
LPBYTE = POINTER(wintypes.BYTE)


class FILETIME(Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


class CREDENTIALW(Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", LPBYTE),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", wintypes.LPVOID),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


PCREDENTIALW = POINTER(CREDENTIALW)
advapi32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
cred_write = advapi32.CredWriteW
cred_write.argtypes = [POINTER(CREDENTIALW), wintypes.DWORD]
cred_write.restype = wintypes.BOOL
cred_read = advapi32.CredReadW
cred_read.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, POINTER(PCREDENTIALW)]
cred_read.restype = wintypes.BOOL
cred_free = advapi32.CredFree
cred_free.argtypes = [wintypes.LPVOID]
cred_free.restype = None
user32 = ctypes.WinDLL("User32.dll", use_last_error=True)
open_clipboard = user32.OpenClipboard
open_clipboard.argtypes = [wintypes.HWND]
open_clipboard.restype = wintypes.BOOL
get_clipboard_data = user32.GetClipboardData
get_clipboard_data.argtypes = [wintypes.UINT]
get_clipboard_data.restype = wintypes.HANDLE
empty_clipboard = user32.EmptyClipboard
empty_clipboard.argtypes = []
empty_clipboard.restype = wintypes.BOOL
close_clipboard = user32.CloseClipboard
close_clipboard.argtypes = []
close_clipboard.restype = wintypes.BOOL
CF_UNICODETEXT = 13


def _write_credential(target: str, value: str) -> None:
    """Salva un valore UTF-16 nel vault dell'utente Windows corrente."""
    data = ctypes.create_unicode_buffer(value)
    credential = CREDENTIALW(
        Type=CRED_TYPE_GENERIC,
        TargetName=target,
        CredentialBlobSize=len(value.encode("utf-16-le")),
        CredentialBlob=cast(data, LPBYTE),
        Persist=CRED_PERSIST_LOCAL_MACHINE,
        UserName="StormShift",
    )
    if not cred_write(byref(credential), 0):
        raise ctypes.WinError(ctypes.get_last_error())


def _read_credential(target: str) -> str | None:
    """Legge un valore dal vault senza stamparlo o registrarlo."""
    credential = PCREDENTIALW()
    if not cred_read(target, CRED_TYPE_GENERIC, 0, byref(credential)):
        error = ctypes.get_last_error()
        if error == 1168:  # ERROR_NOT_FOUND
            return None
        raise ctypes.WinError(error)
    try:
        item = credential.contents
        raw = ctypes.string_at(item.CredentialBlob, item.CredentialBlobSize)
        return raw.decode("utf-16-le")
    finally:
        cred_free(credential)


def get_arco_credentials() -> tuple[str, str]:
    """Restituisce email e ARCO Access Key per un backend StormShift locale."""
    email = _read_credential(EMAIL_TARGET)
    access_key = _read_credential(KEY_TARGET)
    if not email or not access_key:
        raise RuntimeError(
            "Credenziali METEOHUB mancanti. Esegui: "
            "python stormshift_meteohub_secrets.py set"
        )
    return email, access_key


def set_credentials() -> None:
    """Richiede le credenziali senza mostrarle e le salva nel vault Windows."""
    email = input("Email associata a METEOHUB: ").strip()
    access_key = getpass.getpass("ARCO Access Key (input nascosto): ").strip()
    save_credentials(email, access_key)


def save_credentials(email: str, access_key: str) -> None:
    """Salva valori validati nel vault dell'utente Windows corrente."""
    if not email or not access_key:
        raise ValueError("Email e ARCO Access Key sono obbligatorie.")
    _write_credential(EMAIL_TARGET, email)
    _write_credential(KEY_TARGET, access_key)
    print("Credenziali METEOHUB salvate nel Windows Credential Manager.")


def set_credentials_from_clipboard() -> None:
    """Legge la chiave dalla clipboard e la svuota subito dopo l'acquisizione."""
    email = input("Email associata a METEOHUB: ").strip()
    if not open_clipboard(None):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        handle = get_clipboard_data(CF_UNICODETEXT)
        if not handle:
            raise ValueError("La clipboard non contiene testo.")
        access_key = ctypes.wstring_at(handle).strip()
        if not empty_clipboard():
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        close_clipboard()
    save_credentials(email, access_key)


def print_status() -> None:
    """Mostra soltanto se entrambe le credenziali sono presenti."""
    configured = bool(_read_credential(EMAIL_TARGET) and _read_credential(KEY_TARGET))
    print("METEOHUB configurato." if configured else "METEOHUB non configurato.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Archivio sicuro locale per le credenziali METEOHUB di StormShift."
    )
    parser.add_argument(
        "command",
        choices=("set", "set-from-clipboard", "status"),
        help="Operazione da eseguire",
    )
    args = parser.parse_args()
    if args.command == "set":
        set_credentials()
    elif args.command == "set-from-clipboard":
        set_credentials_from_clipboard()
    else:
        print_status()


if __name__ == "__main__":
    main()
