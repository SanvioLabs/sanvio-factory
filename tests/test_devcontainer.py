"""The dev container in .devcontainer/: pinned, non-root, and given nothing from the host but the workspace.

Run with: python3 -m unittest tests.test_devcontainer

Each check is a function that returns a list of problems, so the tests below run it on the real files
and on inputs it has to reject. devcontainer.json is read with json.loads, so a comment in it fails too.
"""
import copy
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / ".devcontainer"

# Folders that hold credentials, from .claude/hooks/guard.py and the deny list in .claude/settings.json,
# plus the two sign-ins the container keeps in its own volumes. None may come from the host.
FORBIDDEN = (".ssh", ".aws", ".gnupg", ".kube", ".docker", ".netrc", ".npmrc", ".pypirc", ".config/gh", ".claude")
# Of those, the only two a volume may be mounted at, under the remote user's home folder.
SIGN_INS = (".claude", ".config/gh")
CLAUDE_FEATURE = "ghcr.io/anthropics/devcontainer-features/claude-code"
GH_FEATURE = "ghcr.io/devcontainers/features/github-cli"
HOOKS = "git config core.hooksPath .githooks"
SETUP = "python3 scripts/check_setup.py"
NO_KEYS = ("privileged", "capAdd", "securityOpt", "initializeCommand")
NO_RUN_ARGS = ("--privileged", "--cap-add", "--security-opt", "-v", "--volume", "--mount")
WARN = ("test_command, generate_command and setup_command run without a sandbox here, since only macOS has "
        "sandbox-exec: they can read any file your user can")
SHARED = "The workspace folder is shared with the host"


def load():
    """devcontainer.json, the Dockerfile and the README, as the tests read them."""
    return (json.loads((FOLDER / "devcontainer.json").read_text()), (FOLDER / "Dockerfile").read_text(),
            (FOLDER / "README.md").read_text())


def home(cfg):
    return "/home/{}".format(cfg.get("remoteUser", ""))


def mount_fields(mount):
    """A mount's source, target and type, from the string form or the object form."""
    if isinstance(mount, str):
        fields = dict(part.split("=", 1) for part in mount.split(",") if "=" in part)
    else:
        fields = dict(mount)
    return {"source": fields.get("source", fields.get("src", "")),
            "target": fields.get("target", fields.get("dst", fields.get("destination", ""))),
            "type": fields.get("type", "")}


def dockerfile_lines(text):
    """Each instruction on one line, with its backslash continuations joined."""
    return [line.strip() for line in re.sub(r"\\\n", " ", text).splitlines()
            if line.strip() and not line.strip().startswith("#")]


def tag_problem(ref, what):
    """Why an image or feature reference isn't pinned, or None when it is."""
    if "@sha256:" in ref:
        return None
    name = ref.rsplit("/", 1)[-1]
    if ":" not in name:
        return "{} {} has no version tag".format(what, ref)
    if name.split(":", 1)[1] == "latest":
        return "{} {} is tagged latest".format(what, ref)
    return None


def user_problems(cfg):
    user = cfg.get("remoteUser")
    if not user:
        return ["remoteUser isn't set, so the container's tools run as root"]
    if user == "root":
        return ["remoteUser is root"]
    return []


def pin_problems(cfg, dockerfile):
    found = [p for p in (tag_problem(ref, "feature") for ref in cfg.get("features", {})) if p]
    froms = [line.split()[1] for line in dockerfile_lines(dockerfile) if line.upper().startswith("FROM ")]
    if not froms:
        return found + ["the Dockerfile has no FROM line"]
    problem = tag_problem(froms[0], "image")
    if problem:
        return found + [problem]
    version = re.search(r"(?<![\d.])(\d+)\.(\d+)(?![\d.])", froms[0].rsplit("/", 1)[-1].split(":", 1)[1])
    if not version:
        found.append("the image tag {} doesn't name a Python version".format(froms[0]))
    elif (int(version.group(1)), int(version.group(2))) < (3, 9):
        found.append("the image's Python {}.{} is older than 3.9".format(version.group(1), version.group(2)))
    return found


def feature_name(ref):
    """A feature reference without its tag or digest."""
    ref = ref.split("@", 1)[0]
    folder, _, last = ref.rpartition("/")
    return folder + "/" + last.split(":", 1)[0]


