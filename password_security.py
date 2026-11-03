"""Argon2id writes, existing PBKDF2 reads and rehash-on-login migration."""
import hashlib
import hmac
import sys
from pathlib import Path
vendor=Path(__file__).with_name('.vendor')
if vendor.is_dir() and str(vendor) not in sys.path:sys.path.insert(0,str(vendor))
from argon2 import PasswordHasher,Type
from argon2.exceptions import VerificationError,InvalidHashError
PH=PasswordHasher(time_cost=3,memory_cost=65536,parallelism=2,type=Type.ID)


def hash_password(password):return PH.hash(password)
def verify(password,stored,salt=''):
    try:
        if stored.startswith('$argon2id$'):return PH.verify(stored,password)
        if len(stored)==64 and salt:return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),600000).hex(),stored)
    except (VerificationError,InvalidHashError,ValueError,TypeError):pass
    return False

def needs_rehash(stored):return not stored.startswith('$argon2id$') or PH.check_needs_rehash(stored)
def validate(password):
    if not isinstance(password,str) or not 12<=len(password)<=200 or not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password) or not any(not c.isalnum() for c in password):raise ValueError('새 비밀번호는 문자·숫자·기호를 포함하여 12~200자로 입력하세요.')
