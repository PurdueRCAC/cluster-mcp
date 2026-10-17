# Planning prototype for restore-test-coverage (2026-10-16), kept as evidence for research/; not a test.
# Run from the worktree root: uv run python spec/restore-test-coverage/research/prototypes/isolation_over_http.py [args]
import asyncio, contextvars, os, sys, tempfile, subprocess, datetime as dt
import httpx, jwt
os.environ['JWT_SECRET'] = 's' * 32
d = tempfile.mkdtemp(); m = os.path.join(d, 'map')
open(m, 'w').write('alice ualice\nbob ubob\nal@x.org uemail\n')
launches = []
class FakePopen:
    def __init__(self, args, **kw):
        launches.append(list(args)); self.args = args; self.returncode = None; self.text = kw.get('text')
        self.pid = 4242
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def communicate(self, input=None, timeout=None):
        self.returncode = 0
        out = f"{self.args[4]}|{self.args[-1]}"
        return (out, '') if self.text else (out.encode(), b'')
    def poll(self): return self.returncode
    def wait(self, timeout=None): return self.returncode
    def kill(self): pass
subprocess.Popen = FakePopen
PLANT = sys.argv[1] == 'plant'
import rcac_mcp.context as ctx
if PLANT:
    class G:
        v = None
        def get(self): return G.v
        def set(self, x): G.v = x
    ctx.executor_var = G()
from rcac_mcp.server import create_mcp_server
from rcac_mcp.middleware import AuthExecutorMiddleware
from rcac_mcp.token import ISSUER, AUDIENCE, ALGORITHM
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.server.middleware import Middleware

class Rendezvous(Middleware):
    def __init__(self, n): self.b = asyncio.Barrier(n)
    async def on_call_tool(self, context, call_next):
        async with asyncio.timeout(5):
            await self.b.wait()
        return await call_next(context)

def tok(**claims):
    now = dt.datetime.now(dt.timezone.utc)
    return jwt.encode({'iss': ISSUER, 'aud': AUDIENCE, 'iat': now, 'exp': now + dt.timedelta(minutes=5), **claims}, os.environ['JWT_SECRET'], algorithm=ALGORITHM)

def http_client(app, token):
    def f(headers=None, auth=None, follow_redirects=True, timeout=None, **kw):
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t', headers=headers, auth=auth, follow_redirects=True)
    return Client(StreamableHttpTransport('http://t/mcp', auth=token, httpx_client_factory=f))

async def main():
    server = create_mcp_server('jwt', middlewares=[AuthExecutorMiddleware('jwt', m)])
    rv = Rendezvous(2); server.add_middleware(rv)
    app = server.http_app()
    async with app.router.lifespan_context(app):
        async with http_client(app, tok(sub='alice')) as a, http_client(app, tok(sub='bob')) as b:
            ra, rb = await asyncio.gather(a.call_tool('run_command', {'command': 'echo A'}, raise_on_error=False),
                                          b.call_tool('run_command', {'command': 'echo B'}, raise_on_error=False))
            print('R1', ra.content[0].text[:60], '||', rb.content[0].text[:60])
        # R2: earlier/concurrent authenticated request + anonymous in-memory call
        server.middleware.remove(rv); rv2 = Rendezvous(2); server.add_middleware(rv2)
        async with http_client(app, tok(sub='alice')) as a, Client(server) as anon:
            ra, rn = await asyncio.gather(a.call_tool('run_command', {'command': 'echo A2'}, raise_on_error=False),
                                          anon.call_tool('run_command', {'command': 'echo ANON'}, raise_on_error=False))
            print('R2', ra.is_error, ra.content[0].text[:50], '||', rn.is_error, rn.content[0].text[:80])
        server.middleware.remove(rv2)
        async with http_client(app, tok(email='al@x.org', preferred_username='bob')) as e:
            r = await e.call_tool('run_command', {'command': 'echo E'}, raise_on_error=False)
            print('R4', r.content[0].text[:60])
        async with http_client(app, tok(sub='', email='', preferred_username='bob')) as e:
            r = await e.call_tool('run_command', {'command': 'echo P'}, raise_on_error=False)
            print('R4b', r.content[0].text[:60])
        async with http_client(app, tok(sub='ghost', email='al@x.org')) as e:
            r = await e.call_tool('run_command', {'command': 'echo G'}, raise_on_error=False)
            print('R5', r.is_error, r.content[0].text[:80])
    print('launches', launches)
contextvars.Context().run(asyncio.run, main())
