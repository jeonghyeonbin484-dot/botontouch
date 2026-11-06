"""Approved organization lookup adapter. Disabled unless explicitly configured.
No cookies, SSO scraping, unconfirmed department endpoint or external AI calls.
"""
import json
import os
import re
import urllib.request
import urllib.parse
import urllib.error
import socket
from pathlib import Path


class DirectoryError(ValueError):
    pass


def settings():
    if os.environ.get('BATON_ORG_TRANSPORT')=='direct':
        base=os.environ.get('BATON_ORG_BASE_URL','').rstrip('/')
        return {'enabled':os.environ.get('BATON_ORG_DIRECT_ENABLED')=='true','approved':os.environ.get('BATON_ORG_API_APPROVED')=='true','url':base+'/swcm/module/orgchartview/selectOrgChartUserListJson.do','department_url':base+'/swcm/module/orgchartview/selectOrgChartDeptListJson.do','method':'POST','response_list_key':'userList','employee_id_field':os.environ.get('BATON_ORG_EMPLOYEE_ID_FIELD','USER_SID'),'authorization_env':'BATON_ORG_AUTHORIZATION' if os.environ.get('BATON_ORG_AUTHORIZATION') else '', 'excluded_department_roots':['64100000001']}
    file = Path(__file__).with_name('organization.local.json')
    if not file.exists():
        return {'enabled': False}
    try:
        value = json.loads(file.read_text(encoding='utf-8-sig'))
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, OSError):
        raise DirectoryError('조직도 설정 파일 형식을 확인하세요.') from None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise DirectoryError('조직도 주소 변경 응답을 차단했습니다. 승인된 주소를 확인하세요.')


