"""Generated authorization tests, SPEC-034 REQ-014. A pytest plugin (pytest 7 or later):

    pytest -p security.api_security.authz security/fixtures.py

`security/fixtures.py` imports the project's roles and handlers, then defines four hooks:

    token_for(role) -> credential that holds `role`
    token_without(roles) -> a valid credential holding none of `roles`
    owner_params(role, param) -> (credential, a value it owns, a value it does not)
    invoke(method, path, token, path_params) -> HTTP status code

For every route declared with role(...), the plugin generates: no credential gets 401; a
credential without the role gets 403; and under owns, another user's resource gets 403 while the
caller's own is allowed. Public routes get no refusal cases. A missing hook is a collection error,
so a project cannot pass by leaving the fixtures out.
"""
import importlib.util
import re
from typing import Iterator

import pytest

from . import registry

HOOKS = ("token_for", "token_without", "owner_params", "invoke")
PARAM = re.compile(r"\{([^}+]+)\+?\}")


def _load(path):
    spec = importlib.util.spec_from_file_location("api_security_project_fixtures", str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    missing = [h for h in HOOKS if not callable(getattr(module, h, None))]
    if missing:
        raise pytest.UsageError(f"{path} is missing the hook(s) {', '.join(missing)}; see api_security.authz")
    return module


class AuthzCase(pytest.Item):
    def __init__(self, *, check, **kwargs):
        super().__init__(**kwargs)
        self.check = check

    def runtest(self):
        self.check()

    def reportinfo(self):
        return self.path, None, self.name


class AuthzFile(pytest.File):
    def collect(self) -> Iterator[AuthzCase]:
        hooks = _load(self.path)
        for route in registry.routes():
            if route.policy is None or route.policy.kind != "role":
                continue
            yield from self._cases(hooks, route)

    def _cases(self, hooks, route):
        m, p, policy = route.method, route.path, route.policy
        base = {name: "sample" for name in PARAM.findall(p)}

        def expect(params, token, want, label):
            def check():
                got = hooks.invoke(m, p, token, dict(params))
                if callable(want):
                    assert want(got), f"{m} {p} {label}: got {got}"
                else:
                    assert got == want, f"{m} {p} {label}: expected {want}, got {got}"
            return check

        yield AuthzCase.from_parent(self, name=f"{m} {p} no-token 401", check=expect(base, None, 401, "no-token"))
        yield AuthzCase.from_parent(self, name=f"{m} {p} without-role 403",
                                    check=expect(base, hooks.token_without(policy.roles), 403, "without-role"))
        def allowed(status):
            return status not in (401, 403)

        if policy.owns:
            token, mine, other = hooks.owner_params(policy.roles[0], policy.owns)
            yield AuthzCase.from_parent(self, name=f"{m} {p} not-owner 403",
                                        check=expect({**base, policy.owns: other}, token, 403, "not-owner"))
            yield AuthzCase.from_parent(self, name=f"{m} {p} owner allowed",
                                        check=expect({**base, policy.owns: mine}, token, allowed, "owner"))
        else:
            yield AuthzCase.from_parent(self, name=f"{m} {p} with-role allowed",
                                        check=expect(base, hooks.token_for(policy.roles[0]), allowed, "with-role"))


def pytest_collect_file(file_path, parent):
    if file_path.name == "fixtures.py" and file_path.parent.name == "security":
        return AuthzFile.from_parent(parent, path=file_path)
    return None
