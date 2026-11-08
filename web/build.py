"""Bundle local UI sources into the single HTML served by the existing backend."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
shell = (ROOT / 'shell.html').read_text(encoding='utf-8')
css = (ROOT / 'ui.css').read_text(encoding='utf-8')
js = (ROOT / 'ui.js').read_text(encoding='utf-8')
js += '\n' + (ROOT / 'workflow.js').read_text(encoding='utf-8')
js += '\n' + (ROOT / 'requests.js').read_text(encoding='utf-8')
js += '\n' + (ROOT / 'accounts.js').read_text(encoding='utf-8-sig')
js += '\n' + (ROOT / 'journey.js').read_text(encoding='utf-8-sig')
js += '\n' + (ROOT / 'evidence.js').read_text(encoding='utf-8-sig')
js += '\n' + (ROOT / 'document-view.js').read_text(encoding='utf-8-sig')
js += '\n' + (ROOT / 'journey-ux.js').read_text(encoding='utf-8-sig')
js += '\n' + (ROOT / 'chat.js').read_text(encoding='utf-8-sig')
js += '\n' + (ROOT / 'report-preview.js').read_text(encoding='utf-8-sig')
js += '\n' + (ROOT / 'user-menu.js').read_text(encoding='utf-8-sig')
js += '\n' + (ROOT / 'chat-notifications.js').read_text(encoding='utf-8-sig')
js += '\n' + (ROOT / 'video-guide-config.js').read_text(encoding='utf-8')
js += '\n' + (ROOT / 'video-guide.js').read_text(encoding='utf-8')
js += '\n' + (ROOT / 'ai-studio.js').read_text(encoding='utf-8-sig')
js += '\n' + (ROOT / 'resource-library.js').read_text(encoding='utf-8-sig')
js += '\n' + (ROOT / 'studio-document-preview.js').read_text(encoding='utf-8-sig')
js += '\n' + (ROOT / 'user-manual.js').read_text(encoding='utf-8-sig')
assert '</script' not in js.lower()
assert shell.count('/* APP_STYLE */') == shell.count('/* APP_SCRIPT */') == 1
output = shell.replace('/* APP_STYLE */', css).replace('/* APP_SCRIPT */', js)
(ROOT / 'index.html').write_text(output, encoding='utf-8')
print('Built web/index.html (self-contained UI)')

login=(ROOT / "login-shell.html").read_text(encoding="utf-8-sig")
login=login.replace("/* LOGIN_STYLE */",(ROOT / "login.css").read_text(encoding="utf-8-sig")).replace("/* LOGIN_SCRIPT */",(ROOT / "login.js").read_text(encoding="utf-8-sig"))
(ROOT / "login.html").write_text(login,encoding="utf-8")
print("Built web/login.html")
