import ctypes as C
import glob
import os
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.join(HERE, "..", "core")
BUILD = os.path.join(HERE, "build")


def find_gcc():
    return shutil.which("gcc") or next(iter(glob.glob(r"C:\msys64\ucrt64\bin\gcc.exe")), None)


@pytest.fixture(scope="session")
def lib():
    gcc = find_gcc()
    if not gcc:
        pytest.skip("gcc bulunamadı")
    os.makedirs(BUILD, exist_ok=True)
    out = os.path.join(BUILD, "libafet.dll" if os.name == "nt" else "libafet.so")
    sources = sorted(glob.glob(os.path.join(CORE, "*.c")))
    cmd = [gcc, "-shared", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-I", CORE, "-o", out, *sources, "-lm"]
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(gcc) + os.pathsep + env.get("PATH", "")  # MinGW'nin kendi DLL'leri önce bulunsun
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    return C.CDLL(out)
