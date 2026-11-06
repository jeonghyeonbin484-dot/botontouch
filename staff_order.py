"""공식 직급 문자열을 정렬에만 사용하며 화면 직급을 임의 생성하지 않는다."""
import re

def rank(value):
 text=str(value or '')
 match=re.search(r'(?<!\d)([1-9])급',text)
 if match:return int(match[1])
 for word,value in [('서기보',9),('주사보',7),('부이사관',3),('관리관',1),('이사관',2),('서기관',4),('사무관',5),('주사',6),('서기',8)]:
  if word in text:return value
 return 99
