"""운영 DB와 외부 AI를 사용하지 않는 핵심 회귀 검사."""
from pathlib import Path
import sys,unittest,argparse,json,time,importlib,inspect,ast
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT),str(ROOT/'tests')]
for parent in ROOT.parents:
    for name in ('.vendor','.ui-tools'):
        candidate=parent/name
        if candidate.is_dir():sys.path.append(str(candidate))
parser=argparse.ArgumentParser();parser.add_argument('--browser',action='store_true');args=parser.parse_args()
suite=unittest.TestSuite();loader=unittest.TestLoader()
for file in sorted((ROOT/'tests').glob('test_*.py')):
    is_browser='browser' in file.stem
    if is_browser!=args.browser:continue
    tree=ast.parse(file.read_text(encoding='utf-8-sig'))
    if not any(isinstance(n,ast.ClassDef) and any(isinstance(b,ast.Attribute) and b.attr=='TestCase' for b in n.bases) for n in tree.body):continue
    module=importlib.import_module(file.stem)
    for name, cls in inspect.getmembers(module,inspect.isclass):
        if issubclass(cls,unittest.TestCase) and cls.__module__==module.__name__:
            suite.addTests(loader.loadTestsFromTestCase(cls))
start=time.monotonic();result=unittest.TextTestRunner(verbosity=2).run(suite)
folder=ROOT/'artifacts/refactor';folder.mkdir(parents=True,exist_ok=True)
(folder/('browser-results.json' if args.browser else 'server-results.json')).write_text(json.dumps({'tests':result.testsRun,'failures':[(str(t),trace) for t,trace in result.failures],'errors':[(str(t),trace) for t,trace in result.errors],'skipped':[(str(t),why) for t,why in result.skipped],'seconds':round(time.monotonic()-start,2)},ensure_ascii=False,indent=2),encoding='utf-8')
raise SystemExit(not result.wasSuccessful())
