import asyncio
import socket
import ssl
import os
from typing import Optional, Callable, Any, Set, Dict, List

from . import _cepoll as cepoll


class EpollEventLoop:
    """Minimal epoll based event loop implemented in Python."""

    def __init__(self) -> None:
        self.epoll_fd = cepoll.create(1024)
        self.callbacks: Dict[int, Callable[[], Any]] = {}
        self.active_fds: Set[int] = set()
        self.running = False
        self.fd_to_callback: Dict[int, Dict[str, Any]] = {}

    def __del__(self) -> None:
        if getattr(self, "epoll_fd", -1) != -1:
            os.close(self.epoll_fd)

    def add_reader(self, fd: int, callback: Callable[[], Any]) -> None:
        cepoll.ctl(
            self.epoll_fd, cepoll.EPOLL_CTL_ADD, fd, cepoll.EPOLLIN | cepoll.EPOLLET
        )
        self.active_fds.add(fd)
        self.fd_to_callback[fd] = {"type": "reader", "callback": callback}

    def add_writer(self, fd: int, callback: Callable[[], Any]) -> None:
        cepoll.ctl(
            self.epoll_fd, cepoll.EPOLL_CTL_ADD, fd, cepoll.EPOLLOUT | cepoll.EPOLLET
        )
        self.active_fds.add(fd)
        self.fd_to_callback[fd] = {"type": "writer", "callback": callback}

    def remove_reader(self, fd: int) -> None:
        try:
            cepoll.ctl(self.epoll_fd, cepoll.EPOLL_CTL_DEL, fd, 0)
        except OSError:
            pass
        self.active_fds.discard(fd)
        self.fd_to_callback.pop(fd, None)

    def remove_writer(self, fd: int) -> None:
        try:
            cepoll.ctl(self.epoll_fd, cepoll.EPOLL_CTL_DEL, fd, 0)
        except OSError:
            pass
        self.active_fds.discard(fd)
        self.fd_to_callback.pop(fd, None)

    async def run_forever(self) -> None:
        self.running = True
        import errno

        while self.running:
            # Wait up to 0.1 second so that stop() can exit promptly.
            try:
                events = await asyncio.to_thread(cepoll.wait, self.epoll_fd, 1024, 100)
            except OSError as e:
                if e.errno == errno.EINTR:
                    continue
                raise
            for fd, ev in events:
                info = self.fd_to_callback.get(fd)
                if not info:
                    continue
                callback = info["callback"]
                try:
                    result = callback()
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:  # pragma: no cover - debug aid
                    print(f"Callback error for fd {fd}: {e}")

    def stop(self) -> None:
        self.running = False

    @property
    def is_running(self) -> bool:
        return self.running

    @property
    def active_file_descriptors(self) -> Set[int]:
        return self.active_fds.copy()


class EpollNetworkStream:
    """Network stream using the epoll event loop."""

    def __init__(self, sock: socket.socket, loop: EpollEventLoop) -> None:
        self.sock = sock
        self.loop = loop
        self.closed = False
        self.read_future: Optional[asyncio.Future] = None
        self.write_future: Optional[asyncio.Future] = None

    async def read(self, max_bytes: Optional[int] = None) -> bytes:
        if self.closed:
            raise RuntimeError("Stream is closed")
        if max_bytes is None:
            max_bytes = 8192
        data = bytearray()
        while len(data) < max_bytes:
            try:
                chunk = self.sock.recv(max_bytes - len(data))
                if not chunk:
                    break
                data.extend(chunk)
            except BlockingIOError:
                await self._wait_for_read()
        return bytes(data)

    async def write(self, data: bytes) -> None:
        if self.closed:
            raise RuntimeError("Stream is closed")
        total = 0
        while total < len(data):
            try:
                sent = self.sock.send(data[total:])
                total += sent
            except BlockingIOError:
                await self._wait_for_write()

    async def _wait_for_read(self) -> None:
        if self.read_future is None:
            self.read_future = asyncio.Future()
            self.loop.add_reader(self.sock.fileno(), self._read_ready)
        await self.read_future
        self.read_future = None

    async def _wait_for_write(self) -> None:
        if self.write_future is None:
            self.write_future = asyncio.Future()
            self.loop.add_writer(self.sock.fileno(), self._write_ready)
        await self.write_future
        self.write_future = None

    def _read_ready(self) -> None:
        if self.read_future and not self.read_future.done():
            self.read_future.set_result(None)
        self.loop.remove_reader(self.sock.fileno())

    def _write_ready(self) -> None:
        if self.write_future and not self.write_future.done():
            self.write_future.set_result(None)
        self.loop.remove_writer(self.sock.fileno())

    async def aclose(self) -> None:
        if not self.closed:
            try:
                self.loop.remove_reader(self.sock.fileno())
                self.loop.remove_writer(self.sock.fileno())
            except Exception:
                pass
            self.sock.close()
            self.closed = True

    def get_extra_info(self, name: str) -> Optional[Any]:
        if name == "socket":
            return self.sock
        elif name == "peername":
            try:
                return self.sock.getpeername()
            except OSError:
                return None
        elif name == "sockname":
            try:
                return self.sock.getsockname()
            except OSError:
                return None
        elif name == "ssl_object":
            return isinstance(self.sock, ssl.SSLSocket)
        return None

    @property
    def is_closed(self) -> bool:
        return self.closed


class EpollNetworkBackend:
    """Network backend using the epoll event loop."""

    def __init__(self) -> None:
        self.loop = EpollEventLoop()

    async def connect_tcp(
        self, host: str, port: int, timeout: Optional[float] = None
    ) -> EpollNetworkStream:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setblocking(False)
        try:
            sock.connect((host, port))
        except (BlockingIOError, InterruptedError):
            pass
        future = asyncio.get_event_loop().create_future()

        def writer():
            if not future.done():
                future.set_result(None)

        self.loop.add_writer(sock.fileno(), writer)
        try:
            if timeout is not None:
                await asyncio.wait_for(future, timeout)
            else:
                await future
        finally:
            self.loop.remove_writer(sock.fileno())
        return EpollNetworkStream(sock, self.loop)

    async def connect_tls(
        self,
        stream: EpollNetworkStream,
        host: str,
        port: int,
        timeout: Optional[float] = None,
        alpn_protocols: Optional[List[str]] = None,
    ) -> EpollNetworkStream:
        context = ssl.create_default_context()
        if alpn_protocols:
            context.set_alpn_protocols(alpn_protocols)
        ssl_sock = context.wrap_socket(
            stream.sock, server_hostname=host, do_handshake_on_connect=False
        )
        ssl_sock.setblocking(False)
        new_stream = EpollNetworkStream(ssl_sock, self.loop)
        # perform handshake
        while True:
            try:
                ssl_sock.do_handshake()
                break
            except ssl.SSLWantReadError:
                await new_stream._wait_for_read()
            except ssl.SSLWantWriteError:
                await new_stream._wait_for_write()
        return new_stream

    async def start_tls(
        self,
        stream: EpollNetworkStream,
        host: str,
        alpn_protocols: Optional[List[str]] = None,
    ) -> EpollNetworkStream:
        return await self.connect_tls(stream, host, 0, None, alpn_protocols)

    def get_event_loop(self) -> EpollEventLoop:
        return self.loop
