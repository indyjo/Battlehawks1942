#!/usr/bin/env python3
"""Disassemble a 68000 image to Motorola syntax that gas can round-trip.

m68k-atari-mintelf-objdump prints MIT syntax (movel %d0,%a0@). This rewrites
each instruction to the Motorola spelling this assembler accepts
(move.l d0,(a0)) under --register-prefix-optional. Instructions it cannot
prove, including 68020 forms decoded out of data, are emitted as .word so
the assembled bytes still match the original.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

AS = Path.home() / "opt/cross-mint/bin/m68k-atari-mintelf-as"
OBJDUMP = Path.home() / "opt/cross-mint/bin/m68k-atari-mintelf-objdump"
OBJCOPY = Path.home() / "opt/cross-mint/bin/m68k-atari-mintelf-objcopy"

BRANCHES = {
    "bra", "bsr", "beq", "bne", "bcc", "bcs", "bpl", "bmi", "bge", "bgt",
    "ble", "blt", "bhi", "bls", "bvc", "bvs",
}
NO_SIZE = {
    "moveq", "rts", "rte", "rtr", "nop", "unlk", "swap", "reset", "stop",
    "trap", "illegal", "dbf", "dbt", "dbra", "dbhi", "dbls", "dbcc", "dbcs",
    "dbne", "dbeq", "dbvc", "dbvs", "dbpl", "dbmi", "dbge", "dblt", "dbgt",
    "dble",
}
REJECT_PREFIX = ("cp", "f", "p", "mv", "bf", "call", "rtm", "cin", "cpush", "pack", "unpk")

ADDR_RE = re.compile(r"^\s*([0-9a-f]+):$")
ATOM_PC_IDX = re.compile(
    r"%pc@\((0x[0-9a-f]+),(%(?:[ad][0-7]|sp|fp)):([wl])\)$"
)
ATOM_PC = re.compile(r"%pc@\((0x[0-9a-f]+)\)$")
ATOM_IDX = re.compile(
    r"(%(?:[ad][0-7]|sp|fp))@\(([0-9a-f]+),(%(?:[ad][0-7]|sp|fp)):([wl])\)$"
)
ATOM_D16 = re.compile(r"(%(?:[ad][0-7]|sp|fp))@\((-?\d+)\)$")
ATOM_POST = re.compile(r"(%(?:[ad][0-7]|sp|fp))@\+$")
ATOM_PRE = re.compile(r"(%(?:[ad][0-7]|sp|fp))@-$")
ATOM_IND = re.compile(r"(%(?:[ad][0-7]|sp|fp))@$")
REG = re.compile(r"%([ad][0-7]|sp|fp|pc|ccr|sr|usp)")


@dataclass
class Insn:
    addr: int
    words: list[int]
    text: str | None  # Motorola body, or None to emit .word
    raw_mnemonic: str


def regname(token: str) -> str:
    return token[1:]


def parse_idx_disp(text: str) -> int:
    """Indexed displacements are an 8-bit field printed in hex.

    Short values omit the leading zero (`a` means 10). Values above 127 are
    negative. A long string is a sign-extended print of that same byte.
    """
    value = int(text, 16)
    if len(text) > 2:
        bits = len(text) * 4
        if value >= 1 << (bits - 1):
            value -= 1 << bits
        value &= 0xFF
    if value >= 128:
        value -= 256
    return value


def split_args(operand: str) -> list[str]:
    args: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in operand:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            args.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        args.append("".join(buf).strip())
    return args


def split_mnemonic(mnemonic: str) -> tuple[str, str] | None:
    if mnemonic in NO_SIZE or mnemonic.startswith("db"):
        return mnemonic, ""
    if mnemonic[:-1] in BRANCHES and mnemonic[-1] in "sw":
        size = ".s" if mnemonic[-1] == "s" else ".w"
        return mnemonic[:-1], size
    if len(mnemonic) > 1 and mnemonic[-1] in "bwl":
        return mnemonic[:-1], "." + mnemonic[-1]
    return mnemonic, ""


# Objdump will happily decode data as 68020/ColdFire opcodes. gas -m68000
# rejects those, so they stay .word instead of being offered as source.
NOT_68000 = {
    "chk2", "cmp2", "cas", "cas2", "pack", "unpk", "rtm", "callm", "mov3q",
    "mvs", "mvz", "bitrev", "byterev", "ff1", "movec", "moves", "cinv",
    "cpush", "intouch", "frestore", "fsave", "psave", "prestore",
}


def reject_mnemonic(mnemonic: str) -> bool:
    if mnemonic in {".short", ".word", ".long"}:
        return True
    if mnemonic.startswith(REJECT_PREFIX):
        return True
    base = mnemonic[:-1] if mnemonic[-1:] in "bwlqs" else mnemonic
    if base in NOT_68000 or mnemonic in NOT_68000:
        return True
    if mnemonic in {"chkl", "bral", "bsrl", "linkl"}:
        return True
    return False


def convert_atom(atom: str, starts: set[int]) -> str | None:
    if ":w:" in atom or ":l:" in atom or ")@(" in atom or "@(" in atom and ")@(" in atom:
        return None
    if re.search(r":[wl]:\d", atom):
        return None
    match = ATOM_PC_IDX.fullmatch(atom)
    if match:
        target = int(match.group(1), 16)
        if target not in starts:
            return None
        return f"L{target:x}(pc,{regname(match.group(2))}.{match.group(3)})"
    match = ATOM_PC.fullmatch(atom)
    if match:
        target = int(match.group(1), 16)
        if target not in starts and target != max(starts, default=-1) + 1:
            return None
        return f"L{target:x}(pc)"
    match = ATOM_IDX.fullmatch(atom)
    if match:
        disp = parse_idx_disp(match.group(2))
        return f"{disp}({regname(match.group(1))},{regname(match.group(3))}.{match.group(4)})"
    match = ATOM_D16.fullmatch(atom)
    if match:
        return f"{int(match.group(2))}({regname(match.group(1))})"
    match = ATOM_POST.fullmatch(atom)
    if match:
        return f"({regname(match.group(1))})+"
    match = ATOM_PRE.fullmatch(atom)
    if match:
        return f"-({regname(match.group(1))})"
    match = ATOM_IND.fullmatch(atom)
    if match:
        return f"({regname(match.group(1))})"
    if atom.startswith("#"):
        body = atom[1:]
        if body.startswith("0x") or body.startswith("-0x"):
            return f"#{int(body, 16)}"
        return f"#{body}"
    if REG.fullmatch(atom):
        return regname(atom)
    if re.fullmatch(r"(?:%(?:[ad][0-7]|sp|fp))(?:-(?:%(?:[ad][0-7]|sp|fp)))?(?:/(?:%(?:[ad][0-7]|sp|fp))(?:-(?:%(?:[ad][0-7]|sp|fp)))?)*", atom):
        return REG.sub(lambda m: m.group(1), atom)
    return None


def convert(mnemonic: str, operand: str | None, words: list[int], starts: set[int]) -> str | None:
    if reject_mnemonic(mnemonic):
        return None
    parts = split_mnemonic(mnemonic)
    if parts is None:
        return None
    base, size = parts
    if operand is None:
        return f"{base}{size}"
    if base in BRANCHES:
        target = operand.strip()
        if not target.startswith("0x"):
            return None
        addr = int(target, 16)
        if addr not in starts:
            return None
        return f"{base}{size} L{addr:x}"
    rendered: list[str] = []
    for atom in split_args(operand):
        if base.startswith("db") and atom.startswith("0x"):
            addr = int(atom, 16)
            if addr not in starts:
                return None
            rendered.append(f"L{addr:x}")
            continue
        if base in {"jmp", "jsr", "pea"} and re.fullmatch(r"0x[0-9a-f]+", atom):
            value = int(atom, 16)
            if len(words) == 2:
                rendered.append(f"{value}.w")
            elif len(words) == 3:
                rendered.append(f"{value}.l")
            else:
                return None
            continue
        piece = convert_atom(atom, starts)
        if piece is None:
            return None
        rendered.append(piece)
    return f"{base}{size} " + ",".join(rendered)


def parse_objdump(listing: str, blob: bytes) -> list[Insn]:
    found: list[Insn] = []
    for line in listing.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        match = ADDR_RE.match(parts[0])
        if not match:
            continue
        hex_words = parts[1].split()
        if not hex_words or any(len(item) != 4 for item in hex_words):
            continue
        text = parts[2].strip() if len(parts) > 2 else ""
        mnemonic, _, operand = text.partition(" ")
        operand = operand or None
        addr = int(match.group(1), 16)
        words = [int(item, 16) for item in hex_words]
        found.append(Insn(addr, words, None, mnemonic))
        setattr(found[-1], "operand", operand)
    if not found:
        raise SystemExit("objdump produced no instructions")
    # Cover bytes objdump did not emit.
    covered = []
    cursor = 0
    for insn in found:
        if insn.addr < cursor:
            raise SystemExit(f"overlapping instruction at {insn.addr:#x}")
        while cursor < insn.addr:
            covered.append(Insn(cursor, [int.from_bytes(blob[cursor:cursor + 2], "big")], None, ""))
            cursor += 2
        length = len(insn.words) * 2
        if insn.addr + length > len(blob):
            raise SystemExit(f"instruction overruns image at {insn.addr:#x}")
        covered.append(insn)
        cursor = insn.addr + length
    while cursor + 1 < len(blob):
        covered.append(Insn(cursor, [int.from_bytes(blob[cursor:cursor + 2], "big")], None, ""))
        cursor += 2
    if cursor != len(blob):
        raise SystemExit(f"image length {len(blob)} is odd or uncovered at {cursor:#x}")
    starts = {insn.addr for insn in covered}
    starts.add(len(blob))
    for insn in covered:
        operand = getattr(insn, "operand", None)
        if insn.raw_mnemonic:
            rendered = convert(insn.raw_mnemonic, operand, insn.words, starts)
            if rendered and gas_would_shrink(rendered, len(insn.words)):
                insn.comment = rendered
                insn.text = None
            else:
                insn.text = rendered
        else:
            insn.text = None
    return covered


def render(insns: list[Insn], title: str) -> str:
    targets = set()
    for insn in insns:
        if insn.text and " L" in f" {insn.text}":
            for match in re.finditer(r"\bL([0-9a-f]+)\b", insn.text):
                targets.add(int(match.group(1), 16))
    lines = [
        f"* {title}",
        "* Motorola syntax for m68k-atari-mintelf-as -m68000 --register-prefix-optional.",
        "* Words that are data, or 68020 forms objdump invented, stay .word.",
        "* .org keeps each instruction at its original address.",
        "        .text",
    ]
    # source line -> instruction that should be rewritten if gas rejects the line
    line_to_addr: dict[int, int] = {}
    previous: int | None = None
    for insn in insns:
        org_line = len(lines) + 1
        lines.append(f"        .org 0x{insn.addr:x}")
        if previous is not None:
            # A backwards .org means the previous instruction encoded too long.
            line_to_addr[org_line] = previous
        if insn.addr in targets:
            lines.append(f"L{insn.addr:x}:")
        comment = getattr(insn, "comment", None)
        if comment:
            lines.append(f"* {comment}")
        body_line = len(lines) + 1
        line_to_addr[body_line] = insn.addr
        if insn.text:
            lines.append(f"        {insn.text}")
        else:
            for word in insn.words:
                lines.append(f"        .word 0x{word:04x}")
                line_to_addr[len(lines)] = insn.addr
        previous = insn.addr
    if len(insns) and (insns[-1].addr + len(insns[-1].words) * 2) in targets:
        end = insns[-1].addr + len(insns[-1].words) * 2
        lines.append(f"L{end:x}:")
    return "\n".join(lines) + "\n", line_to_addr


def objdump_blob(blob: bytes, work: Path) -> str:
    work.parent.mkdir(parents=True, exist_ok=True)
    bin_path = work.with_suffix(".bin")
    bin_path.write_bytes(blob)
    run = subprocess.run(
        [str(OBJDUMP), "-b", "binary", "-m", "m68k", "--disassemble-zeroes", "-D", str(bin_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return run.stdout


def assemble(src: Path, work: Path) -> tuple[bytes | None, str]:
    obj = work.with_suffix(".o")
    out = work.with_suffix(".out")
    proc = subprocess.run(
        [str(AS), "-m68000", "--register-prefix-optional", "-o", str(obj), str(src)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None, proc.stderr
    subprocess.run(
        [str(OBJCOPY), "-O", "binary", "-j", ".text", str(obj), str(out)],
        check=True,
        capture_output=True,
    )
    return out.read_bytes(), ""


def gas_would_shrink(text: str, nwords: int) -> bool:
    """Forms this gas encodes with a shorter opcode than the one objdump saw."""
    match = re.fullmatch(r"move\.l #(-?\d+),d[0-7]", text)
    if match and nwords == 3 and -128 <= int(match.group(1)) <= 127:
        return True
    if re.match(r"(?:add|sub)\.[bwl] #([1-8]),", text):
        return True
    if nwords == 2 and re.fullmatch(r"lea 0\([a-z0-9]+\),[a-z0-9]+", text):
        return True
    return False


def force_words(insn: Insn) -> None:
    if insn.text and not getattr(insn, "comment", None):
        insn.comment = insn.text
    insn.text = None


def addresses_on_lines(stderr: str, line_to_addr: dict[int, int]) -> set[int]:
    bad_lines = {int(match) for match in re.findall(r":(\d+):", stderr)}
    return {line_to_addr[line] for line in bad_lines if line in line_to_addr}


def drop_bad_encodings(insns: list[Insn], work: Path) -> int:
    """Assemble address-independent instructions once and drop the ones gas
    encodes differently from the original words. PC-relative forms are left
    for the real assembly, where their labels have the right addresses.
    """
    chosen = [
        insn for insn in insns
        if insn.text and not re.search(r"\bL[0-9a-f]+\b", insn.text)
    ]
    if not chosen:
        return 0
    lines = ["        .text"]
    for index, insn in enumerate(chosen):
        lines.append("        .word 0xa55a")
        lines.append(f"        .word 0x{index:04x}")
        lines.append(f"        {insn.text}")
    probe_src = work.with_suffix(".probe.s")
    probe_src.write_text("\n".join(lines) + "\n")
    produced, errors = assemble(probe_src, work.with_suffix(".probe"))
    if produced is None:
        bad_lines = {int(match) for match in re.findall(r":(\d+):", errors)}
        dropped = 0
        for index, insn in enumerate(chosen):
            # .text is line 1; each instruction occupies the third line of a triple.
            if 4 + index * 3 in bad_lines:
                force_words(insn)
                dropped += 1
        return dropped
    dropped = 0
    pos = 0
    for index, insn in enumerate(chosen):
        if produced[pos:pos + 2] != b"\xa5\x5a":
            break
        if int.from_bytes(produced[pos + 2:pos + 4], "big") != index:
            break
        pos += 4
        expect = b"".join(word.to_bytes(2, "big") for word in insn.words)
        got = produced[pos:pos + len(expect)]
        # The probe stops at the next marker. If gas emitted a different
        # length, the marker check on the next item fails and we drop this one.
        nxt = pos + len(expect)
        marker_ok = nxt == len(produced) or produced[nxt:nxt + 2] == b"\xa5\x5a"
        if got != expect or not marker_ok:
            force_words(insn)
            dropped += 1
            if not marker_ok:
                break
        pos += len(expect)
    return dropped


def disassemble_file(blob: bytes, src: Path, title: str, work: Path) -> None:
    listing = objdump_blob(blob, work)
    insns = parse_objdump(listing, blob)
    for _ in range(40):
        drop_bad_encodings(insns, work)
        text, line_to_addr = render(insns, title)
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text(text)
        produced, errors = assemble(src, work)
        if produced is None:
            bad = addresses_on_lines(errors, line_to_addr)
            if not bad:
                raise SystemExit(errors)
            for insn in insns:
                if insn.addr in bad:
                    force_words(insn)
            continue
        if produced == blob:
            words = sum(1 for insn in insns if insn.text is None)
            print(f"{src} ok  insns {len(insns)}  raw {words}")
            return
        changed = 0
        for insn in insns:
            if insn.text is None:
                continue
            end = insn.addr + len(insn.words) * 2
            if end > len(produced) or produced[insn.addr:end] != blob[insn.addr:end]:
                force_words(insn)
                changed += 1
        if changed == 0:
            raise SystemExit(
                f"bytes differ for {src}: produced {len(produced)} original {len(blob)}"
            )
    leftover = sum(1 for insn in insns if insn.text is not None)
    raise SystemExit(f"failed to round-trip {src} with {leftover} instructions still in text")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("binary", type=Path)
    ap.add_argument("src", type=Path)
    ap.add_argument("--title", default="68000")
    ap.add_argument("--work", type=Path, default=Path("build/disasm"))
    args = ap.parse_args()
    disassemble_file(args.binary.read_bytes(), args.src, args.title, args.work)
    sys.exit(0)


if __name__ == "__main__":
    main()
