import glob
import os
import subprocess

import pytest

CORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core")
SOURCES = ["wire", "aes128", "ccm", "security", "routing", "lora_time", "node"]


def find_arm_gcc():
    hits = glob.glob(r"C:\ST\STM32CubeIDE_*\STM32CubeIDE\plugins\com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32*\tools\bin\arm-none-eabi-gcc.exe")
    return hits[0] if hits else None


def test_core_compiles_for_cortex_m4_without_warnings(tmp_path):
    gcc = find_arm_gcc()
    if not gcc:
        pytest.skip("arm-none-eabi-gcc (STM32CubeIDE) bulunamadı")
    flags = ["-c", "-std=c11", "-Os", "-mcpu=cortex-m4", "-mthumb", "-mfpu=fpv4-sp-d16", "-mfloat-abi=hard",
             "-ffunction-sections", "-fdata-sections", "-Wall", "-Wextra", "-Werror", "-I", CORE]
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(gcc) + os.pathsep + env.get("PATH", "")
    total = 0
    for name in SOURCES:
        out = str(tmp_path / (name + ".o"))
        r = subprocess.run([gcc, *flags, os.path.join(CORE, name + ".c"), "-o", out], capture_output=True, text=True, env=env)
        assert r.returncode == 0, name + ": " + r.stderr
        total += os.path.getsize(out)
    assert total > 0
