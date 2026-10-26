"""Selected-model validation shared by local and controller request boundaries."""
import json
import os
import selectors
import time

ROUTES={"GET":{"/v1/models","/health"},"POST":{"/v1/chat/completions","/v1/completions","/v1/embeddings","/v1/responses"}}
LIMIT=64*1024*1024


def validate_body(body,model):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result: raise ValueError("Ambiguous JSON request.")
            result[key]=value
        return result
    def invalid(value): raise ValueError("Invalid JSON constant.")
    document=json.loads(body.decode("utf-8"),object_pairs_hook=unique,parse_constant=invalid)
    if not isinstance(document,dict) or document.get("model")!=model:
        raise ValueError("Choose the exact selected model.")


def guarded_request(input_fd,model,authorized,*,seconds=15,clock=time.monotonic):
    if not isinstance(model,str) or not model or len(model)>500 or any(ord(c)<32 for c in model):
        raise ValueError("An explicit selected model is required.")
    until=clock()+seconds; next_check=clock()
    with selectors.DefaultSelector() as selector:
        selector.register(input_fd,selectors.EVENT_READ)
        def read(size):
            nonlocal next_check
            while True:
                now=clock(); remaining=until-now
                if remaining<=0: raise ValueError("Request authorization expired.")
                if now>=next_check:
                    if not authorized(): raise ValueError("Request authorization expired.")
                    next_check=clock()+1
                if selector.select(min(1,remaining)):
                    part=os.read(input_fd,size)
                    if not part: raise ValueError("Incomplete request.")
                    return part
        header=bytearray()
        while not header.endswith(b"\r\n\r\n"):
            if len(header)>=16384: raise ValueError("Request headers are too large.")
            header.extend(read(1))
        lines=header.decode("ascii").split("\r\n")
        method,path,version=lines[0].split(" ")
        if version!="HTTP/1.1" or path not in ROUTES.get(method,set()): raise ValueError("Unsupported model route.")
        headers={}
        for line in lines[1:-2]:
            name,separator,value=line.partition(":")
            if not separator or not name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for c in name):
                raise ValueError("Malformed request header.")
            name=name.lower()
            if name in headers: raise ValueError("Duplicate request header.")
            value=value.strip()
            if any(ord(c)<32 or ord(c)==127 for c in value): raise ValueError("Invalid request header.")
            headers[name]=value
        if "transfer-encoding" in headers: raise ValueError("Chunked request bodies are unsupported.")
        size=headers.get("content-length","0")
        if not size.isascii() or not size.isdigit() or len(size)>10: raise ValueError("Invalid request length.")
        size=int(size)
        if size>LIMIT or (method=="GET" and size) or (method=="POST" and ("content-length" not in headers or headers.get("content-type","").partition(";")[0].strip().lower()!="application/json")):
            raise ValueError("Send one bounded JSON request.")
        body=bytearray()
        while len(body)<size: body.extend(read(min(65536,size-len(body))))
        if method=="POST": validate_body(body,model)
        if not authorized(): raise ValueError("Request authorization expired.")
        canonical=(method+" "+path+" HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\nContent-Type: application/json\r\nAccept: application/json, text/event-stream\r\nContent-Length: "+str(size)+"\r\n\r\n").encode()
        return canonical+body
