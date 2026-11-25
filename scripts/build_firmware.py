"""STM32F407 yazılımını derler (STM32CubeIDE'nin arm-none-eabi araç zinciriyle).

Kullanım (proje kökünden):  python scripts/build_firmware.py blink
Çıktı: firmware/build/<uygulama>.elf, .bin, .map
"""
import glob
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
BOARD = os.path.join(ROOT, "firmware", "drivers", "f407disc")
BUILD = os.path.join(ROOT, "firmware", "build")
CPU = ["-mcpu=cortex-m4", "-mthumb", "-mfpu=fpv4-sp-d16", "-mfloat-abi=hard"]


def find_toolchain():
    hits = glob.glob(r"C:\ST\STM32CubeIDE_*\STM32CubeIDE\plugins\com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32*\tools\bin")
    if not hits:
        sys.exit("arm-none-eabi-gcc bulunamadı (STM32CubeIDE kurulu mu?)")
    return hits[0]


def main():
    if len(sys.argv) < 2:
        sys.exit("kullanım: python scripts/build_firmware.py <uygulama> [--core]")
    app = sys.argv[1]
    use_core = "--core" in sys.argv
    app_dir = os.path.join(ROOT, "firmware", "apps", app)
    sources = sorted(glob.glob(os.path.join(BOARD, "*.c"))) + sorted(glob.glob(os.path.join(app_dir, "*.c")))
    includes = [BOARD, app_dir]
    if use_core:
        core = os.path.join(ROOT, "firmware", "core")
        sources += [s for s in sorted(glob.glob(os.path.join(core, "*.c"))) if not s.endswith("host_api.c")]
        includes.append(core)
    tools = find_toolchain()
    env = dict(os.environ)
    env["PATH"] = tools + os.pathsep + env.get("PATH", "")
    os.makedirs(BUILD, exist_ok=True)
    elf = os.path.join(BUILD, app + ".elf")
    cmd = [os.path.join(tools, "arm-none-eabi-gcc.exe"), *CPU, "-Os", "-g", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
           "-ffunction-sections", "-fdata-sections", *[f"-I{i}" for i in includes], "-T", os.path.join(BOARD, "link.ld"),
           "-Wl,--gc-sections", f"-Wl,-Map={os.path.join(BUILD, app + '.map')}", "--specs=nano.specs", "--specs=nosys.specs",
           "-nostartfiles", "-o", elf, *sources, "-lm"]
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode:
        sys.exit("DERLEME HATASI:\n" + r.stdout + r.stderr)
    subprocess.run([os.path.join(tools, "arm-none-eabi-objcopy.exe"), "-O", "binary", elf, os.path.join(BUILD, app + ".bin")], check=True, env=env)
    print(subprocess.run([os.path.join(tools, "arm-none-eabi-size.exe"), elf], capture_output=True, text=True, env=env).stdout)
    print("hazır:", os.path.join(BUILD, app + ".bin"))


if __name__ == "__main__":
    main()
