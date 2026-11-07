import json

from flask import request


def interpret(event, identity):
    body = json.loads(event["body"])
    # ruleid: api-security.identity-from-request.python
    user = body["user_id"]
    # ruleid: api-security.identity-from-request.python
    device = body.get("device_id")
    qs = event.get("queryStringParameters") or {}
    # ruleid: api-security.identity-from-request.python
    owner = qs.get("userId")
    # ok: api-security.identity-from-request.python
    text = body["text"]
    # ok: api-security.identity-from-request.python
    me = identity["user_id"]
    # ok: api-security.identity-from-request.python
    target = event["pathParameters"]["user_id"]
    return user, device, owner, text, me, target


def flask_view():
    # ruleid: api-security.identity-from-request.python
    uid = request.json["user_id"]
    # ruleid: api-security.identity-from-request.python
    acct = request.args.get("account_id")
    # The marker with a reason is accepted, read by the check rather than Semgrep.
    # ok: api-security.identity-from-request.python
    sender = request.json["user_id"]  # nosemgrep: api-security.identity-from-request.python -- echoed back to the caller only, never trusted
    return uid, acct, sender
