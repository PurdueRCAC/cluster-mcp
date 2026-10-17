import os, socket, threading, tempfile
import paramiko
os.environ['HOME'] = tempfile.mkdtemp(); os.environ.pop('SSH_AUTH_SOCK', None)
host_key = paramiko.Ed25519Key.generate() if hasattr(paramiko.Ed25519Key, 'generate') else None
if host_key is None:
    host_key = paramiko.RSAKey.generate(2048)
client_key = paramiko.RSAKey.generate(2048)
class Srv(paramiko.ServerInterface):
    def check_auth_publickey(self, username, key):
        return paramiko.AUTH_SUCCESSFUL if key.get_base64() == client_key.get_base64() else paramiko.AUTH_FAILED
    def check_channel_env_request(self, channel, name, value): return True
    def get_allowed_auths(self, username): return 'publickey'
    def check_channel_request(self, kind, chanid): return paramiko.OPEN_SUCCEEDED
    def check_channel_exec_request(self, channel, command):
        def reply():
            import time; time.sleep(0.2)
            channel.sendall(b'smoke:' + command); channel.send_exit_status(3); channel.close()
        threading.Thread(target=reply, daemon=True).start(); return True
sock = socket.socket(); sock.bind(('127.0.0.1', 0)); sock.listen(1); port = sock.getsockname()[1]
def serve():
    conn, _ = sock.accept(); t = paramiko.Transport(conn); t.add_server_key(host_key); t.start_server(server=Srv())
    while t.is_active(): t.join(0.1)
threading.Thread(target=serve, daemon=True).start()
from rcac_mcp.executor.ssh import SSHExecutor
ex = SSHExecutor('127.0.0.1', port=port, user='smoke', connect_kwargs={'pkey': client_key, 'look_for_keys': False, 'allow_agent': False})
r = ex.run('echo hi'); print(repr(r)); ex.close()
