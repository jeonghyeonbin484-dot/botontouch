import os
def enabled(db=None):return False


def shared_initial_allowed(db):
 if os.environ.get('BATON_STAFF_SHARED_INITIAL_ALLOWED','false')=='true':return True
 return enabled(db)

