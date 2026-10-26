"""Explicit credential references, DPAPI on Windows and owner-only files on Linux."""
import base64
import json
import os
from pathlib import Path
import re
import stat

from .records import Store,atomic_json


def _dpapi(data, decrypt=False):
    import ctypes
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_=[("size",wintypes.DWORD),("data",ctypes.POINTER(ctypes.c_ubyte))]
    raw=ctypes.create_string_buffer(data)
    source=Blob(len(data),ctypes.cast(raw,ctypes.POINTER(ctypes.c_ubyte)))
    output=Blob()
    crypt=ctypes.WinDLL("crypt32",use_last_error=True)
    if decrypt:
        method=crypt.CryptUnprotectData
        description_type=ctypes.POINTER(wintypes.LPWSTR)
    else:
        method=crypt.CryptProtectData
        description_type=wintypes.LPCWSTR
    method.argtypes=[ctypes.POINTER(Blob),description_type,ctypes.POINTER(Blob),wintypes.LPVOID,wintypes.LPVOID,wintypes.DWORD,ctypes.POINTER(Blob)]
    method.restype=wintypes.BOOL
    if not method(ctypes.byref(source),None,None,None,None,1,ctypes.byref(output)):
        raise ValueError("Windows could not protect or read this credential for the current user.")
    try:
        return ctypes.string_at(output.data,output.size)
    finally:
        kernel=ctypes.WinDLL("kernel32",use_last_error=True)
        kernel.LocalFree.argtypes=[wintypes.HLOCAL]
        kernel.LocalFree.restype=wintypes.HLOCAL
        kernel.LocalFree(ctypes.cast(output.data,wintypes.HLOCAL))


class Credentials:
    def __init__(self,root):
        self.root=Path(root)
        if self.root.is_symlink():
            raise ValueError("Credential storage must be a private directory, not a link.")
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        self._permissions(self.root,directory=True)

    @staticmethod
    def _permissions(path,directory=False):
        if path.is_symlink():
            raise ValueError("Credential links are not permitted.")
        if os.name!="nt":
            info=path.stat()
            if info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)&0o077:
                raise ValueError("Credential storage must be accessible only to its owning user.")

    def _path(self,reference):
        if not isinstance(reference,str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}",reference):
            raise ValueError("Select an explicit saved credential reference.")
        return self.root/(reference+".json")

    def _update_lock(self):
        self._permissions(self.root,directory=True)
        directory=self.root/".updates"
        if directory.is_symlink(): raise ValueError("Credential update state cannot be a link.")
        directory.mkdir(mode=0o700,exist_ok=True)
        self._permissions(directory,directory=True)
        return Store(directory).allocation_lock()

    @staticmethod
    def _check_value(value):
        if not isinstance(value,str) or not 1<=len(value)<=16384 or any(ord(c)<32 for c in value):
            raise ValueError("Enter a nonempty credential without line breaks.")

    def exists(self,reference):
        self._permissions(self.root,directory=True)
        path=self._path(reference)
        if path.is_symlink(): raise ValueError("Credential links are not permitted.")
        return path.exists()

    def save(self,reference,value,*,overwrite=False):
        self._path(reference); self._check_value(value)
        with self._update_lock():
            self._save(reference,value,overwrite=overwrite)

    def replace_if(self,reference,expected,value):
        self._path(reference); self._check_value(value)
        with self._update_lock():
            if self.read(reference)!=expected:
                raise ValueError("The credential changed during refresh. Recheck the original account before continuing.")
            self._save(reference,value,overwrite=True)

    def _save(self,reference,value,*,overwrite=False):
        path=self._path(reference)
        self._permissions(self.root,directory=True)
        if path.exists() and not overwrite:
            raise ValueError("This credential reference already exists. Choose a new reference or explicitly replace it.")
        self._check_value(value)
        if os.name=="nt":
            content={"schema":1,"format":"dpapi-user","value":base64.b64encode(_dpapi(value.encode())).decode("ascii")}
        else:
            content={"schema":1,"format":"owner-only-file","value":value}
        atomic_json(path,content)
        self._permissions(path)

    def read(self,reference):
        try:
            self._permissions(self.root,directory=True)
            path=self._path(reference)
            self._permissions(path)
            if path.stat().st_size>65536:
                raise ValueError("Invalid credential record.")
            content=json.loads(path.read_text(encoding="utf-8"))
            if set(content)!={"schema","format","value"} or type(content["schema"]) is not int or content["schema"]!=1:
                raise ValueError("Invalid credential record.")
            if os.name=="nt" and content["format"]=="dpapi-user":
                value=_dpapi(base64.b64decode(content["value"],validate=True),decrypt=True).decode("utf-8")
            elif os.name!="nt" and content["format"]=="owner-only-file":
                value=content["value"]
            else:
                raise ValueError("Credential belongs to a different storage environment.")
            if not isinstance(value,str) or not 1<=len(value)<=16384 or any(ord(c)<32 for c in value):
                raise ValueError("Invalid credential value.")
            return value
        except (OSError,ValueError,TypeError,KeyError,UnicodeError):
            raise ValueError("The explicitly selected credential could not be read. Re-enter it for this connection.") from None
