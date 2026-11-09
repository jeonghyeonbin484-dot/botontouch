"""이전 import 경로를 동일한 모듈 객체로 연결한다. 상태를 복제하지 않는다."""
from importlib import import_module
import sys

def install_legacy_alias(legacy_name, implementation_name):
    implementation = import_module(implementation_name)
    sys.modules[legacy_name] = implementation
    return implementation
