"""신규 계정 발급은 가상 공유 저장소에서만 검증한다."""
import json, sqlite3, unittest, urllib.error
from test_cloud import Fixture, PASSWORD

class AdminAccountCreationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture().start()
    def tearDown(self):
        self.fixture.stop()
    def reject(self, body, client=None, status=403):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.fixture.call('/api/auth/users/create', body, client)
        self.assertEqual(caught.exception.code, status)
    def test_create_change_password_and_login_without_exposing_secret(self):
        f=self.fixture; admin=f.login('demo.admin')
        result=f.call('/api/auth/users/create', {'username':'Judge.New','password':PASSWORD}, admin)
        self.assertEqual(result['username'],'judge.new')
        self.assertTrue(result['must_change_password'])
        self.assertFalse(result['employee_linked'])
        self.assertNotIn(PASSWORD,json.dumps(result))
        db=sqlite3.connect(':memory:');db.deserialize(f.memory.payload)
        row=db.execute('SELECT password_hash,role FROM users WHERE id=?',(result['id'],)).fetchone()
        self.assertTrue(row[0].startswith('$argon2id$'));self.assertEqual(row[1],'member')
        self.assertNotIn(PASSWORD,str(db.execute('SELECT details FROM auth_audit').fetchall()));db.close()
        self.reject({'username':'JUDGE.NEW','password':PASSWORD},admin,409)
        user=f.client();login=f.call('/api/auth/login',{'username':'JUDGE.NEW','password':PASSWORD},user)
        self.assertTrue(login['user']['must_change_password'])
        with self.assertRaises(urllib.error.HTTPError) as blocked:f.call('/api/workspaces',client=user)
        self.assertEqual(blocked.exception.code,403)
        new='Fictional-Changed-Password-2026!'
        f.call('/api/auth/password',{'current_password':PASSWORD,'new_password':new,'confirmation':new},user)
        f.call('/api/auth/logout',{},user)
        user=f.client();login=f.call('/api/auth/login',{'username':'judge.new','password':new},user)
        self.assertFalse(login['user']['must_change_password'])
        self.assertEqual(login['user']['role'],'member')
        self.assertEqual(f.call('/api/workspaces',client=user),[])
        with self.assertRaises(urllib.error.HTTPError) as old:f.call('/api/auth/login',{'username':'judge.new','password':PASSWORD})
        self.assertEqual(old.exception.code,401)
    def test_admin_only_and_invalid_requests_never_create_account(self):
        f=self.fixture;admin=f.login('demo.admin');member=f.login('demo.a')
        body={'username':'judge.denied','password':PASSWORD}
        self.reject(body,None,401);self.reject(body,member,403)
        self.reject({**body,'password':'1234!'},admin,400)
        self.reject({**body,'role':'admin'},admin,403)
        self.assertNotIn('judge.denied',[u['username'] for u in f.call('/api/auth/users',client=admin)])

    def test_matching_directory_identity_is_linked_and_inactive_staff_rejected(self):
        f=self.fixture;admin=f.login('demo.admin')
        db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row;db.deserialize(f.memory.payload)
        template=dict(db.execute("SELECT * FROM org_employees WHERE employee_id='DEMO-B'").fetchone())
        for identity,username,active in [('LOCAL-LINKED','judge.linked',1),('LOCAL-INACTIVE','judge.inactive',0)]:
            staff={**template,'employee_id':identity,'saeoll_id':username,'active':active}
            keys=list(staff)
            db.execute('INSERT INTO org_employees('+','.join(keys)+') VALUES('+','.join('?' for _ in keys)+')',[staff[k] for k in keys])
        db.commit()
        with f.memory.lock:f.memory.payload=db.serialize();f.memory.version+=1
        db.close()
        result=f.call('/api/auth/users/create',{'username':'JUDGE.LINKED','password':PASSWORD},admin)
        self.assertTrue(result['employee_linked'])
        user=next(u for u in f.call('/api/auth/users',client=admin) if u['id']==result['id'])
        self.assertEqual(user['employee']['employee_id'],'LOCAL-LINKED')
        self.reject({'username':'judge.inactive','password':PASSWORD},admin,409)
