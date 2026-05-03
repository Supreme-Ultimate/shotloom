"""Small production management CLI."""
from __future__ import annotations

import argparse
import getpass
import sys

from auth import hash_password
from database import Credits, CreditTransaction, SessionLocal, User, init_db
from config import INITIAL_CREDITS


def _prompt_password(password: str | None) -> str:
    if password:
        return password
    first = getpass.getpass("Password: ")
    second = getpass.getpass("Confirm password: ")
    if first != second:
        raise SystemExit("Passwords do not match")
    return first


def create_admin(args: argparse.Namespace) -> None:
    init_db()
    password = _prompt_password(args.password)
    if len(password) < 6:
        raise SystemExit("Password must be at least 6 characters")

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == args.email).first()
        if user:
            if not args.update_existing:
                raise SystemExit("User already exists. Use --update-existing to promote/reset it.")
            user.hashed_password = hash_password(password)
            user.display_name = args.display_name or user.display_name or args.email.split("@")[0]
            user.is_active = True
            user.is_superuser = True
            user.is_verified = True
        else:
            user = User(
                email=args.email,
                hashed_password=hash_password(password),
                display_name=args.display_name or args.email.split("@")[0],
                is_active=True,
                is_superuser=True,
                is_verified=True,
            )
            db.add(user)
            db.flush()
            db.add(Credits(user_id=user.id, balance=INITIAL_CREDITS))
            db.add(CreditTransaction(user_id=user.id, delta=INITIAL_CREDITS, reason="initial_grant"))
        db.commit()
        print(f"Admin ready: {args.email}")
    finally:
        db.close()


def reset_password(args: argparse.Namespace) -> None:
    init_db()
    password = _prompt_password(args.password)
    if len(password) < 6:
        raise SystemExit("Password must be at least 6 characters")

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == args.email).first()
        if not user:
            raise SystemExit("User not found")
        user.hashed_password = hash_password(password)
        user.is_active = True
        db.commit()
        print(f"Password reset: {args.email}")
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Video analysis management CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-admin", help="Create or promote an admin user")
    create.add_argument("email")
    create.add_argument("--password")
    create.add_argument("--display-name", default="")
    create.add_argument("--update-existing", action="store_true")
    create.set_defaults(func=create_admin)

    reset = sub.add_parser("reset-password", help="Reset a user's password")
    reset.add_argument("email")
    reset.add_argument("--password")
    reset.set_defaults(func=reset_password)

    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
