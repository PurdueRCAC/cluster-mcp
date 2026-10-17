# Planning prototype for restore-test-coverage (2026-10-16), kept as evidence for research/; not a test.
# Run from the worktree root: uv run python spec/restore-test-coverage/research/prototypes/tokens_over_http.py [args]
import asyncio, contextvars, os, sys, tempfile, subprocess, datetime as dt
import httpx, jwt
S = 'k' * 32
os.environ['JWT_SECRET'] = S
d = tempfile.mkdtemp(); m = os.path.join(d, 'map'); open(m, 'w').write('alice ualice\n')
from rcac_mcp.server import create_mcp_server
from rcac_mcp.middleware import AuthExecutorMiddleware
from rcac_mcp.auth import create_jwt_auth
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
import rcac_mcp.executor.delegate as dm
ran = []
class P:
    def __init__(s, a, **k): ran.append(a); s.args = a; s.returncode = 0
    def __enter__(s): return s
    def __exit__(s, *a): pass
    def communicate(s, input=None, timeout=None): return ('ok', '')
    def poll(s): return 0
subprocess.Popen = P
for v in (None, '', 'k'*31, 'k'*32):
    if v is None: os.environ.pop('JWT_SECRET', None)
    else: os.environ['JWT_SECRET'] = v
    try: create_jwt_auth(); print(repr(v and len(v)), 'accepted')
    except ValueError as e: print(repr(v and len(v)), 'refused', e)
os.environ['JWT_SECRET'] = S
cli = subprocess.run  # not used
def mint(iss='rcac-mcp', aud='rcac-mcp', key=S, alg='HS256', exp=300, sub='alice'):
    now = dt.datetime.now(dt.timezone.utc)
    return jwt.encode({'iss': iss, 'aud': aud, 'iat': now, 'exp': now + dt.timedelta(seconds=exp), 'sub': sub}, key, algorithm=alg)
def client(app, t):
    f = lambda headers=None, auth=None, **kw: httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t', headers=headers, auth=auth)
    return Client(StreamableHttpTransport('http://t/mcp', auth=t, httpx_client_factory=f))
cli_tok = sys.argv[1]
async def main():
    server = create_mcp_server('jwt', middlewares=[AuthExecutorMiddleware('jwt', m)])
    app = server.http_app()
    async with app.router.lifespan_context(app):
        for name, t in [('ok', mint()), ('cli', cli_tok), ('iss', mint(iss='x')), ('aud', mint(aud='x')), ('key', mint(key='z'*32)), ('alg', mint(alg='HS512')), ('exp', mint(exp=-60))]:
            try:
                async with client(app, t) as c:
                    r = await c.call_tool('run_command', {'command': 'true'}, raise_on_error=False)
                    print(name, 'accepted', r.is_error)
            except httpx.HTTPStatusError as e:
                print(name, 'rejected', e.response.status_code)
contextvars.Context().run(asyncio.run, main())
print(len(ran), [a[4] for a in ran])