def fetch_employees(department_id, department_name=None, config=None, diagnostics=None):
    config = settings() if config is None else config
    if config.get('enabled') is not True or config.get('approved') is not True:
        raise DirectoryError('조직도 실시간 연계가 비활성화되어 있습니다. 관리자가 등록한 직원정보를 사용할 수 있습니다.')
    method = config.get('method')
    if method not in ('GET', 'POST'):
        raise DirectoryError('공식 연계의 HTTP 요청 방식(GET 또는 POST)을 확인해 설정하세요.')
    url = config.get('url', '')
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise DirectoryError('승인된 조직도 API 주소 설정을 확인하세요.')
    if parsed.path != '/swcm/module/orgchartview/selectOrgChartUserListJson.do':
        raise DirectoryError('확인된 직원 목록 조회 경로만 지원합니다.')
    if not re.fullmatch(r'[a-zA-Z0-9_.-]{1,100}', department_id):
        raise DirectoryError('부서 식별값 형식이 올바르지 않습니다.')
    body = urllib.parse.urlencode({'pid': 'OCP03', 'dept_id': department_id, 'keyword2': '', 's_field': ''}).encode()
    headers = {'Accept': 'application/json', 'Content-Type': 'application/x-www-form-urlencoded'}
    env_name = config.get('authorization_env', '')
    if env_name:
        if not isinstance(env_name, str) or not re.fullmatch('[A-Z][A-Z0-9_]{0,79}', env_name):
            raise DirectoryError('인증 환경변수 이름 설정을 확인하세요.')
        authorization = os.environ.get(env_name, '')
        if not authorization or '\r' in authorization or '\n' in authorization:
            raise DirectoryError('공식 연계용 인증 환경변수가 설정되지 않았습니다.')
        headers['Authorization'] = authorization
    request = urllib.request.Request(url + ('?' + body.decode() if method == 'GET' else ''), data=body if method == 'POST' else None, headers=headers, method=method)
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=8) as response:
            if diagnostics is not None:diagnostics['http_status']=response.status
            raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise DirectoryError('조직도 응답 크기 제한을 초과했습니다.')
            value = json.loads(raw.decode('utf-8-sig'))
    except DirectoryError:
        raise
    except urllib.error.HTTPError as error:
        raise DirectoryError('조직도 HTTP '+str(error.code)+' 응답입니다. 인증·연계 권한과 공식 요청 방식을 확인하세요. 기존 등록정보는 유지됩니다.') from None
    except (TimeoutError, socket.timeout):
        raise DirectoryError('조직도 연결 제한시간(8초)을 초과했습니다. 내부망 연결을 확인하세요.') from None
    except urllib.error.URLError:
        raise DirectoryError('조직도 서버 연결에 실패했습니다. 내부망·프록시·인증서 설정을 담당자에게 확인하세요.') from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise DirectoryError('조직도 응답이 정상 JSON이 아닙니다. 공식 응답 형식을 확인하세요.') from None
    except Exception:
        raise DirectoryError('조직도 조회에 실패했습니다. 인증·접근권한·네트워크·응답 형식을 확인하세요. 기존 등록 직원정보는 유지됩니다.') from None
    if isinstance(value,dict) and 'success' in value and value['success'] is not True:
        raise DirectoryError('조직도 API가 success=false를 반환했습니다. 연계 권한과 요청 조건을 확인하세요.')
    key = config.get('response_list_key', '')
    if isinstance(value, dict) and isinstance(key, str) and key:
        value = value.get(key)
    if not isinstance(value, list) or len(value) > 10000:
        raise DirectoryError('직원 배열 응답이 아닙니다. 공식 응답에서 직원 목록 키를 확인해 response_list_key를 설정하세요.')
    if diagnostics is not None:
        diagnostics['raw_employee_count']=len(value)
        diagnostics['missing_login_count']=sum(isinstance(r,dict) and (r.get('SAEOLL_ID') is None or r.get('SAEOLL_ID')=='') for r in value)
        diagnostics['invalid_login_count']=sum(isinstance(r,dict) and not (isinstance(r.get('SAEOLL_ID'),str) and re.fullmatch(r'[a-zA-Z0-9가-힣_.@-]{2,80}',r['SAEOLL_ID'].strip())) for r in value)
    result, seen, logins = [], set(), set()
    for row in value:
        if not isinstance(row, dict):
            raise DirectoryError('조직도 직원 응답 형식이 올바르지 않습니다.')
        saeoll=row.get('SAEOLL_ID')
        if saeoll is None or isinstance(saeoll,str) and not saeoll.strip():
            saeoll=None  # Missing login is not a missing staff identity. Never substitute USER_ID.
        else:
            if not isinstance(saeoll,str) or not re.fullmatch(r'[a-zA-Z0-9가-힣_.@-]{2,80}',saeoll.strip()):raise DirectoryError('직원 SAEOLL_ID 형식이 올바르지 않습니다. 관리자 확인이 필요합니다.')
            saeoll=saeoll.strip().lower()
            if saeoll in logins:raise DirectoryError('조직도에 중복 SAEOLL_ID가 있습니다. 관리자 확인이 필요합니다.')
            logins.add(saeoll)
        identity_field=config.get('employee_id_field','USER_ID')
        if identity_field not in ('USER_ID','USER_SID'):raise DirectoryError('직원 식별 필드 설정을 확인하세요.')
        fields = {k: row.get(k, '') for k in ('USER_ID', 'USER_NM', 'DEPT_NM', 'POS_NM')}
        fields['USER_ID']=row.get(identity_field,'')
        grade=row.get('CLSS_NM','')
        if not isinstance(grade,str) or len(grade)>200:raise DirectoryError('직급 응답 형식이 올바르지 않습니다.')
        if config.get('response_list_key')=='userList' and row.get('DEPT_ID')!=department_id:raise DirectoryError('요청한 부서 코드와 응답 DEPT_ID가 다릅니다.')
        if not fields['DEPT_NM'] or not isinstance(fields['DEPT_NM'],str):raise DirectoryError('응답 부서명이 없습니다.')
        if any(not isinstance(v, str) or len(v) > 200 for v in fields.values()) or not fields['USER_ID'].strip() or not fields['USER_NM'].strip():
            raise DirectoryError('직원 식별값·성명 응답이 누락되었거나 올바르지 않습니다.')
        if fields['USER_ID'] in seen or (department_name is not None and fields['DEPT_NM'].strip() != department_name):
            raise DirectoryError('중복 직원 식별값 또는 선택 부서와 다른 응답입니다. 부서 등록명과 공식 응답을 확인하세요.')
        seen.add(fields['USER_ID'])
        # EMAIL/TELNO are intentionally not retained or exposed: selection needs neither.
        mapped_status=None
        status_field=config.get('employment_status_field','')
        status_map=config.get('employment_status_map',{})
        if status_field:
            if not isinstance(status_field,str) or not isinstance(status_map,dict):raise DirectoryError('재직 상태 매핑 설정을 확인하세요.')
            mapped_status=status_map.get(str(row.get(status_field,'')))
            if mapped_status not in (None,'active','inactive','retired','transferred'):raise DirectoryError('재직 상태 매핑 값이 올바르지 않습니다.')
        result.append({'employee_id': fields['USER_ID'].strip(), 'name': fields['USER_NM'].strip(), 'position': ' · '.join(dict.fromkeys(x for x in (grade.strip(),fields['POS_NM'].strip()) if x)), 'department_name':fields['DEPT_NM'].strip(), 'department_id': department_id, 'saeoll_id':saeoll})
        if mapped_status is not None:result[-1]['employment_status']=mapped_status
    return result


