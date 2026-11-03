"""Public demo: no internal endpoints or authentication materials."""
class DirectoryError(ValueError):pass
def settings():return {'enabled':False,'approved':False}
def fetch_employees(*args,**kwargs):raise DirectoryError('공개 테스트에서는 내부 조직도 연동을 제공하지 않습니다.')
