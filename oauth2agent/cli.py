from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .core import (
    DEFAULT_AUTH_API_BASE,
    DEFAULT_CODEX_BASE,
    OAuth2AgentError,
    check_conversation_isolation,
    convert_oauth_to_agent_identity,
    load_identity_file,
    load_oauth_file,
    verify_responses,
    write_identity_file,
)
from .mock import run_simulation
from .oauth_login import DEFAULT_ISSUER, interactive_oauth
from . import __version__


def _default_output(input_path: str) -> str:
    path = Path(input_path)
    return str(path.with_name(path.stem + "-agent.json"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oauth2agent",
        description="Standalone ChatGPT/Codex OAuth -> Codex Agent Identity converter.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    login = sub.add_parser("login", help="perform ChatGPT OAuth interactively, then create Agent Identity")
    login.add_argument("-o", "--output", default="codex-agent-identity.json")
    login.add_argument("--format", choices=["sub2api", "codex"], default="sub2api")
    login.add_argument("--issuer", default=DEFAULT_ISSUER)
    login.add_argument("--auth-api-base", default=DEFAULT_AUTH_API_BASE)
    login.add_argument("--port", type=int, default=1455)
    login.add_argument("--manual", action="store_true", help="paste callback URL instead of listening on localhost")
    login.add_argument("--no-browser", action="store_true")

    convert = sub.add_parser("convert", help="convert an existing OAuth JSON file")
    convert.add_argument("input", help="Codex auth.json or JSON exported from another tool")
    convert.add_argument("-o", "--output")
    convert.add_argument("--format", choices=["sub2api", "codex"], default="sub2api")
    convert.add_argument("--auth-api-base", default=DEFAULT_AUTH_API_BASE)

    verify = sub.add_parser("verify", help="verify an Agent Identity against Codex Responses")
    verify.add_argument("input")
    verify.add_argument("--codex-base", default=DEFAULT_CODEX_BASE)
    verify.add_argument("--model", default="gpt-5.4")
    verify.add_argument("--prompt", default="Reply with exactly: OK")
    verify.add_argument("--check-isolation", action="store_true")

    simulate = sub.add_parser("simulate", help="run an offline local simulation with no real OAuth or quota usage")
    simulate.add_argument("--output-dir")

    return parser


def _print_summary(identity, output: str) -> None:
    print(f"Agent runtime: {identity.agent_runtime_id}")
    print(f"Task ID:       {identity.task_id}")
    print(f"Account ID:    {identity.account_id}")
    print(f"User ID:       {identity.chatgpt_user_id}")
    print(f"Plan:          {identity.plan_type}")
    if identity.email:
        print(f"Email:         {identity.email}")
    print(f"Output:        {output}")
    print("OAuth tokens:  NOT written")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "login":
            oauth = interactive_oauth(
                issuer=args.issuer,
                port=args.port,
                manual=args.manual,
                open_browser=not args.no_browser,
            )
            identity = convert_oauth_to_agent_identity(oauth, auth_api_base=args.auth_api_base)
            write_identity_file(args.output, identity, output_format=args.format)
            _print_summary(identity, args.output)
            return 0

        if args.command == "convert":
            oauth = load_oauth_file(args.input)
            identity = convert_oauth_to_agent_identity(oauth, auth_api_base=args.auth_api_base)
            output = args.output or _default_output(args.input)
            write_identity_file(output, identity, output_format=args.format)
            _print_summary(identity, output)
            return 0

        if args.command == "verify":
            identity = load_identity_file(args.input)
            text = verify_responses(identity, codex_base=args.codex_base, model=args.model, prompt=args.prompt)
            print("Responses:", text)
            if args.check_isolation:
                status = check_conversation_isolation(identity, codex_base=args.codex_base)
                print(f"Conversations endpoint: HTTP {status}")
                if status not in {401, 403}:
                    raise OAuth2AgentError("conversation isolation check failed")
            return 0

        if args.command == "simulate":
            report = run_simulation(args.output_dir)
            print(f"OAuth source:  {report.email or 'demo'} ({report.plan_type})")
            print(f"Agent runtime: {report.runtime_id}")
            print(f"Task ID:       {report.task_id}")
            print(f"Output file:   {report.output_file}")
            print(f"Responses:     {report.response_text!r}")
            print(f"Isolation:     HTTP {report.isolation_status}")
            print("SIMULATION PASSED")
            return 0

        raise AssertionError("unreachable")
    except OAuth2AgentError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