def tool_problems(cfg, dockerfile):
    features = [feature_name(ref) for ref in cfg.get("features", {})]
    found = ["no {} feature".format(name) for name in (CLAUDE_FEATURE, GH_FEATURE) if name not in features]
    installs = [line.split() for line in dockerfile_lines(dockerfile) if "apt-get install" in line]
    words = {word for line in installs for word in line}
    found += ["the Dockerfile doesn't install {}".format(tool) for tool in ("git", "tmux") if tool not in words]
    return found


def mount_problems(cfg):
    """Every mount is a volume of this container's own, and only the two sign-ins may be mounted at all."""
    found = []
    allowed = ["{}/{}".format(home(cfg), name) for name in SIGN_INS]
    for mount in cfg.get("mounts", []):
        fields = mount_fields(mount)
        source, target = fields["source"], fields["target"]
        if fields["type"] != "volume":
            found.append("{} isn't a volume: a bind gives the container a folder of the host".format(mount))
        if "${devcontainerId}" not in source:
            found.append("{}'s source has no ${{devcontainerId}}, so other projects share it".format(mount))
        if any(text in source for text in ("/", "~", "${localEnv")):
            found.append("{}'s source is a path on the host".format(mount))
        if any(name in source for name in FORBIDDEN):
            found.append("{}'s source names a credential folder".format(mount))
        if target not in allowed:
            names = [name for name in FORBIDDEN if name in target]
            found.append("{} mounts over {}".format(mount, names[0]) if names
                         else "{} targets {}, not one of {}".format(mount, target, allowed))
    return found


def volume_problems(cfg):
    """Exactly the two sign-in volumes, named apart, and Claude Code told where its own is."""
    found = []
    claude, gh = ("{}/{}".format(home(cfg), name) for name in SIGN_INS)
    volumes = [mount_fields(m) for m in cfg.get("mounts", []) if mount_fields(m)["type"] == "volume"]
    if len(volumes) != 2:
        found.append("{} volumes, not 2".format(len(volumes)))
    if len({v["source"] for v in volumes}) != len(volumes):
        found.append("two volumes share a name")
    if sorted(v["target"] for v in volumes) != sorted([claude, gh]):
        found.append("the volumes aren't at {} and {}".format(claude, gh))
    if cfg.get("containerEnv", {}).get("CLAUDE_CONFIG_DIR") != claude:
        found.append("CLAUDE_CONFIG_DIR isn't {}".format(claude))
    return found


def post_create_problems(cfg):
    command = cfg.get("postCreateCommand", "")
    if isinstance(command, list):
        command = " ".join(command)
    if not isinstance(command, str):
        command = " ".join(str(part) for part in command.values())
    if HOOKS not in command:
        return ["postCreateCommand doesn't run {}".format(HOOKS)]
    if SETUP not in command[command.index(HOOKS):]:
        return ["postCreateCommand doesn't run {} after {}".format(SETUP, HOOKS)]
    return []


def privilege_problems(cfg):
    found = ["{} is set".format(key) for key in NO_KEYS if key in cfg]
    workspace = cfg.get("workspaceMount")
    if workspace is not None and mount_fields(workspace)["source"] != "${localWorkspaceFolder}":
        found.append("workspaceMount mounts something other than the workspace folder")
    found += ["runArgs has {}".format(arg) for arg in cfg.get("runArgs", [])
              if any(arg.startswith(prefix) for prefix in NO_RUN_ARGS)]
    return found


def readme_problems(text):
    return ["the README doesn't say {!r}".format(words) for words in (WARN, "gh auth login", SHARED)
            if words not in text]


def problems(cfg, dockerfile, readme=None):
    found = (user_problems(cfg) + pin_problems(cfg, dockerfile) + tool_problems(cfg, dockerfile)
             + mount_problems(cfg) + volume_problems(cfg) + post_create_problems(cfg) + privilege_problems(cfg))
    return found + (readme_problems(readme) if readme is not None else [])


class TheRealFiles(unittest.TestCase):
    def test_they_pass_every_check(self):
        self.assertEqual(problems(*load()), [])

    def test_the_readme_quotes_the_loops_warning_as_it_is_written(self):
        source = re.sub(r'"\s*\n\s*"', "", (ROOT / "scripts" / "loop.py").read_text())
        self.assertIn(WARN, source, "the loop's WARN line changed: quote the new one in the README and here")


