"""이전 경로 호환용. 구현: batontouch.server.application."""
from batontouch.compat import install_legacy_alias
if __name__ == '__main__':
    from batontouch.server.application import start_local_server
    start_local_server()
else:
    install_legacy_alias(__name__, 'batontouch.server.application')
