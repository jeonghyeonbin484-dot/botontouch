from contextvars import ContextVar
current_data=ContextVar("cloud_data",default=None)
