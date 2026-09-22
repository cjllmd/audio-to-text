"""软件注册授权：机器码采集 + RSA 非对称签名授权（永久授权，无过期）。

流程：
  1. 采集硬件指纹计算机器码。
  2. 卖方用私钥对「机器码」签名，得到注册码。
  3. 软件内置公钥验签，校验机器码与当前机器匹配。

公钥内嵌于本文件；私钥由卖方单独保存（tools/gen_license.py 生成）。
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REG_FILE = Path.home() / ".asr_license.json"
TRIAL_MAX = 5


def _trial_file() -> Path:
    home = Path.home()
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", home)) / "asr"
    elif sys.platform == "darwin":
        base = home / "Library" / "Application Support" / "asr"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share")) / "asr"
    base.mkdir(parents=True, exist_ok=True)
    return base / "trial.dat"


def _trial_shadow_paths() -> list[Path]:
    home = Path.home()
    if sys.platform == "win32":
        appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        localappdata = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        return [
            appdata / "asr_cache" / "shadow.dat",
            localappdata / "asr_data" / "cache.dat",
            localappdata / "Temp" / "asr_tmp.dat",
        ]
    elif sys.platform == "darwin":
        return [
            home / "Library" / "Caches" / "com.apple.dt.Xcode" / "asr_shadow.dat",
            home / "Library" / "Preferences" / "asr_pref.dat",
            home / ".asr_shadow",
        ]
    else:
        return [
            home / ".cache" / "asr_shadow.dat",
            home / ".config" / "asr_pref.dat",
            home / ".asr_shadow",
        ]


PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAqYMAMTfZprD/eXWvCK9U
ZpcM9vK8pvqHjDl3+yWOT6HrY7M/dR4EQCpZ/W4ijv1cWkIO/h3R/idkxlizKjgL
6pIDfJWAnMjWKeZCJsBWeb8qwA70Qez/U2rZYZpwjmKk0aUjRSJts/X5Tr2tb3xV
FVhOshrstugE37iDL4zeyRe9iS+dqxB+jpCVNeDDlLx+z6ybUT/1GlXcYLuARLPt
LSsST6I5G2AydGq8xmPONqtG0RTWQd2sD7MvwlnPXBFUZcWyG9dRtvEF2GSIzmfF
i6RHREdQYwtFKNUoBEmVvttOOIYJW1Qpzvc6ABFpcF8ntots4wqyU1rXyJLM+e2g
xQIDAQAB
-----END PUBLIC KEY-----"""

_PUBLIC_KEY_HASH = hashlib.sha256(PUBLIC_KEY_PEM).hexdigest()[:16]
_LICENSE_VERSION = "1"


def _run(args: list[str]) -> str:
    try:
        kwargs = {"capture_output": True, "text": True, "timeout": 10}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        out = subprocess.run(args, **kwargs)
        return (out.stdout or out.stderr or "").strip()
    except Exception:
        return ""


def _ioreg_entries() -> list[str]:
    raw = _run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"])
    items = []
    for line in raw.splitlines():
        for key in ("IOPlatformUUID", "IOPlatformSerialNumber", "board-id"):
            if key in line and "=" in line:
                val = line.split("=", 1)[1].strip().strip('"')
                if val:
                    items.append(f"{key}:{val}")
    return items


def _sysctl_hw() -> list[str]:
    out = []
    for key in ("hw.model", "hw.machine", "hw.ncpu", "hw.memsize"):
        v = _run(["sysctl", "-n", key])
        if v:
            out.append(f"{key}:{v}")
    return out


def _mac_addresses() -> list[str]:
    out = []
    if sys.platform == "win32":
        raw = _run(["ipconfig", "/all"])
        for line in raw.splitlines():
            if "Physical Address" in line or "物理地址" in line:
                mac = line.split(":")[-1].strip()
                if mac:
                    out.append("mac:" + mac.replace("-", ":"))
    else:
        ifs = _run(["ifconfig"]).splitlines()
        cur = None
        for line in ifs:
            s = line.strip()
            if s.startswith("en") or s.startswith("eth"):
                cur = s.split(":")[0]
            elif "ether" in s and cur:
                mac = s.split("ether", 1)[1].strip()
                out.append(f"mac:{cur}:{mac}")
                cur = None
    return out


def _windows_hw() -> list[str]:
    out = []
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography"
        ) as k:
            out.append("MachineGuid:" + winreg.QueryValueEx(k, "MachineGuid")[0])
    except Exception:
        pass
    import re
    for cmd, label in (
        (["powershell", "-NoProfile", "-NonInteractive", "-Command",
          "Get-WmiObject Win32_DiskDrive | Select-Object -ExpandProperty SerialNumber"], "disk"),
        (["powershell", "-NoProfile", "-NonInteractive", "-Command",
          "Get-WmiObject Win32_BIOS | Select-Object -ExpandProperty SerialNumber"], "bios"),
        (["powershell", "-NoProfile", "-NonInteractive", "-Command",
          "Get-WmiObject Win32_Processor | Select-Object -ExpandProperty ProcessorId"], "cpu"),
    ):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            val = r.stdout.strip()
            if val and not re.fullmatch(r"[\s_]+", val):
                out.append(f"{label}:{val}")
        except Exception:
            pass
    return out