class BadInputs(unittest.TestCase):
    """Each change to the real devcontainer.json or Dockerfile that a check has to catch."""

    def setUp(self):
        self.cfg, self.dockerfile, _ = load()

    def changed(self, **values):
        cfg = copy.deepcopy(self.cfg)
        cfg.update(values)
        return cfg

    def with_mount(self, mount):
        return self.changed(mounts=self.cfg["mounts"] + [mount])

    def test_a_bind_of_the_hosts_ssh_folder_fails(self):
        cfg = self.with_mount("source=${localEnv:HOME}/.ssh,target=/home/vscode/.ssh,type=bind")
        self.assertTrue(mount_problems(cfg))

    def test_a_bind_of_each_forbidden_folder_fails(self):
        for name in FORBIDDEN:
            with self.subTest(name=name):
                bind = "source=${{localEnv:HOME}}/{0},target=/home/vscode/{0},type=bind".format(name)
                self.assertTrue(mount_problems(self.changed(mounts=[bind])))
                as_object = {"source": "${localEnv:HOME}/" + name, "target": "/tmp/x", "type": "bind"}
                self.assertTrue(mount_problems(self.changed(mounts=[as_object])))

    def test_a_volume_at_aws_fails(self):
        for target in ("~/.aws", "/home/vscode/.aws"):
            with self.subTest(target=target):
                cfg = self.with_mount("source=aws-${{devcontainerId}},target={},type=volume".format(target))
                self.assertTrue(mount_problems(cfg))

    def test_a_volume_at_each_other_forbidden_folder_fails(self):
        for name in FORBIDDEN:
            if name in SIGN_INS:
                continue
            with self.subTest(name=name):
                volume = "source=v-${{devcontainerId}},target=/home/vscode/{},type=volume".format(name)
                self.assertTrue(mount_problems(self.with_mount(volume)))

    def test_a_sign_in_volume_shared_with_other_projects_fails(self):
        mounts = ["source=claude-code-config,target=/home/vscode/.claude,type=volume", self.cfg["mounts"][1]]
        self.assertTrue(mount_problems(self.changed(mounts=mounts)))

    def test_a_bind_at_a_sign_in_folder_fails(self):
        mounts = ["source=${localEnv:HOME}/.claude,target=/home/vscode/.claude,type=bind", self.cfg["mounts"][1]]
        self.assertTrue(mount_problems(self.changed(mounts=mounts)))
        self.assertTrue(volume_problems(self.changed(mounts=mounts)))

    def test_the_short_mount_field_names_are_read(self):
        cfg = self.with_mount("src=${localEnv:HOME}/.aws,dst=/home/vscode/.aws,type=bind")
        self.assertTrue(mount_problems(cfg))
        self.assertEqual(mount_fields("src=a,destination=/b,type=volume"),
                         {"source": "a", "target": "/b", "type": "volume"})

    def test_a_third_volume_or_two_with_one_name_fails(self):
        third = "source=x-${devcontainerId},target=/home/vscode/.cache,type=volume"
        self.assertTrue(volume_problems(self.with_mount(third)))
        same = [m.replace("gh-config-", "claude-code-config-") for m in self.cfg["mounts"]]
        self.assertIn("two volumes share a name", volume_problems(self.changed(mounts=same)))

    def test_claude_config_dir_elsewhere_fails(self):
        self.assertTrue(volume_problems(self.changed(containerEnv={"CLAUDE_CONFIG_DIR": "/tmp/claude"})))

    def test_an_image_tagged_latest_fails(self):
        dockerfile = re.sub(r"(?m)^FROM \S+", "FROM mcr.microsoft.com/devcontainers/python:latest", self.dockerfile)
        self.assertIn("image mcr.microsoft.com/devcontainers/python:latest is tagged latest",
                      pin_problems(self.cfg, dockerfile))

    def test_an_untagged_image_or_an_old_python_fails(self):
        for image in ("mcr.microsoft.com/devcontainers/python", "mcr.microsoft.com/devcontainers/python:1-3.8-bookworm"):
            with self.subTest(image=image):
                dockerfile = re.sub(r"(?m)^FROM \S+", "FROM " + image, self.dockerfile)
                self.assertTrue(pin_problems(self.cfg, dockerfile))

    def test_a_bare_or_latest_feature_fails(self):
        for ref in ("ghcr.io/devcontainers/features/node", "ghcr.io/devcontainers/features/node:latest"):
            with self.subTest(ref=ref):
                features = dict(self.cfg["features"], **{ref: {}})
                self.assertTrue(pin_problems(self.changed(features=features), self.dockerfile))

    def test_a_feature_pinned_by_digest_passes(self):
        features = {k: v for k, v in self.cfg["features"].items() if "node" not in k}
        features["ghcr.io/devcontainers/features/node@sha256:" + "0" * 64] = {}
        self.assertEqual(pin_problems(self.changed(features=features), self.dockerfile), [])

    def test_a_missing_tool_fails(self):
        features = {k: v for k, v in self.cfg["features"].items() if "claude-code" not in k}
        self.assertTrue(tool_problems(self.changed(features=features), self.dockerfile))
        features = {k: v for k, v in self.cfg["features"].items() if "github-cli" not in k}
        self.assertTrue(tool_problems(self.changed(features=features), self.dockerfile))
        self.assertIn("the Dockerfile doesn't install tmux",
                      tool_problems(self.cfg, re.sub(r"\btmux\b", "", self.dockerfile)))

    def test_privileged_fails(self):
        self.assertEqual(privilege_problems(self.changed(privileged=True)), ["privileged is set"])

    def test_cap_add_or_a_volume_in_run_args_fails(self):
        for args in (["--cap-add=NET_ADMIN"], ["-v", "/:/host"], ["--mount=type=bind,src=/,dst=/host"]):
            with self.subTest(args=args):
                self.assertTrue(privilege_problems(self.changed(runArgs=args)))

    def test_a_workspace_mount_of_another_folder_fails(self):
        cfg = self.changed(workspaceMount="source=${localEnv:HOME},target=/workspace,type=bind")
        self.assertTrue(privilege_problems(cfg))

    def test_root_fails(self):
        self.assertEqual(user_problems(self.changed(remoteUser="root")), ["remoteUser is root"])
        cfg = copy.deepcopy(self.cfg)
        del cfg["remoteUser"]
        self.assertTrue(user_problems(cfg))

    def test_the_setup_check_before_the_hooks_fails(self):
        cfg = self.changed(postCreateCommand="{} && {}".format(SETUP, HOOKS))
        self.assertEqual(post_create_problems(cfg),
                         ["postCreateCommand doesn't run {} after {}".format(SETUP, HOOKS)])

    def test_a_comment_in_devcontainer_json_fails_to_load(self):
        text = (FOLDER / "devcontainer.json").read_text()
        with self.assertRaises(json.JSONDecodeError):
            json.loads(text.replace("{", "{\n  // a comment", 1))

    def test_a_readme_missing_its_warning_fails(self):
        _, _, readme = load()
        self.assertEqual(readme_problems(readme.replace(WARN, "")), ["the README doesn't say {!r}".format(WARN)])


