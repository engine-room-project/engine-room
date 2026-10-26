"""Bounded, backpressured Linux stdio/socket streaming with repeated authorization."""
import os
import selectors
import socket
import time

BUFFER=262144
CHUNK=65536


def duplex(peer,input_fd,output_fd,authorized,*,clock=time.monotonic,interval=5,request=None):
    # The SSH bridge calls this on Linux. No requests, prompts or tokens are logged.
    incoming=bytearray(); outgoing=bytearray()
    input_eof=request is not None; peer_eof=False; shutdown=False
    pending=memoryview(request) if request is not None else memoryview(b"")
    previous={fd:os.get_blocking(fd) for fd in (input_fd,output_fd)}
    peer.setblocking(False)
    for fd in previous: os.set_blocking(fd,False)
    next_check=clock()
    try:
        with selectors.DefaultSelector() as selector:
            while True:
                if clock()>=next_check:
                    if not authorized(): return
                    next_check=clock()+interval
                if pending and len(incoming)<BUFFER:
                    count=min(len(pending),BUFFER-len(incoming)); incoming.extend(pending[:count]); pending=pending[count:]
                if peer_eof and not outgoing: return
                if input_eof and not incoming and not pending and not shutdown:
                    peer.shutdown(socket.SHUT_WR); shutdown=True
                # Rebuilding three registrations keeps state simple and buffers bounded.
                for key in list(selector.get_map().values()): selector.unregister(key.fileobj)
                mask=(selectors.EVENT_READ if not peer_eof and len(outgoing)<BUFFER else 0)|(selectors.EVENT_WRITE if incoming else 0)
                if mask: selector.register(peer,mask,"peer")
                if not input_eof and not peer_eof and len(incoming)<BUFFER: selector.register(input_fd,selectors.EVENT_READ,"input")
                if outgoing: selector.register(output_fd,selectors.EVENT_WRITE,"output")
                for key,events in selector.select(timeout=min(1,max(0,next_check-clock()))):
                    try:
                        if key.data=="input":
                            data=os.read(input_fd,min(CHUNK,BUFFER-len(incoming)))
                            if data: incoming.extend(data)
                            else: input_eof=True
                        elif key.data=="output":
                            sent=os.write(output_fd,outgoing[:CHUNK]); del outgoing[:sent]
                        else:
                            if events&selectors.EVENT_READ:
                                data=peer.recv(min(CHUNK,BUFFER-len(outgoing)))
                                if data: outgoing.extend(data)
                                else: peer_eof=True
                            if events&selectors.EVENT_WRITE and incoming:
                                sent=peer.send(incoming[:CHUNK]); del incoming[:sent]
                    except BlockingIOError: pass
    finally:
        for fd,blocking in previous.items():
            try: os.set_blocking(fd,blocking)
            except OSError: pass
