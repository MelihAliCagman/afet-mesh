"""STM32F407 kartına yükleme ve RAM tamponundan program çıktısını (log) okuma.

Kullanım (proje kökünden):
  python scripts/flash.py blink                 # firmware/build/blink.bin dosyasını yükler
  python scripts/flash.py selftest --log        # yükler, bekler, log tamponunu okuyup yazar
  python scripts/flash.py selftest --log-only   # yüklemeden yalnızca logu okur
  python scripts/flash.py --restore YEDEK.bin   # özgün yazılımı (yedekten) geri yükler
Not: Yazmadan önce kartın yedeği alınmış olmalıdır."""
import glob
import os
import re
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
BUILD = os.path.join(ROOT, "firmware", "build")


def find(pattern):
    hits = glob.glob(pattern, recursive=True)
    if not hits:
        sys.exit("bulunamadı: " + pattern)
    return hits[0]


CLI = None


def cli(*args):
    global CLI
    if CLI is None:
        CLI = find(r"C:\ST\STM32CubeIDE_*\STM32CubeIDE\plugins\com.st.stm32cube.ide.mcu.externaltools.cubeprogrammer*\tools\bin\STM32_Programmer_CLI.exe")
    r = subprocess.run([CLI, *args], capture_output=True, text=True, errors="replace")
    return r.returncode, r.stdout + r.stderr


def symbols(app):
    tools = find(r"C:\ST\STM32CubeIDE_*\STM32CubeIDE\plugins\com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32*\tools\bin")
    nm = subprocess.run([os.path.join(tools, "arm-none-eabi-nm.exe"), os.path.join(BUILD, app + ".elf")], capture_output=True, text=True).stdout
    return {m.group(2): int(m.group(1), 16) for m in re.finditer(r"^([0-9a-fA-F]{8}) [BbDd] (\w+)$", nm, re.M)}


def flash(binfile):
    code, out = cli("-c", "port=SWD", "mode=UR", "reset=HWrst", "-w", binfile, "0x08000000", "-v", "-hardRst")
    if code != 0 or "Download verified successfully" not in out:
        sys.exit("YÜKLEME BAŞARISIZ:\n" + out[-1500:])
    print("yüklendi ve doğrulandı:", os.path.basename(binfile))


def parse_mem(out):
    mem = {}
    for line in out.splitlines():
        m = re.match(r"\s*(0x[0-9A-Fa-f]{8})\s*:\s*((?:[0-9A-Fa-f]{2}\s*)+)$", line)
        if m:
            base = int(m.group(1), 16)
            for i, b in enumerate(m.group(2).split()):
                mem[base + i] = int(b, 16)
    return mem


def mem_bytes(mem, addr, size):
    try:
        return bytes(mem[addr + i] for i in range(size))
    except KeyError:
        sys.exit("okuma eksik (adres 0x%08X)" % addr)


def read_log(app, size=2048, end_marker="<BITTI>"):
    """Bağlanmak kartı yeniden başlatır; program tamamlanana kadar aynı oturumda önce bekletici bir flash okuması
    yapılır. Bitiş işareti görünmezse bekletme büyütülerek yeniden denenir."""
    sym = symbols(app)
    text = ""
    for repeats in (1, 3, 6, 12):
        delay = ["-r8", "0x08000000", "32768"] * repeats
        code, out = cli("-c", "port=SWD", *delay,
                        "-r8", hex(sym["log_head"]), "4", "-r8", hex(sym["log_buf"]), str(size))
        mem = parse_mem(out)
        try:
            head = int.from_bytes(mem_bytes(mem, sym["log_head"], 4), "little")
            buf = mem_bytes(mem, sym["log_buf"], size)
        except SystemExit:
            continue
        n = min(head, size)
        raw = buf[:n] if head <= size else buf[head % size:] + buf[: head % size]
        text = raw.decode("utf-8", errors="replace")
        if end_marker in text:
            break
    return text


def main():
    args = sys.argv[1:]
    if args[:1] == ["--restore"]:
        flash(args[1])
        return
    app = args[0]
    if "--log-only" not in args:
        flash(os.path.join(BUILD, app + ".bin"))
    if "--log" in args or "--log-only" in args:
        time.sleep(2.0)
        print(read_log(app))


if __name__ == "__main__":
    main()