class GoodInputs(unittest.TestCase):
    """What the checks must let through."""

    def setUp(self):
        self.cfg, self.dockerfile, _ = load()

    def test_the_two_sign_in_volumes_pass_though_their_folders_are_forbidden(self):
        self.assertIn(".claude", FORBIDDEN)
        self.assertIn(".config/gh", FORBIDDEN)
        cfg = {"remoteUser": "vscode", "containerEnv": {"CLAUDE_CONFIG_DIR": "/home/vscode/.claude"},
               "mounts": ["source=claude-code-config-${devcontainerId},target=/home/vscode/.claude,type=volume",
                          {"source": "gh-config-${devcontainerId}", "target": "/home/vscode/.config/gh",
                           "type": "volume"}]}
        self.assertEqual(mount_problems(cfg) + volume_problems(cfg), [])

    def test_no_workspace_mount_passes(self):
        self.assertNotIn("workspaceMount", self.cfg)
        self.assertEqual(privilege_problems(self.cfg), [])

    def test_the_default_workspace_mount_passes(self):
        cfg = dict(self.cfg, workspaceMount="source=${localWorkspaceFolder},target=/workspaces/x,type=bind")
        self.assertEqual(privilege_problems(cfg), [])


if __name__ == "__main__":
    unittest.main()
