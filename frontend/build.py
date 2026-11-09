"""기능별 소스를 기존 실행 순서로 결합하여 공개 HTML 진입점을 생성한다."""
import json
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parent

def read_source(relative_path, encoding='utf-8-sig'):
    source_path = (WEB_ROOT / relative_path).resolve()
    if not source_path.is_relative_to(WEB_ROOT):
        raise ValueError('화면 소스 경로가 올바르지 않습니다.')
    return source_path.read_text(encoding=encoding)

def build_page(page, output_name, style_marker, script_marker):
    template = read_source(page['template'])
    styles = '\n'.join(read_source(path) for path in page['styles'])
    scripts = ''.join(read_source(path, 'utf-8') for path in page.get('bootstrap', []))
    for path in page['scripts']:
        if scripts:
            scripts += '\n'
        scripts += read_source(path)
    assert '</script' not in scripts.lower()
    assert template.count(style_marker) == template.count(script_marker) == 1
    output = template.replace(style_marker, styles).replace(script_marker, scripts)
    (WEB_ROOT / output_name).write_text(output, encoding='utf-8')
    print('Built frontend/' + output_name)

def main():
    manifest = json.loads(read_source('bundle-manifest.json'))
    build_page(manifest['application'], 'index.html', '/* APP_STYLE */', '/* APP_SCRIPT */')
    build_page(manifest['login'], 'login.html', '/* LOGIN_STYLE */', '/* LOGIN_SCRIPT */')

if __name__ == '__main__':
    main()
