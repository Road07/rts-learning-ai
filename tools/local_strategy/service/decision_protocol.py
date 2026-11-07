"""Lossless legacy/compact/same-frame batch envelopes. Preserve caller order."""

def decode(body,model):
    if not isinstance(body,dict) or body.get('model')!=model:raise ValueError('Unexpected model')
    batch='requests' in body
    if batch:
        requests=body['requests']
        if not isinstance(requests,list) or not 1<=len(requests)<=8:raise ValueError('Invalid batch size')
    elif 'request' in body:requests=[body['request']]
    else:
        import json
        message=next(m for m in reversed(body['messages']) if m['role']=='user')
        requests=[json.loads(message['content'])]
    for request in requests:
        if not isinstance(request,dict):raise ValueError('Invalid request')
        obs=request.get('observation');candidates=request.get('candidates')
        if not isinstance(obs,dict) or not isinstance(candidates,list) or not 1<=len(candidates)<=64:raise ValueError('Invalid state/candidates')
        if any(not isinstance(c,dict) or not isinstance(c.get('id'),str) or not isinstance(c.get('description',''),str) for c in candidates):raise ValueError('Invalid candidate')
    if batch:
        # Never silently combine different times, matches, or two updates of one bot.
        keys=[(r['observation'].get('match_id'),r['observation'].get('decision_frame')) for r in requests]
        players=[r['observation'].get('player_index') for r in requests]
        if any(k!=keys[0] for k in keys) or any(v is None for v in keys[0]) or any(v is None for v in players) or len(set(players))!=len(players):raise ValueError('Batch requires distinct players at one match/frame')
    return requests,batch
