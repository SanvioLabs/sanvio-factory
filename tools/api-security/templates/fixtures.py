"""Hooks for the generated authorization tests (SPEC-034, api_security.authz).

Run with:  pytest -p security.api_security.authz security/fixtures.py

Fill in each hook for this project. Until you do, every hook raises, and the generated tests fail:
a project cannot pass the enforced check by leaving this file as it came.
Never put a real credential here. Mint test tokens the way the project's own tests do.
"""
# The plugin imports security/config.json's roles_module and handler_modules itself, so every
# declared route gets its cases. Import here only what invoke() needs, such as the router:
# from app.handlers import router


def token_for(role):
    """A credential that holds `role`."""
    raise NotImplementedError("token_for: return a test credential holding the role")


def token_without(roles):
    """A valid credential that holds none of `roles` (another role, or a signed-in user with none)."""
    raise NotImplementedError("token_without: return a valid credential holding none of the roles")


def owner_params(role, param):
    """(credential holding `role`, a value of `param` it owns, a value it does not own)."""
    raise NotImplementedError("owner_params: return (credential, owned value, someone else's value)")


def invoke(method, path, token, path_params):
    """Call the route the way production does and return the HTTP status code.

    With the library's Router:
        headers = {"authorization": "Bearer " + token} if token else {}
        event = {"routeKey": f"{method} {path}", "headers": headers, "pathParameters": path_params}
        return router.handle(event, None)["statusCode"]
    """
    raise NotImplementedError("invoke: call the route and return its status code")
