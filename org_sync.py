def department_tree(db):
    rows=[dict(r) for r in db.execute('SELECT * FROM org_departments WHERE active=1')]
    byid={r['id']:r for r in rows};children={}
    for row in rows:children.setdefault(row['parent_id'] if row['parent_id'] in byid else '',[]).append(row)
    def order(row):
        try:return (0,float(row['sort_order']),row['name'],row['id'])
        except (ValueError,TypeError):return (1,0,row['name'],row['id'])
    result=[];seen=set()
    def visit(row,path,depth):
        if row['id'] in seen:return
        seen.add(row['id']);item=dict(row);item.update(depth=depth,path=' / '.join(path+[row['name']]),parent_missing=bool(row['parent_id'] and row['parent_id'] not in byid));
        if not row.get('hidden_from_picker'):result.append(item)
        for child in sorted(children.get(row['id'],[]),key=order):visit(child,path+[row['name']],depth+1)
    for row in sorted(children.get('',[]),key=order):visit(row,[],0)
    for row in rows:
        if row['id'] not in seen:visit(row,[],0)
    return result

def live_lookup(*args,**kwargs):
 raise ValueError('공개 테스트에서는 내부 조직도에 접속하지 않습니다. 가상 직원 목록을 사용하세요.')
def start(*args,**kwargs):
 raise ValueError('공개 테스트에서는 실제 조직도 동기화를 차단합니다.')
def latest(*args,**kwargs):
 return {'state':'disabled','report':{},'notice':'가상 부서·직원만 제공하는 테스트 사이트입니다.'}
