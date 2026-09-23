#!/usr/bin/env python3
"""卖方注册码签发工具（永久授权）。

用法：
  1) 首次：生成密钥对
     python tools/gen_license.py gen-keypair --out tools/keys

  2) 运行混淆编码工具，将公钥转为 XOR 分段编码：
     python tools/gen_license.py encode-pub --pub tools/keys/public.pem

  3) 将输出的编码常量替换到 license.py 顶部的 _PEM_E1/E2/E3 等变量。

  4) 为某台机器签发注册码（永久有效）：
     python tools/gen_license.py issue --machine XXXXX... --key tools/keys/private.pem

  5) 校验某个注册码：
     python tools/gen_license.py verify --code "...."
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from license import verify_license, sign_license, _PEM_XK, _PK_HASH_XK, _PK_CRC_XK


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
    print("\n下一步：运行 encode-pub 命令生成混淆编码常量")


def encode_pub(pub_path: Path) -> None:
    pem = pub_path.read_bytes()
    n = len(pem)
    s1, s2, s3 = pem[:n//3], pem[n//3:2*n//3], pem[2*n//3:]
    xk = _PEM_XK
    e1 = base64.b64encode(bytes(b ^ xk[0] for b in s1)).decode()
    e2 = base64.b64encode(bytes(b ^ xk[1] for b in s2)).decode()
    e3 = base64.b64encode(bytes(b ^ xk[2] for b in s3)).decode()

    h = hashlib.sha256(pem).hexdigest()
    hash_xor_xk = _PK_HASH_XK
    hash_ints = [ord(c) ^ hash_xor_xk for c in h]

    crc = zlib.crc32(pem) & 0xFFFFFFFF
    crc_xor = crc ^ _PK_CRC_XK

    print("将以下常量替换到 license.py：\n")
    print(f'_PEM_E1 = "{e1}"')
    print(f'_PEM_E2 = "{e2}"')
    print(f'_PEM_E3 = "{e3}"')
    print(f"_PEM_XK = {xk}")
    print(f"\n_PK_HASH_XOR = {hash_ints}")
    print(f"_PK_HASH_XK = {hex(hash_xor_xk)}")
    print(f"_PK_CRC_XOR = {crc_xor}")
    print(f"_PK_CRC_XK = {hex(_PK_CRC_XK)}")


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

    p_enc = sub.add_parser("encode-pub", help="将公钥 PEM 编码为混淆常量")
    p_enc.add_argument("--pub", type=Path, default=Path("tools/keys/public.pem"), help="公钥路径")

    p_issue = sub.add_parser("issue", help="为机器码签发注册码（永久）")
    p_issue.add_argument("--machine", required=True, help="客户的机器码（24位）")
    p_issue.add_argument("--key", type=Path, default=Path("tools/keys/private.pem"), help="私钥路径")

    p_verify = sub.add_parser("verify", help="校验注册码")
    p_verify.add_argument("--code", required=True, help="注册码")

    args = parser.parse_args()
    if args.cmd == "gen-keypair":
        gen_keypair(args.out)
    elif args.cmd == "encode-pub":
        encode_pub(args.pub)
    elif args.cmd == "issue":
        issue(args.machine, args.key)
    elif args.cmd == "verify":
        verify(args.code)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())