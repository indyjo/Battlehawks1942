# Motorola syntax, GNU only. Run from the repository root.
# python3 tools/prepare_workspace.py extract, disassemble, and install every patch
# make check                         byte-match the original code (flags off)
# make prg                           assemble the patched sources and splice BH.PRG
# make AMIGA_PALETTE=1 prg           define AMIGA_PALETTE for that assembly
# make C2P_TIMING=1 prg              define C2P_TIMING for that assembly
# make ST_C2P_MOVEP=1 prg            lookup-table movep converter
# make prg HATARI_BH=/path/to/dir    also copy BH.PRG into that directory
AS      := $(HOME)/opt/cross-mint/bin/m68k-atari-mintelf-as
OBJCOPY := $(HOME)/opt/cross-mint/bin/m68k-atari-mintelf-objcopy
ASFLAGS := -m68000 --register-prefix-optional
STBUILD := build/st
PRGFLAGS :=
ifdef AMIGA_PALETTE
PRGFLAGS += --amiga-palette
STBUILD := build/st-amiga
endif
ifdef C2P_TIMING
PRGFLAGS += --c2p-timing
ifeq ($(STBUILD),build/st)
STBUILD := build/st-c2p
else
STBUILD := build/st-amiga-c2p
endif
endif
ifdef ST_C2P_MOVEP
PRGFLAGS += --c2p-movep
ifeq ($(STBUILD),build/st)
STBUILD := build/st-movep
else
STBUILD := $(STBUILD)-movep
endif
endif

CODE_SRCS := \
	src/amiga/bh_code.s \
	src/amiga/flt_code.s \
	src/amiga/type_hunk0.s \
	src/amiga/type_hunk1.s \
	src/st/bh_text.s

CODE_BINS := $(patsubst src/%.s,build/%.bin,$(CODE_SRCS))

.PHONY: check code prg prepare clean

check: code
	cmp build/amiga/bh_code.bin extracted/amiga/hunks/bh/hunk0.code.bin
	cmp build/amiga/flt_code.bin extracted/amiga/hunks/flt/hunk0.code.bin
	cmp build/amiga/type_hunk0.bin extracted/amiga/hunks/type/hunk0.code.bin
	cmp build/amiga/type_hunk1.bin extracted/amiga/hunks/type/hunk1.code.bin
	cmp build/st/bh_text.bin extracted/st/hunks/bh/text.bin

code: $(CODE_BINS)

build/%.o: src/%.s
	mkdir -p $(dir $@)
	$(AS) $(ASFLAGS) -o $@ $<

build/%.bin: build/%.o
	$(OBJCOPY) -O binary -j .text $< $@

build/st/bh_data.o: src/st/bh_data.s
	mkdir -p $(dir $@)
	$(AS) $(ASFLAGS) -o $@ $<

build/st/bh_data.bin: build/st/bh_data.o
	$(OBJCOPY) -O binary -j .data $< $@

# The stager assembles the already-patched sources. Flags only define symbols.
$(STBUILD)/BH.PRG: src/st/bh_text.s src/st/bh_data.s src/st/c2p_timing.s src/st/c2p_movep.s src/st/amiga_palette.s tools/stage_st_deploy.py tools/splice_prg.py extracted/st/disk1/files/BH.PRG
	python3 tools/stage_st_deploy.py $(PRGFLAGS) --prg-out $@

prepare:
	python3 tools/prepare_workspace.py

prg: $(STBUILD)/BH.PRG
ifdef HATARI_BH
	cp $(STBUILD)/BH.PRG $(HATARI_BH)/BH.PRG
endif

clean:
	rm -rf build
