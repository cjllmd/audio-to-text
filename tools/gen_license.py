#!/usr/bin/env python3
"""卖方注册码签发工具（永久授权）。

用法：
  1) 首次：生成密钥对
     python tools/gen_license.py gen-keypair --out tools/keys

  2) 把生成的公钥 PEM 内容粘贴到 license.py 的 PUBLIC_KEY_PEM。

  3) 为某台机器签发注册码（永久有效）：
     python tools/gen_license.py issue --machine XXXXX... --key tools/keys/private.pem

  4) 校验某个注册码：
     python tools/gen_license.py verify --code "...."
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from license import verify_license, sign_license


def gen_keypair(out_dir: Path) -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    out_dir.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = out_dir / "private.pem"
    pub = out_dir / "public.pem"
    priv.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    pub.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    print(f"私钥已写入：{priv}  （请立即妥善保管，勿外泄）")
    print(f"公钥已写入：{pub}")
    print("\n请将 public.pem 的内容完整粘贴到 license.py 的 PUBLIC_KEY_PEM：")


def issue(machine: str, key_path: Path) -> None:
    key = key_path.read_bytes()
    code = sign_license(machine, key)
    print(f"机器码：{machine}")
    print("有效期：永久")
    print("注册码（发给客户）：")
    print(code)


def verify(code: str) -> None:
    ok, msg, info = verify_license(code)
    print(f"结果：{'✓ 有效' if ok else '✗ 无效'} — {msg}")
    if info:
        for k, v in info.items():
            print(f"  {k}: {v}")


def main() -> int:
    parser = argparse.ArgumentParser(description="音频转文字 注册码签发工具")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_kp = sub.add_parser("gen-keypair", help="生成 RSA 密钥对")
    p_kp.add_argument("--out", type=Path, default=Path("tools/keys"), help="输出目录")

    p_issue = sub.add_parser("issue", help="为机器码签发注册码（永久）")
    p_issue.add_argument("--machine", required=True, help="客户的机器码（24位）")
    p_issue.add_argument("--key", type=Path, default=Path("tools/keys/private.pem"), help="私钥路径")

    p_verify = sub.add_parser("verify", help="校验注册码")
    p_verify.add_argument("--code", required=True, help="注册码")

    args = parser.parse_args()
    if args.cmd == "gen-keypair":
        gen_keypair(args.out)
    elif args.cmd == "issue":
        issue(args.machine, args.key)
    elif args.cmd == "verify":
        verify(args.code)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())