def machine_code() -> str:
    if sys.platform == "win32":
        parts = _windows_hw() + _mac_addresses()
    else:
        parts = _ioreg_entries() + _sysctl_hw() + _mac_addresses()
    if not parts:
        raise RuntimeError("无法读取本机硬件信息，无法生成机器码")
    digest = hashlib.sha256("\n".join(sorted(set(parts))).encode("utf-8")).hexdigest()
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    num = int(digest, 16)
    code = []
    for _ in range(24):
        code.append(alphabet[num % len(alphabet)])
        num //= len(alphabet)
    return "".join(reversed(code))


def _b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64decode(data: str) -> bytes:
    return base64.b64decode(data.encode("ascii"))


def sign_license(machine: str, private_key_pem: bytes) -> str:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    key = serialization.load_pem_private_key(private_key_pem, password=None)
    payload = f"{_LICENSE_VERSION}|{machine}".encode("utf-8")
    signature = key.sign(payload, padding.PKCS1v15(), hashes.SHA256())
    return _b64encode(payload) + "." + _b64encode(signature)


def verify_license(code: str) -> tuple[bool, str, dict]:
    try:
        if hashlib.sha256(PUBLIC_KEY_PEM).hexdigest()[:16] != _PUBLIC_KEY_HASH:
            return False, "授权模块完整性校验失败", {}
        try:
            payload_b64, sig_b64 = code.strip().split(".", 1)
        except ValueError:
            return False, "注册码格式不正确", {}
        payload = _b64decode(payload_b64)
        signature = _b64decode(sig_b64)
        try:
            parts = payload.decode("utf-8").split("|")
            version, machine = parts[0], parts[1]
        except (ValueError, IndexError):
            return False, "注册码内容损坏", {}
        if version != _LICENSE_VERSION:
            return False, "注册码版本不兼容", {}
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        pub = serialization.load_pem_public_key(PUBLIC_KEY_PEM)
        try:
            pub.verify(signature, payload, padding.PKCS1v15(), hashes.SHA256())
        except Exception:
            return False, "注册码签名无效（非本软件签发）", {}
        return True, "注册有效", {"machine": machine}
    except Exception as e:
        return False, f"注册码无法解析：{e}", {}


def _machine_matches(info: dict) -> bool:
    try:
        return info.get("machine") == machine_code()
    except RuntimeError:
        return False


def save_registration(code: str) -> bool:
    ok, msg, info = verify_license(code)
    if not ok:
        return False
    if not _machine_matches(info):
        return False
    try:
        REG_FILE.write_text(
            json.dumps({"code": code, "machine": info.get("machine")}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        return False
    reset_trial()
    return True


def current_registration() -> dict | None:
    if not REG_FILE.exists():
        return None
    try:
        data = json.loads(REG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    code = data.get("code", "")
    ok, msg, info = verify_license(code)
    if not ok or not _machine_matches(info):
        return None
    info["msg"] = msg
    return info


def _trial_fernet():
    from cryptography.fernet import Fernet

    try:
        code = machine_code()
    except RuntimeError:
        code = "unknown"
    key = base64.urlsafe_b64encode(hashlib.sha256(f"asr_trial_fernet:{code}".encode()).digest())
    return Fernet(key)


def _encrypt_trial(count: int) -> str:
    return _trial_fernet().encrypt(str(count).encode("utf-8")).decode("ascii")


def _decrypt_trial(data: str) -> int:
    try:
        plain = _trial_fernet().decrypt(data.encode("ascii"))
        return int(plain.decode("utf-8"))
    except Exception:
        return 0


def _mark_trial_used():
    data = {}
    if REG_FILE.exists():
        try:
            data = json.loads(REG_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    data["trial_used"] = True
    try:
        REG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def _is_trial_marked() -> bool:
    if not REG_FILE.exists():
        return False
    try:
        data = json.loads(REG_FILE.read_text(encoding="utf-8"))
        return bool(data.get("trial_used"))
    except (OSError, ValueError):
        return False


def _read_trial_from_shadows() -> int | None:
    max_count = None
    for p in _trial_shadow_paths():
        if p.exists():
            try:
                c = _decrypt_trial(p.read_text(encoding="utf-8").strip())
                if max_count is None or c > max_count:
                    max_count = c
            except (OSError, ValueError):
                pass
    return max_count


def trial_count() -> int:
    tf = _trial_file()
    if tf.exists():
        try:
            count = _decrypt_trial(tf.read_text(encoding="utf-8").strip())
            return count
        except (OSError, ValueError):
            pass
    shadow_count = _read_trial_from_shadows()
    if shadow_count is not None:
        return max(shadow_count, 1)
    if _is_trial_marked():
        return TRIAL_MAX
    return 0


def increment_trial() -> int:
    count = trial_count() + 1
    encrypted = _encrypt_trial(count)
    tf = _trial_file()
    try:
        tf.parent.mkdir(parents=True, exist_ok=True)
        tf.write_text(encrypted, encoding="utf-8")
    except OSError:
        pass
    for p in _trial_shadow_paths():
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(encrypted, encoding="utf-8")
        except OSError:
            pass
    _mark_trial_used()
    remaining = TRIAL_MAX - count
    return remaining if remaining >= 0 else 0


def reset_trial():
    tf = _trial_file()
    try:
        if tf.exists():
            tf.unlink()
    except OSError:
        pass
    for p in _trial_shadow_paths():
        try:
            if p.exists():
                p.unlink()
        except OSError:
            pass
    if REG_FILE.exists():
        try:
            data = json.loads(REG_FILE.read_text(encoding="utf-8"))
            data.pop("trial_used", None)
            if not data.get("code") and not data.get("machine"):
                REG_FILE.unlink()
            else:
                REG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass


def is_registered() -> bool:
    return current_registration() is not None