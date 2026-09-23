"""软件注册授权：机器码采集 + RSA 非对称签名授权（永久授权，无过期）。

安全增强：
  - 公钥混淆存储（XOR 分段 + 双重完整性校验）
  - 多点授权检查（GUI + 核心识别函数）
  - 授权文件加密存储（Fernet + HMAC）
  - 试用计数增强（基于机器码的不可预测 shadow 路径 + 时间戳防回拨）
  - 机器码采集加固（格式校验 + 交叉验证）
  - 反调试检测（环境变量 / API 检测）
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path

REG_FILE = Path.home() / ".asr_license.json"
TRIAL_MAX = 3

_PEM_E1 = "d3d3d3cYHx0TFHoKDxgWExl6ER8Dd3d3d3dQFxMTGBMwGxQYPTErMjEzHWMtahgbCx8cGxsVGRsLYhsXExMYGT0RGRsLHxsuCGwfCjh1Dh0JNBw8EzgMCzs0LFAAaRsxFGsfcQljaxsObBs+Dy91cT5vNQoLMBALEQ0wKDMSDAkAFBttais2MTsTOTssPBEgPWI9EB4X"
_PEM_E2 = "xtTqiNnTqeDN88To6/rW8MD1kcXoz/mQk5Pv7uDXxuLC7Ij7+Zv25PaS1s/qkOeQ1MntwODC8vvozZvt1cTaz8mQm/HS64ip5sqa59fHksWU5uDOyfL29vnbk5HW0JbM4eDn7JaU5+Dh2tnFk9rPyJP19Pr2zJTv4u7gxPuTxOTR6c7U7OuW4Knhz5TszuzbkOrGwfbV"
_PEM_E3 = "sJX3lPaolZP/rpD094OzpvOphaPxjJe2s6uAroamrLXz/7GMofORr5aljaWlq6CGhv6OzYKvi/6JtfHwiaamlKGXvbGpqvCNoKiUsZHxno2BqbKMiKyDqoKJi5H+sYvyooCqhK2+8KmorrLwg6uOk4rosIDNsJaOg4aWhoXN6urq6uqCiYPnl5KFi46E54yCnurq6urqzQ=="
_PEM_XK = (90, 163, 199)

_PK_HASH_XOR = [66, 73, 24, 66, 24, 67, 25, 79, 79, 75, 31, 67, 79, 73, 30, 73, 66, 74, 79, 72, 26, 76, 76, 78, 66, 79, 74, 30, 25, 79, 31, 72, 67, 29, 73, 29, 24, 30, 30, 29, 31, 75, 67, 73, 25, 67, 31, 24, 31, 66, 29, 76, 66, 76, 79, 76, 31, 24, 25, 24, 67, 31, 26, 76]
_PK_HASH_XK = 0x7b
_PK_CRC_XOR = 2489191069
_PK_CRC_XK = 0xdeadbeef

_LICENSE_VERSION = "1"

def _make_verifier():
    """闭包隐藏全局状态：公钥和完整性校验封装在闭包中，防止外部 patch 全局变量。"""
    s1 = bytes(b ^ _PEM_XK[0] for b in base64.b64decode(_PEM_E1))
    s2 = bytes(b ^ _PEM_XK[1] for b in base64.b64decode(_PEM_E2))
    s3 = bytes(b ^ _PEM_XK[2] for b in base64.b64decode(_PEM_E3))
    pem = s1 + s2 + s3

    h = hashlib.sha256(pem).hexdigest()
    expected_h = "".join(chr(v ^ _PK_HASH_XK) for v in _PK_HASH_XOR)
    crc = zlib.crc32(pem) & 0xFFFFFFFF
    expected_crc = _PK_CRC_XOR ^ _PK_CRC_XK

    pub_key_cache = None

    def get_pub_key():
        nonlocal pub_key_cache
        if pub_key_cache is None:
            from cryptography.hazmat.primitives import serialization
            pub_key_cache = serialization.load_pem_public_key(pem)
        return pub_key_cache

    def verify_pk_integrity() -> bool:
        if hashlib.sha256(pem).hexdigest() != expected_h:
            return False
        if (zlib.crc32(pem) & 0xFFFFFFFF) != expected_crc:
            return False
        return True

    return get_pub_key, verify_pk_integrity


_get_pub_key, _verify_pk_integrity = _make_verifier()

# 以下两行防止 _make_verifier 产生的闭包被垃圾回收后重新定义
_verify_pk_integrity_cell = _verify_pk_integrity.__code__
import sys as _sys
if _verify_pk_integrity_cell is not _verify_pk_integrity.__code__:
    _sys.exit(1)

def _make_debugger_check():
    """闭包封装反调试状态，防止外部直接 patch `_debug_tainted` 变量。"""
    _tainted = False

    def check():
        nonlocal _tainted
        if _tainted:
            return True
        try:
            if sys.platform == "win32":
                import ctypes
                if ctypes.windll.kernel32.IsDebuggerPresent():
                    _tainted = True
                    return True
                ptr = ctypes.c_int()
                if ctypes.windll.kernel32.CheckRemoteDebuggerPresent(
                    ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(ptr)
                ):
                    if ptr.value:
                        _tainted = True
                        return True
            debug_env_vars = [
                "DYLD_INSERT_LIBRARIES", "LD_PRELOAD",
                "_XCODE_DEBUG", "PYDEVD_LOAD_VALUES_ASYNC",
                "PYTHONDEBUG", "PYTHONINSPECT",
                "PYCHARM_HOSTED", "PYDEV_CONSOLE_ENCODING",
                "VSCODE_DEBUG", "DEBUGPY_ENABLE",
            ]
            for var in debug_env_vars:
                if os.environ.get(var):
                    _tainted = True
                    return True
            if sys.platform == "darwin":
                import ctypes
                libc = ctypes.CDLL("libc.dylib", use_errno=True)
                P_TRACED = 0x00000800
                kinfo_proc_size = 4096
                buf = ctypes.create_string_buffer(kinfo_proc_size)
                size = ctypes.c_size_t(kinfo_proc_size)
                mib = (ctypes.c_int * 4)(1, 14, libc.getpid(), 0)
                if libc.sysctl(mib, 4, buf, ctypes.byref(size), None, 0) == 0:
                    kp_flags = struct.unpack_from("N", buf.raw, 32)[0] if size.value >= 40 else 0
                    if kp_flags & P_TRACED:
                        _tainted = True
                        return True
            if sys.platform == "linux":
                try:
                    with open("/proc/self/status") as f:
                        for line in f:
                            if line.startswith("TracerPid:"):
                                pid = line.split(":")[1].strip()
                                if pid != "0":
                                    _tainted = True
                                    return True
                                break
                except (OSError, IOError):
                    pass
                if os.environ.get("LD_PRELOAD"):
                    _tainted = True
                    return True
        except Exception:
            pass
        return False

    def is_tainted():
        return _tainted

    return check, is_tainted


_check_debugger, _debug_is_tainted = _make_debugger_check()

# 模块加载时立即执行一次反调试检查
_check_debugger()


def _run(args: list[str]) -> str:
    try:
        kwargs = {"capture_output": True, "text": True, "timeout": 10}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        out = subprocess.run(args, **kwargs)
        return (out.stdout or out.stderr or "").strip()
    except Exception:
        return ""


def _validate_uuid(val: str) -> bool:
    if len(val) != 36:
        return False
    parts = val.split("-")
    if [len(p) for p in parts] != [8, 4, 4, 4, 12]:
        return False
    return all(c in "0123456789ABCDEFabcdef" for p in parts for c in p)


def _validate_mac(val: str) -> bool:
    clean = val.replace(":", "").replace("-", "").upper()
    return len(clean) == 12 and all(c in "0123456789ABCDEF" for c in clean)


def _ioreg_entries() -> list[str]:
    raw = _run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"])
    items = []
    for line in raw.splitlines():
        for key in ("IOPlatformUUID", "IOPlatformSerialNumber", "board-id"):
            if key in line and "=" in line:
                val = line.split("=", 1)[1].strip().strip('"')
                if val:
                    if key == "IOPlatformUUID" and not _validate_uuid(val):
                        continue
                    items.append(f"{key}:{val}")
    return items


def _sysctl_hw() -> list[str]:
    out = []
    for key in ("hw.model", "hw.machine", "hw.ncpu", "hw.memsize"):
        v = _run(["sysctl", "-n", key])
        if v:
            if key == "hw.ncpu":
                try:
                    n = int(v)
                    if n < 1 or n > 256:
                        continue
                except ValueError:
                    continue
            if key == "hw.memsize":
                try:
                    m = int(v)
                    if m < 1_000_000 or m > 10_000_000_000_000:
                        continue
                except ValueError:
                    continue
            out.append(f"{key}:{v}")
    return out


def _mac_addresses() -> list[str]:
    out = []
    if sys.platform == "win32":
        raw = _run(["ipconfig", "/all"])
        for line in raw.splitlines():
            if "Physical Address" in line or "物理地址" in line:
                mac = line.split(":")[-1].strip()
                if mac and _validate_mac(mac):
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
                if _validate_mac(mac):
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
            guid = winreg.QueryValueEx(k, "MachineGuid")[0]
            if _validate_uuid(guid):
                out.append("MachineGuid:" + guid)
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


def _license_fernet():
    from cryptography.fernet import Fernet
    try:
        mc = machine_code()
    except RuntimeError:
        mc = "unknown"
    key_material = hashlib.sha256(f"asr_license_fernet:{mc}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key_material))


def _license_hmac_key() -> bytes:
    try:
        mc = machine_code()
    except RuntimeError:
        mc = "unknown"
    return hashlib.sha256(f"asr_license_hmac:{mc}".encode()).digest()


def sign_license(machine: str, private_key_pem: bytes) -> str:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    key = serialization.load_pem_private_key(private_key_pem, password=None)
    payload = f"{_LICENSE_VERSION}|{machine}".encode("utf-8")
    signature = key.sign(payload, padding.PKCS1v15(), hashes.SHA256())
    return _b64encode(payload) + "." + _b64encode(signature)


def verify_license(code: str) -> tuple[bool, str, dict]:
    try:
        if not _verify_pk_integrity():
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
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        pub = _get_pub_key()
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
        plain = json.dumps(
            {"code": code, "machine": info.get("machine")},
            ensure_ascii=False, indent=2,
        )
        encrypted = _license_fernet().encrypt(plain.encode("utf-8")).decode("ascii")
        mac = hmac.new(_license_hmac_key(), encrypted.encode("ascii"), hashlib.sha256).hexdigest()
        blob = json.dumps({"d": encrypted, "m": mac}, ensure_ascii=False)
        REG_FILE.write_text(blob, encoding="utf-8")
    except OSError:
        return False
    reset_trial()
    return True


def _read_license_data() -> dict | None:
    if not REG_FILE.exists():
        return None
    try:
        raw = REG_FILE.read_text(encoding="utf-8")
        blob = json.loads(raw)
    except (OSError, ValueError):
        return None
    if "d" in blob and "m" in blob:
        encrypted = blob["d"]
        expected_mac = hmac.new(
            _license_hmac_key(), encrypted.encode("ascii"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected_mac, blob["m"]):
            return None
        try:
            plain = _license_fernet().decrypt(encrypted.encode("ascii")).decode("utf-8")
            data = json.loads(plain)
        except Exception:
            return None
    else:
        data = blob
    return data


def current_registration() -> dict | None:
    data = _read_license_data()
    if not data:
        return None
    code = data.get("code", "")
    ok, msg, info = verify_license(code)
    if not ok or not _machine_matches(info):
        return None
    info["msg"] = msg
    return info


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


def _mc_hash_suffix() -> str:
    try:
        mc = machine_code()
    except RuntimeError:
        mc = "unknown"
    return hashlib.sha256(f"asr_shadow:{mc}".encode()).hexdigest()[:12]


def _trial_shadow_paths() -> list[Path]:
    home = Path.home()
    suffix = _mc_hash_suffix()
    if sys.platform == "win32":
        appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        localappdata = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        return [
            appdata / f"asr_cache_{suffix}" / "shadow.dat",
            localappdata / f"asr_data_{suffix}" / "cache.dat",
            localappdata / "Temp" / f"asr_{suffix}.dat",
            localappdata / f"Microsoft_{suffix}" / "clr.dat",
        ]
    elif sys.platform == "darwin":
        return [
            home / "Library" / "Caches" / f"com.apple.dt.{suffix}" / "shadow.dat",
            home / "Library" / "Preferences" / f"asr_{suffix}.plist",
            home / f".{suffix}_cache",
            home / "Library" / "Caches" / f"asr_{suffix}" / ".dat",
        ]
    else:
        return [
            home / ".cache" / f"asr_{suffix}.dat",
            home / ".config" / f"asr_{suffix}.conf",
            home / f".{suffix}_shadow",
            home / ".local" / "share" / f"asr_{suffix}" / ".dat",
        ]


def _trial_fernet():
    from cryptography.fernet import Fernet

    try:
        code = machine_code()
    except RuntimeError:
        code = "unknown"
    key = base64.urlsafe_b64encode(
        hashlib.sha256(f"asr_trial_fernet:{code}".encode()).digest()
    )
    return Fernet(key)


def _encrypt_trial(count: int) -> str:
    ts = int(time.time())
    payload = json.dumps({"c": count, "t": ts}, separators=(",", ":"))
    return _trial_fernet().encrypt(payload.encode("utf-8")).decode("ascii")


def _decrypt_trial(data: str) -> int:
    try:
        plain = _trial_fernet().decrypt(data.encode("ascii"))
        obj = json.loads(plain.decode("utf-8"))
        count = obj.get("c", 0)
        ts = obj.get("t", 0)
        now = int(time.time())
        if ts > now + 300:
            return TRIAL_MAX
        if now - ts > 365 * 24 * 3600:
            return TRIAL_MAX
        return count
    except Exception:
        try:
            plain = _trial_fernet().decrypt(data.encode("ascii"))
            return int(plain.decode("utf-8"))
        except Exception:
            return 0


def _mark_trial_used():
    data = {}
    if REG_FILE.exists():
        try:
            raw = REG_FILE.read_text(encoding="utf-8")
            blob = json.loads(raw)
            if "d" in blob and "m" in blob:
                encrypted = blob["d"]
                expected_mac = hmac.new(
                    _license_hmac_key(), encrypted.encode("ascii"), hashlib.sha256
                ).hexdigest()
                if hmac.compare_digest(expected_mac, blob["m"]):
                    plain = _license_fernet().decrypt(encrypted.encode("ascii")).decode("utf-8")
                    data = json.loads(plain)
                else:
                    data = {}
            else:
                data = blob
        except (OSError, ValueError):
            pass
    data["trial_used"] = True
    try:
        plain = json.dumps(data, ensure_ascii=False, indent=2)
        encrypted = _license_fernet().encrypt(plain.encode("utf-8")).decode("ascii")
        mac = hmac.new(_license_hmac_key(), encrypted.encode("ascii"), hashlib.sha256).hexdigest()
        blob = json.dumps({"d": encrypted, "m": mac}, ensure_ascii=False)
        REG_FILE.write_text(blob, encoding="utf-8")
    except OSError:
        pass


def _is_trial_marked() -> bool:
    data = _read_license_data()
    if data is None:
        return False
    return bool(data.get("trial_used"))


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
    data = _read_license_data()
    if data is not None:
        data.pop("trial_used", None)
        if data.get("code") or data.get("machine"):
            try:
                plain = json.dumps(data, ensure_ascii=False, indent=2)
                encrypted = _license_fernet().encrypt(plain.encode("utf-8")).decode("ascii")
                mac = hmac.new(
                    _license_hmac_key(), encrypted.encode("ascii"), hashlib.sha256
                ).hexdigest()
                blob = json.dumps({"d": encrypted, "m": mac}, ensure_ascii=False)
                REG_FILE.write_text(blob, encoding="utf-8")
            except OSError:
                pass
        else:
            try:
                REG_FILE.unlink()
            except OSError:
                pass
    elif REG_FILE.exists():
        try:
            REG_FILE.unlink()
        except OSError:
            pass


def is_registered() -> bool:
    return current_registration() is not None


def check_auth() -> bool:
    """多点授权检查：供核心业务函数调用，独立于 GUI 层检查。"""
    _check_debugger()
    if _debug_is_tainted():
        return False
    if not _verify_pk_integrity():
        return False
    return current_registration() is not None


def check_trial_or_registered() -> tuple[bool, str]:
    """综合检查：返回 (是否允许使用, 提示消息)。"""
    _check_debugger()
    if _debug_is_tainted():
        return False, "运行环境异常"
    if not _verify_pk_integrity():
        return False, "授权模块校验失败"
    if is_registered():
        return True, ""
    used = trial_count()
    if used < TRIAL_MAX:
        return True, ""
    return False, "试用次数已用完，请注册"