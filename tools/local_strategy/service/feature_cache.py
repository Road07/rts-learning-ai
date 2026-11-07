"""Request-local immutable feature reuse. No state shared between bots/frames."""
from contextvars import ContextVar

_scope=ContextVar('inference_feature_cache',default=None)

def begin(enabled):return _scope.set({} if enabled else None)
def end(token):_scope.reset(token)

def cached(name,observation,compute):
    scope=_scope.get()
    if scope is None:return compute()
    key=(name,id(observation))
    if key not in scope:scope[key]=(observation,tuple(compute()))
    # Callers extend lists. Never return the cached backing object.
    return list(scope[key][1])
