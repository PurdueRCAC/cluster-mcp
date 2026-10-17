# Planning prototype for restore-test-coverage (2026-10-16), kept as evidence for research/; not a test.
# Run from the worktree root: uv run python spec/restore-test-coverage/research/prototypes/unit_guard.py [args]
import socket, os, subprocess, sys
refused = []
def refuse(name):
    def f(*a, **k):
        refused.append((name, a[:2])); raise OSError(f'guard: {name} refused')
    return f
socket.socket.connect = refuse('connect'); socket.socket.connect_ex = refuse('connect_ex')
socket.create_connection = refuse('create_connection'); socket.getaddrinfo = refuse('getaddrinfo')
os.system = refuse('os.system'); os.posix_spawn = refuse('posix_spawn'); os.posix_spawnp = refuse('posix_spawnp')
sys.argv = [sys.argv[0], 'clean']
exec(open(sys.argv[0].replace('unit_guard', 'isolation_over_http')).read())
print('refused', refused)
# SSH executor attempt under guard
from rcac_mcp.executor.ssh import SSHExecutor
try:
    SSHExecutor('cluster.example.org')
except Exception as e:
    print('ssh', type(e).__name__, str(e)[:80])
print('refused', refused)
