# Planning prototype for restore-test-coverage (2026-10-16), kept as evidence for research/; not a test.
# Run from the worktree root: uv run python spec/restore-test-coverage/research/prototypes/exec_mode_ladder.py [args]
import os, tempfile
import rcac_mcp, rcac_mcp.executor.ssh as sshmod
from rcac_mcp import MCPServerApp
d = tempfile.mkdtemp(); m = os.path.join(d, 'map'); open(m, 'w').write('alice ualice\n')
os.environ['RCAC_USER_MAP'] = m; os.environ.pop('RCAC_SSH_HOST', None)
class FakeConn:
    def __init__(s, host, **kw): s.host = host; s.is_connected = False
    def open(s): s.is_connected = True
    def close(s): s.is_connected = False
sshmod.Connection = FakeConn
seen = []
class Stub:
    def run(self, **kw): seen[-1]['run'] = kw
def stub(auth_mode=None, middlewares=None):
    seen.append({'auth': auth_mode, 'mw': middlewares}); return Stub()
rcac_mcp.create_mcp_server = stub
def desc(mw):
    out = []
    for x in mw:
        ex = getattr(x, '_executor', None)
        out.append((type(x).__name__, type(ex).__name__ if ex else None, getattr(ex, 'hostname', None)))
    return out
for argv, env in [(['-t','stdio','-e','local'], {}), (['-t','stdio','-a','jwt'], {}), (['-t','http','--ssh-host','h1'], {}),
                  (['-t','sse'], {'RCAC_SSH_HOST':'h2'}), (['-t','http'], {}), (['-t','http','-a','jwt'], {}), (['-t','http','-a','oidc','--ssh-host','h3'], {})]:
    seen.clear()
    for k, v in env.items(): os.environ[k] = v
    rc = MCPServerApp.main(argv)
    for k in env: os.environ.pop(k)
    print(argv, env, rc, [desc(s['mw']) for s in seen], [s.get('run') for s in seen])