def fetch_departments(config=None):
    config=settings() if config is None else config
    if config.get('enabled') is not True or config.get('approved') is not True:raise DirectoryError('조직도 연계가 비활성화되어 있습니다.')
    source=urllib.parse.urlsplit(config.get('url',''))
    if source.scheme not in ('http','https') or not source.hostname or source.username or source.password:raise DirectoryError('조직도 주소를 확인하세요.')
    url=urllib.parse.urlunsplit((source.scheme,source.netloc,'/swcm/module/orgchartview/selectOrgChartDeptListJson.do','',''))
    headers={'Accept':'application/json','Content-Type':'application/x-www-form-urlencoded'}
    env=config.get('authorization_env','')
    if env:
        if not re.fullmatch('[A-Z][A-Z0-9_]{0,79}',env):raise DirectoryError('인증 환경변수 이름을 확인하세요.')
        token=os.environ.get(env,'')
        if not token or '\r' in token or '\n' in token:raise DirectoryError('공식 인증정보가 없습니다.')
        headers['Authorization']=token
    request=urllib.request.Request(url,data=b'pid=OCP03',headers=headers,method='POST')
    try:
        with urllib.request.build_opener(NoRedirect()).open(request,timeout=8) as response:
            raw=response.read(4*1024*1024+1)
            if len(raw)>4*1024*1024:raise DirectoryError('부서 응답 크기 제한을 초과했습니다.')
            value=json.loads(raw.decode('utf-8-sig'))
    except DirectoryError:raise
    except urllib.error.HTTPError as error:raise DirectoryError('부서 API HTTP '+str(error.code)+' 응답입니다.') from None
    except (TimeoutError,socket.timeout):raise DirectoryError('부서 API 제한시간(8초)을 초과했습니다.') from None
    except urllib.error.URLError:raise DirectoryError('부서 API 네트워크 연결에 실패했습니다.') from None
    except (ValueError,UnicodeError):raise DirectoryError('부서 API 응답이 정상 JSON이 아닙니다.') from None
    if not isinstance(value,dict) or value.get('success') is not True or not isinstance(value.get('deptList'),list):raise DirectoryError('부서 API success 또는 deptList 응답을 확인하세요.')
    if not value['deptList'] or len(value['deptList'])>10000:raise DirectoryError('부서 목록이 비었거나 제한을 초과했습니다.')
    result={}
    for row in value['deptList']:
        if not isinstance(row,dict):raise DirectoryError('부서 항목 형식이 올바르지 않습니다.')
        key,name,parent=row.get('DEPT_ID'),row.get('DEPT_NM'),row.get('PARENT_DEPT_ID')
        if not isinstance(key,str) or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,100}',key) or not isinstance(name,str) or not name.strip() or len(name)>200:raise DirectoryError('부서 코드·부서명 형식이 올바르지 않습니다.')
        if parent is None:parent=''
        if not isinstance(parent,str) or len(parent)>100:raise DirectoryError('상위 부서 코드 형식이 올바르지 않습니다.')
        item={'id':key,'name':name.strip(),'parent_id':parent,'sort_order':str(row.get('SORTORDER',''))[:100],'mode':str(row.get('D_MODE',''))[:100],'team_flag':str(row.get('TEAM_YN',''))[:100]}
        if key in result and result[key]!=item:raise DirectoryError('부서 코드 중복 충돌입니다.')
        result[key]=item
    for key in result:
        visited=set();current=key
        while current in result:
            if current in visited:raise DirectoryError('부서 계층에 순환 관계가 있습니다.')
            visited.add(current);current=result[current]['parent_id']
    return list(result.values())
