# Code Comparison: RISCY-V02 vs 6502

Side-by-side assembly for common routines. All cycle counts assume same-page branches. The 6502 uses zero-page pointers; RISCY-V02 uses register arguments.

## memcpy

```c
void memcpy(void *dst, const void *src, size_t n);
```

**6502** — arguments in zero page: src ($00), dst ($02), count ($04). Based on [cc65](https://github.com/cc65/cc65)'s `memcpy.s` (Ullrich von Bassewitz; 2× unroll by Christian Krueger).

```
memcpy:
    LDY #0              ;  2 cy   2 B
    LDX count+1         ;  3 cy   2 B    ; full pages
    BEQ partial         ;  2 cy   2 B
page:
    LDA (src),Y         ;  5 cy   2 B
    STA (dst),Y         ;  6 cy   2 B
    INY                 ;  2 cy   1 B
    LDA (src),Y         ;  5 cy   2 B
    STA (dst),Y         ;  6 cy   2 B
    INY                 ;  2 cy   1 B
    BNE page            ;  3 cy   2 B
    INC src+1           ;  5 cy   2 B    ; next page
    INC dst+1           ;  5 cy   2 B
    DEX                 ;  2 cy   1 B
    BNE page            ;  3 cy   2 B
partial:
    LDX count           ;  3 cy   2 B    ; remaining bytes
    BEQ done            ;  2 cy   2 B
tail:
    LDA (src),Y         ;  5 cy   2 B
    STA (dst),Y         ;  6 cy   2 B
    INY                 ;  2 cy   1 B
    DEX                 ;  2 cy   1 B
    BNE tail            ;  3 cy   2 B
done:
    RTS                 ;  6 cy   1 B
```

Inner loop (full pages, 2× unrolled): 2×(`LDA` + `STA` + `INY`) + `BNE` = **14.5 cy/byte**, 12 B

Page boundary: `INC` + `INC` + `DEX` + `BNE` = 15 cy / 256 bytes (0.06 cy/byte amortized)

Tail loop (partial page): adds `DEX` for count = **18 cy/byte**, 8 B

Total code: **38 bytes**

**RISCY-V02** — arguments in registers: R2 = dst, R3 = src, R4 = count

```
memcpy:
    LI   R1, 1          ;  2 cy   2 B    ; mask
    AND  R1, R4, R1     ;  2 cy   2 B    ; R1 = odd flag
    SRLI R4, 1          ;  2 cy   2 B    ; R4 = word count
    BZ   R4, tail       ;  2 cy   2 B
words:
    LWR  R5, R3         ;  4 cy   2 B
    SWR  R5, R2         ;  4 cy   2 B
    ADDI R3, 2          ;  2 cy   2 B
    ADDI R2, 2          ;  2 cy   2 B
    ADDI R4, -1         ;  2 cy   2 B
    BNZ  R4, words      ;  3 cy   2 B
tail:
    BZ   R1, done       ;  2 cy   2 B
    LBUR R5, R3         ;  3 cy   2 B
    SBR  R5, R2         ;  3 cy   2 B
done:
    JR   R6, 0          ;  3 cy   2 B
```

Word loop: `LWR` + `SWR` + 3×`ADDI` + `BNZ` = 17 cy / 2 bytes = **8.5 cy/byte**, 12 B

Tail: single `LBUR` + `SBR` for the trailing odd byte (if any). No page handling needed.

Total code: **28 bytes**

| | 6502 | RISCY-V02 |
|---|---|---|
| Inner loop | 14.5 cy/byte | 8.5 cy/byte |
| Boundary overhead | 15 cy / 256 B | none |
| Tail | 18 cy/byte | 6 cy (1 byte) |
| Code size | 38 B | 28 B |

cc65 unrolls 2× in the full-page loop, amortizing the branch over two bytes. Despite this optimization, RISCY-V02's word loads/stores still copy at 59% of the cycle cost — the architectural advantage (16-bit data path, no page boundaries) dominates the loop-unrolling trick. The 6502 pays 10 extra bytes for the unroll and page-crossing logic.

## strcpy

```c
char *strcpy(char *dst, const char *src);
```

**6502** — arguments in zero page: src ($00), dst ($02). Matches [cc65](https://github.com/cc65/cc65)'s `strcpy.s` (Ullrich von Bassewitz).

```
strcpy:
    LDY #0              ;  2 cy   2 B
loop:
    LDA (src),Y         ;  5 cy   2 B
    STA (dst),Y         ;  6 cy   2 B
    BEQ done            ;  2 cy   2 B
    INY                 ;  2 cy   1 B
    BNE loop            ;  3 cy   2 B
    INC src+1           ;  5 cy   2 B    ; page crossing
    INC dst+1           ;  5 cy   2 B
    BRA loop            ;  3 cy   2 B
done:
    RTS                 ;  6 cy   1 B
```

Inner loop: `LDA` + `STA` + `BEQ` + `INY` + `BNE` = **18 cy/char**, 9 B

Page crossing: `INC` + `INC` + `BRA` = 13 cy / 256 chars (0.05 cy/char amortized)

Total code: **18 bytes**

**RISCY-V02** — arguments in registers: R2 = dst, R3 = src

```
strcpy:
    LBUR R5, R3         ;  3 cy   2 B
    SBR  R5, R2         ;  3 cy   2 B
    ADDI R3, 1          ;  2 cy   2 B
    ADDI R2, 1          ;  2 cy   2 B
    BNZ  R5, strcpy     ;  3 cy   2 B
    JR   R6, 0          ;  3 cy   2 B
```

Inner loop: `LBUR` + `SBR` + 2×`ADDI` + `BNZ` = **13 cy/char**, 10 B. No page handling.

Total code: **12 bytes**

| | 6502 | RISCY-V02 |
|---|---|---|
| Inner loop | 18 cy/char | 13 cy/char |
| Page overhead | 13 cy / 256 chars | none |
| Code size | 18 B | 12 B |

Both versions store-then-test for the null terminator. The 6502 needs a separate `BEQ` (2 cycles) every character plus page-crossing logic; RISCY-V02 folds termination into the back-edge branch. The 6502's page-crossing code (6 bytes) wipes out its density advantage.

Word-copy variant (RISCY-V02 only, R7 = 0x00FF preloaded):

```
strcpy:
    LWR  R5, R3         ;  4 cy   2 B    ; load 2 chars
    AND  R1, R5, R7     ;  2 cy   2 B    ; R1 = low byte
    BZ   R1, lo         ;  2 cy   2 B
    SUB  R1, R5, R1     ;  2 cy   2 B    ; R1 = high byte << 8
    BZ   R1, hi         ;  2 cy   2 B
    SWR  R5, R2         ;  4 cy   2 B    ; store 2 chars
    ADDI R3, 2          ;  2 cy   2 B
    ADDI R2, 2          ;  2 cy   2 B
    J    strcpy         ;  3 cy   2 B
lo: SBR  R5, R2         ;  3 cy   2 B    ; store null
    JR   R6, 0          ;  3 cy   2 B
hi: SWR  R5, R2         ;  4 cy   2 B    ; store char + null
    JR   R6, 0          ;  3 cy   2 B
```

Word loop: 23 cy / 2 chars = **11.5 cy/char**, 26 B. The null-byte detection (8 cy) eats most of the word-load savings — unlike memcpy, strcpy's per-element null check limits the benefit.

## 16×16 → 16 Multiply

```c
uint16_t mul(uint16_t a, uint16_t b);
```

The 6502 uses cc65's right-shift algorithm: shift the multiplier right, conditionally add the multiplicand to an accumulator, then right-shift the entire 32-bit result. The accumulator and multiplier share a single shift chain, so only one set of shifts is needed per iteration. RISCY-V02 uses a left-shift variant with early exit, which is more natural when 16-bit operations are single instructions.

**6502** — arguments in zero page: mult ($00), mcand ($02), tmp ($04). Based on [cc65](https://github.com/cc65/cc65)'s `umul16x16r32.s` (Ullrich von Bassewitz). Result low 16 bits replace mult.

```
multiply:
    LDA #0              ;  2 cy   2 B    ; A = accumulator low
    STA tmp             ;  3 cy   2 B    ; tmp = accumulator high
    LDY #16             ;  2 cy   2 B    ; bit counter
    LSR mult+1          ;  5 cy   2 B    ; get first bit into carry
    ROR mult            ;  5 cy   2 B
loop:
    BCC no_add          ;  3 cy   2 B    (taken, 2 cy not taken)
    CLC                 ;  2 cy   1 B    ; accumulator += mcand
    ADC mcand           ;  3 cy   2 B
    TAX                 ;  2 cy   1 B
    LDA mcand+1         ;  3 cy   2 B
    ADC tmp             ;  3 cy   2 B
    STA tmp             ;  3 cy   2 B
    TXA                 ;  2 cy   1 B
no_add:
    ROR tmp             ;  5 cy   2 B    ; shift 32-bit result right
    ROR A               ;  2 cy   1 B
    ROR mult+1          ;  5 cy   2 B
    ROR mult            ;  5 cy   2 B
    DEY                 ;  2 cy   1 B
    BNE loop            ;  3 cy   2 B
    RTS                 ;  6 cy   1 B
```

Per iteration (no add): **25 cy** — `BCC`(taken)+4×`ROR`+`DEY`+`BNE`

Per iteration (add): **42 cy** — adds `CLC`+`ADC`+`TAX`+`LDA`+`ADC`+`STA`+`TXA`

Average: **33.5 cy/iter**. Total code: **34 bytes**

**RISCY-V02** — arguments in registers: R2 = multiplier, R3 = multiplicand, result in R4

```
multiply:
    LI   R4, 0          ;  2 cy   2 B
    LI   R1, 1          ;  2 cy   2 B    ; constant mask
loop:
    BZ   R2, done       ;  2 cy   2 B    ; early exit
    AND  R0, R2, R1     ;  2 cy   2 B    ; R0 = bit 0
    SRLI R2, 1          ;  2 cy   2 B    ; multiplier >>= 1
    BZ   R0, no_add     ;  2.5 cy 2 B
    ADD  R4, R4, R3     ;  2 cy   2 B    ; result += mcand
no_add:
    SLLI R3, 1          ;  2 cy   2 B    ; mcand <<= 1
    J    loop           ;  3 cy   2 B
done:
    JR   R6, 0          ;  3 cy   2 B
```

Per iteration (no add): **14 cy** — `BZ`+`AND`+`SRLI`+`BZ`(taken)+`SLLI`+`J`

Per iteration (add): **15 cy** — adds `ADD`

Average: **14.5 cy/iter**. Total code: **20 bytes**

| | 6502 | RISCY-V02 |
|---|---|---|
| Per iteration (avg) | 33.5 cy | 14.5 cy |
| 16 iterations (avg) | ~536 cy | ~232 cy |
| Code size | 34 B | 20 B |

cc65's right-shift algorithm is optimal for 8-bit CPUs — the accumulator and multiplier share a single 32-bit shift chain (4 RORs), eliminating the separate multiplicand shift. No early-exit test is needed because the multiplier shift is folded into the result shift. RISCY-V02 is still 2.3× faster: 16-bit add, shift, and branch-on-zero each replace multi-instruction 6502 sequences, and the left-shift variant with early exit is natural when those operations are cheap.

## 16 ÷ 16 Unsigned Division

```c
uint16_t udiv16(uint16_t dividend, uint16_t divisor);
// Returns quotient; remainder available as a byproduct.
```

Both implementations use binary long division (restoring): shift the dividend left one bit at a time into a running remainder, trial-subtract the divisor, and shift the success/fail bit into the quotient.

**6502** — arguments in zero page: dividend ($00), divisor ($02), rem ($04). Based on [cc65](https://github.com/cc65/cc65)'s `udiv.s` (Ullrich von Bassewitz). Quotient replaces dividend; remainder in rem. cc65 also has a 16÷8 fast path (not shown) that halves cycle count when the divisor fits in one byte.

```
udiv16:
    LDA #0              ;  2 cy   2 B    ; A = remainder low
    STA rem+1           ;  3 cy   2 B    ; remainder high = 0
    LDY #16             ;  2 cy   2 B    ; bit counter
loop:
    ASL dividend        ;  5 cy   2 B    ; shift dividend left
    ROL dividend+1      ;  5 cy   2 B    ;   high bit → carry
    ROL A               ;  2 cy   1 B    ; shift into remainder
    ROL rem+1           ;  5 cy   2 B
    TAX                 ;  2 cy   1 B    ; save remainder low
    CMP divisor         ;  3 cy   2 B    ; trial subtract (sets carry)
    LDA rem+1           ;  3 cy   2 B
    SBC divisor+1       ;  3 cy   2 B    ; carry from CMP propagates
    BCC no_sub          ;  3 cy   2 B    ; borrow → can't subtract
    STA rem+1           ;  3 cy   2 B    ; commit high byte
    TXA                 ;  2 cy   1 B
    SBC divisor         ;  3 cy   2 B    ; commit low byte
    TAX                 ;  2 cy   1 B
    INC dividend        ;  5 cy   2 B    ; set quotient bit
no_sub:
    TXA                 ;  2 cy   1 B    ; A = remainder low
    DEY                 ;  2 cy   1 B
    BNE loop            ;  3 cy   2 B
    STA rem             ;  3 cy   2 B    ; store final remainder
    RTS                 ;  6 cy   1 B
```

Per iteration (no sub): **38 cy** — `ASL`+`ROL`+`ROL A`+`ROL`+`TAX`+`CMP`+`LDA`+`SBC`+`BCC`(taken)+`TXA`+`DEY`+`BNE`

Per iteration (sub): **52 cy** — adds `STA`+`TXA`+`SBC`+`TAX`+`INC`

Average: **45 cy/iter**. Total code: **37 bytes**

**RISCY-V02** — R2 = dividend (becomes quotient), R3 = divisor, R4 = remainder

```
udiv16:
    LI   R4, 0          ;  2 cy   2 B    ; remainder = 0
    LI   R5, 16         ;  2 cy   2 B    ; counter
loop:
    SLLT R2             ;  2 cy   2 B    ; dividend <<= 1, T = old bit 15
    RLT  R4             ;  2 cy   2 B    ; remainder <<= 1, shift in T
    CLTU R4, R3         ;  2 cy   2 B    ; T = (rem < div)
    BT   no_sub         ;  2.5 cy 2 B    ; skip if can't subtract
    SUB  R4, R4, R3     ;  2 cy   2 B    ; remainder -= divisor
    ORI  R2, 1          ;  2 cy   2 B    ; set quotient bit
no_sub:
    ADDI R5, -1         ;  2 cy   2 B    ; counter--
    BNZ  R5, loop       ;  3 cy   2 B
    JR   R6, 0          ;  3 cy   2 B
```

Per iteration (no sub): **16 cy** — `SLLT`+`RLT`+`CLTU`+`BT`(taken)+`ADDI`+`BNZ`

Per iteration (sub): **19 cy** — adds `SUB`+`ORI`

Average: **17.5 cy/iter**. Total code: **22 bytes**

| | 6502 | RISCY-V02 |
|---|---|---|
| Per iteration (avg) | 45 cy | 17.5 cy |
| 16 iterations | ~720 cy | ~280 cy |
| Code size | 37 B | 22 B |

Same restoring division algorithm. cc65 keeps the remainder low byte in A throughout the loop, avoiding memory round-trips, and uses `CMP` to set carry for the trial subtract (replacing `SEC`+`LDA`+`SBC`). The 2.6× speedup: RISCY-V02's 16-bit shifts are single instructions, and `CLTU`+`BT` replaces the multi-instruction trial-subtract-and-branch. `SLLT`+`RLT` chain the dividend's high bit directly into the remainder without a register save.

## CRC-8 (SMBUS)

```c
uint8_t crc8(const uint8_t *data, uint8_t len);  // poly=0x07, init=0
```

Both use the standard bitwise algorithm: XOR each byte into the CRC, then shift left 8 times, conditionally XORing with the polynomial when the high bit shifts out.

**6502** — ptr ($00), len ($02, 8-bit), result in A

```
crc8:
    LDA #0              ;  2 cy   2 B    crc = 0
    LDY #0              ;  2 cy   2 B    index
byte_loop:
    EOR (ptr),Y         ;  5 cy   2 B    crc ^= *data
    LDX #8              ;  2 cy   2 B
bit_loop:
    ASL A               ;  2 cy   1 B    crc <<= 1
    BCC no_xor          ;  2.5 cy 2 B
    EOR #$07            ;  2 cy   2 B    crc ^= poly
no_xor:
    DEX                 ;  2 cy   1 B
    BNE bit_loop        ;  3 cy   2 B
    INY                 ;  2 cy   1 B
    DEC len             ;  5 cy   2 B
    BNE byte_loop       ;  3 cy   2 B
    RTS                 ;  6 cy   1 B
```

Bit loop (no xor): **10 cy** — `ASL`+`BCC`(taken)+`DEX`+`BNE`

Bit loop (xor): **11 cy** — adds `EOR`

Average: **10.5 cy/bit**, 84 cy/byte bit processing. Per byte: **101 cy**. Total code: **22 bytes**

**RISCY-V02** — R2 = data ptr, R3 = len, result in R4; CRC kept in upper byte

```
crc8:
    LI   R4, 0          ;  2 cy   2 B    crc = 0 (upper byte)
    LI   R0, 0x07       ;  2 cy   2 B    polynomial
    SLLI R0, 8          ;  2 cy   2 B    R0 = 0x0700
byte_loop:
    LBUR R5, R2         ;  3 cy   2 B    R5 = *data
    SLLI R5, 8          ;  2 cy   2 B    data in upper byte
    XOR  R4, R4, R5     ;  2 cy   2 B    crc ^= byte
    LI   R5, 8          ;  2 cy   2 B
bit_loop:
    SLLT R4             ;  2 cy   2 B    crc <<= 1, T = old bit 15
    BF   no_xor         ;  2.5 cy 2 B    skip if bit was 0
    XOR  R4, R4, R0     ;  2 cy   2 B    crc ^= poly
no_xor:
    ADDI R5, -1         ;  2 cy   2 B
    BNZ  R5, bit_loop   ;  3 cy   2 B
    ADDI R2, 1          ;  2 cy   2 B    data++
    ADDI R3, -1         ;  2 cy   2 B    len--
    BNZ  R3, byte_loop  ;  3 cy   2 B
    SRLI R4, 8          ;  2 cy   2 B    move to low byte
    JR   R6, 0          ;  3 cy   2 B
```

Bit loop (no xor): **10 cy** — `SLLT`+`BF`(taken)+`ADDI`+`BNZ`

Bit loop (xor): **11 cy** — adds `XOR`

Average: **10.5 cy/bit**, 84 cy/byte bit processing. Per byte: **100 cy**. Total code: **32 bytes**

| | 6502 | RISCY-V02 |
|---|---|---|
| Bit loop (avg) | 10.5 cy | 10.5 cy |
| Per byte | 101 cy | 100 cy |
| Code size | 22 B | 32 B |

Essentially a tie. `SLLT` matches the 6502's `ASL` + carry pattern — the bit loops are identical in cycle count. The 6502 wins on density (22 B vs 32 B) because its 1-byte implied-operand instructions pack tightly in an inherently 8-bit algorithm.

## CRC-16/CCITT

```c
uint16_t crc16(const uint8_t *data, uint8_t len);  // poly=0x1021, init=0xFFFF
```

Same bitwise algorithm, but with a 16-bit accumulator. The data byte is XORed into the high byte of the CRC.

**6502** — ptr ($00), len ($02, 8-bit), crc ($04)

```
crc16:
    LDA #$FF            ;  2 cy   2 B    crc = 0xFFFF
    STA crc             ;  3 cy   2 B
    STA crc+1           ;  3 cy   2 B
    LDY #0              ;  2 cy   2 B
byte_loop:
    LDA crc+1           ;  3 cy   2 B    crc_hi ^= *data
    EOR (ptr),Y         ;  5 cy   2 B
    STA crc+1           ;  3 cy   2 B
    LDX #8              ;  2 cy   2 B
bit_loop:
    ASL crc             ;  5 cy   2 B    crc <<= 1
    ROL crc+1           ;  5 cy   2 B
    BCC no_xor          ;  2.5 cy 2 B
    LDA crc+1           ;  3 cy   2 B    crc ^= 0x1021
    EOR #$10            ;  2 cy   2 B
    STA crc+1           ;  3 cy   2 B
    LDA crc             ;  3 cy   2 B
    EOR #$21            ;  2 cy   2 B
    STA crc             ;  3 cy   2 B
no_xor:
    DEX                 ;  2 cy   1 B
    BNE bit_loop        ;  3 cy   2 B
    INY                 ;  2 cy   1 B
    DEC len             ;  5 cy   2 B
    BNE byte_loop       ;  3 cy   2 B
    RTS                 ;  6 cy   1 B
```

Bit loop (no xor): **18 cy** — `ASL`+`ROL`+`BCC`(taken)+`DEX`+`BNE`

Bit loop (xor): **33 cy** — adds 2×(`LDA`+`EOR`+`STA`)

Average: **25.5 cy/bit**, 204 cy/byte bit processing. Per byte: **227 cy**. Total code: **43 bytes**

**RISCY-V02** — R2 = data ptr, R3 = len, R4 = crc, R0 = polynomial

```
crc16:
    LI   R4, -1         ;  2 cy   2 B    crc = 0xFFFF
    LUI  R0, 0x10       ;  2 cy   2 B    R0 = 0x1000
    ORI  R0, 0x21       ;  2 cy   2 B    R0 = 0x1021
byte_loop:
    LBUR R5, R2         ;  3 cy   2 B    R5 = *data
    SLLI R5, 8          ;  2 cy   2 B    byte → high position
    XOR  R4, R4, R5     ;  2 cy   2 B    crc ^= byte << 8
    LI   R5, 8          ;  2 cy   2 B
bit_loop:
    SLLT R4             ;  2 cy   2 B    crc <<= 1, T = old bit 15
    BF   no_xor         ;  2.5 cy 2 B    skip if bit was 0
    XOR  R4, R4, R0     ;  2 cy   2 B    crc ^= 0x1021
no_xor:
    ADDI R5, -1         ;  2 cy   2 B
    BNZ  R5, bit_loop   ;  3 cy   2 B
    ADDI R2, 1          ;  2 cy   2 B    data++
    ADDI R3, -1         ;  2 cy   2 B    len--
    BNZ  R3, byte_loop  ;  3 cy   2 B
    JR   R6, 0          ;  3 cy   2 B
```

Bit loop (no xor): **10 cy** — `SLLT`+`BF`(taken)+`ADDI`+`BNZ`

Bit loop (xor): **11 cy** — adds `XOR`

Average: **10.5 cy/bit**, 84 cy/byte bit processing. Per byte: **100 cy**. Total code: **34 bytes**

| | 6502 | RISCY-V02 |
|---|---|---|
| Bit loop (avg) | 25.5 cy | 10.5 cy |
| Per byte | 227 cy | 100 cy |
| Code size | 43 B | 34 B |

RISCY-V02 wins CRC-16 by >2× and is more compact. The 6502's bit loop balloons from 10.5 to 25.5 cy because every shift becomes `ASL`+`ROL` and every XOR becomes `LDA`+`EOR`+`STA` × 2 — the polynomial XOR alone is 1 instruction vs 6. The density advantage reverses from CRC-8 because byte-serialization overhead outweighs the 1-byte instruction advantage.

## Raster Bar Interrupt Handler

A classic demo effect: an interrupt fires once per scanline to change the background color, producing horizontal rainbow bands. The handler increments a color byte in memory and writes it to a display register — the simplest possible useful work. Both examples target a C64-style system (VIC-II at $D000, color byte in zero page).

**Interrupt entry latency:**

Both CPUs must finish the current instruction before taking the interrupt. The average wait depends on the instruction mix of the interrupted code:

- **6502:** Instructions take 2–7 cycles. Length-biased sampling across a typical game loop gives an average wait of **~1.5 cycles**. After the instruction completes, the hardware pushes PC and status to the stack and reads the IRQ vector: **7 cycles**.
- **RISCY-V02:** Instructions take 2–4 cycles (pipeline-visible). Average wait: **~1 cycle**. After completion, EPC/ESR are saved and the PC is redirected at dispatch (instantaneous), then the vector is fetched: **2 cycles**.

**6502** — color byte at $02 (zero page), VIC-II at $D019/$D021

```
                                    ;  7 cy        entry: push PC+P, read vector
irq_handler:
    PHA                 ;  3 cy   1 B    save A
    INC $02             ;  5 cy   2 B    color++ (zero page RMW)
    LDA $02             ;  3 cy   2 B    load updated color
    STA $D021           ;  4 cy   3 B    set background color
    LDA #$01            ;  2 cy   2 B
    STA $D019           ;  4 cy   3 B    ack raster interrupt
    PLA                 ;  4 cy   1 B    restore A
    RTI                 ;  6 cy   1 B
```

| Phase | Cycles |
|---|---|
| Instruction wait (avg) | ~1.5 |
| Hardware entry (push+vector) | 7 |
| Register save (`PHA`) | 3 |
| Handler body | 18 |
| Register restore (`PLA`) | 4 |
| Exit (`RTI`) | 6 |
| **Total** | **~39.5** |

Total code: **15 bytes**

**RISCY-V02** — color byte at $0002 (zero page), VIC-II at $D000

Every register the handler touches must be saved and restored. The handler needs R0 (implicit base for I-type memory ops) and R5 (scratch). The color byte is not within reach of the VIC registers, so R0 must be loaded twice — once for zero page, once for $D000.

Register saves go below the current SP without adjusting it. This is safe because RISCY-V02's IRQ entry sets I=1, masking further IRQs, and NMI handlers cannot return (RETI from NMI is undefined behavior per the architecture — NMI handlers reset, halt, or spin). Since nothing that could resume the handler will touch the stack, the space below SP is exclusively ours for the handler's lifetime.

```
                                    ;  2 cy        entry: dispatch + fetch vector
irq_handler:
    SWS  R0, -4         ;  4 cy   2 B    save R0 below SP
    SWS  R5, -2         ;  4 cy   2 B    save R5 below SP
    LI   R0, 0          ;  2 cy   2 B    R0 → zero page
    LBU  R5, 2          ;  3 cy   2 B    R5 = color ($0002)
    ADDI R5, 1          ;  2 cy   2 B    color++
    SB   R5, 2          ;  3 cy   2 B    save color ($0002)
    LUI  R0, 0xD0       ;  2 cy   2 B    R0 = $D000
    SB   R5, $21        ;  3 cy   2 B    $D021: background color
    SB   R5, $19        ;  3 cy   2 B    $D019: ack raster interrupt
    LWS  R5, -2         ;  4 cy   2 B    restore R5
    LWS  R0, -4         ;  4 cy   2 B    restore R0
    RETI                ;  3 cy   2 B
```

| Phase | Cycles |
|---|---|
| Instruction wait (avg) | ~1 |
| Hardware entry (dispatch+fetch) | 2 |
| Register save (`SWS`×2) | 8 |
| Handler body | 18 |
| Register restore (`LWS`×2) | 8 |
| Exit (`RETI`+fetch) | 3 |
| **Total** | **~40** |

Total code: **24 bytes**

| | 6502 | RISCY-V02 |
|---|---|---|
| Entry (HW) | 7 cy | 2 cy |
| Insn wait (avg) | ~1.5 cy | ~1 cy |
| Save/restore | 7 cy | 16 cy |
| Handler body | 18 cy | 18 cy |
| Exit | 6 cy | 3 cy |
| **Total** | **~39.5 cy** | **~40 cy** |
| Code size | 15 B | 24 B |

Essentially a tie. The 6502's advantage — each instruction carries its own address, so the handler mixes zero-page and absolute accesses without base register setup — is offset by RISCY-V02's 2-cycle entry/exit vs 13. RISCY-V02 must reload R0 when switching memory regions and save/restore two registers (16 cy vs 7 cy), but the entry/exit savings compensate. For handlers with more useful work, the save/restore cost is fixed while body instructions are generally faster.

## RC4 Keystream (PRGA)

RC4's pseudo-random generation algorithm — the core inner loop of the stream cipher. Each call generates one byte of keystream from a 256-byte permutation table S and two indices i, j:

```
i = (i + 1) mod 256
j = (j + S[i]) mod 256
swap(S[i], S[j])
output = S[(S[i] + S[j]) mod 256]
```

Four array-indexed operations with computed indices, a swap, and double indirection — a worst case for a load-store architecture that must compute every address through registers.

**6502** — S at $0200 (page-aligned), i/j in zero page

```
rc4_byte:
    INC i           ; 5 cy  2 B    i = (i+1) mod 256
    LDX i           ; 3 cy  2 B    X = i
    LDA $0200,X     ; 4 cy  3 B    A = S[i]
    PHA             ; 3 cy  1 B    save S[i]
    CLC             ; 2 cy  1 B
    ADC j           ; 3 cy  2 B    A = j + S[i]
    STA j           ; 3 cy  2 B    j updated
    TAY             ; 2 cy  1 B    Y = j
    LDA $0200,Y     ; 4 cy  3 B    A = S[j]
    STA $0200,X     ; 5 cy  3 B    S[i] = S[j]
    PLA             ; 4 cy  1 B    A = old S[i]
    STA $0200,Y     ; 5 cy  3 B    S[j] = old S[i]
    CLC             ; 2 cy  1 B
    ADC $0200,X     ; 4 cy  3 B    A = S[i]+S[j] (new)
    TAY             ; 2 cy  1 B
    LDA $0200,Y     ; 4 cy  3 B    output byte
    RTS             ; 6 cy  1 B
```

**61 cycles, 34 bytes.** S[i] is saved with `PHA` before the j computation (avoiding a re-read), then restored with `PLA` for the swap. The i and j indices must live in zero page because X and Y are needed for array indexing.

**RISCY-V02** — S base in R0, i in R1, j in R2; output in R3; R7 = 0x00FF (preloaded once)

```
; Setup (once): LI R7, -1; SRLI R7, 8  →  R7 = 0x00FF
rc4_byte:
    ADDI R1, 1          ; 2 cy  2 B    i++
    AND  R1, R1, R7     ; 2 cy  2 B    mod 256
    ADD  R3, R0, R1     ; 2 cy  2 B    R3 = &S[i]
    LBUR R4, R3         ; 3 cy  2 B    R4 = S[i]
    ADD  R2, R2, R4     ; 2 cy  2 B    j += S[i]
    AND  R2, R2, R7     ; 2 cy  2 B    mod 256
    ADD  R3, R0, R2     ; 2 cy  2 B    R3 = &S[j]
    LBUR R5, R3         ; 3 cy  2 B    R5 = S[j]
    SBR  R4, R3         ; 3 cy  2 B    S[j] = old S[i]
    ADD  R3, R0, R1     ; 2 cy  2 B    R3 = &S[i]
    SBR  R5, R3         ; 3 cy  2 B    S[i] = old S[j]
    ADD  R3, R4, R5     ; 2 cy  2 B    R3 = S[i]+S[j]
    AND  R3, R3, R7     ; 2 cy  2 B    mod 256
    ADD  R3, R0, R3     ; 2 cy  2 B    R3 = &S[sum]
    LBUR R3, R3         ; 3 cy  2 B    output byte
    JR   R6, 0          ; 3 cy  2 B
```

**38 cycles, 32 bytes.** Three `AND` instructions (6 cy) with a preloaded mask register are needed for mod-256 masking that the 6502 gets for free from 8-bit registers (the mask setup is amortized over many calls). Five `ADD` instructions (10 cy) compute array addresses that the 6502 folds into its indexed addressing modes. Despite this 16-cycle tax, RISCY-V02 wins by a wide margin.

| | 6502 | RISCY-V02 |
|---|---|---|
| Cycles | 61 | 38 |
| Code size | 34 B | 32 B |
| Speedup | 1.0× | 1.6× |

RISCY-V02 wins 1.6× on speed and is slightly more compact despite needing explicit mod-256 masking (ANDI is sign-extended, so a preloaded mask register is needed). Two factors overwhelm the masking/address tax: registers eliminate state traffic (the 6502 spends 14 cy per call reading and writing i/j in zero page; RISCY-V02 keeps them in registers), and multiple live values avoid spills (the swap needs S[i] and S[j] simultaneously, forcing the 6502 into a `PHA`/`PLA` spill that RISCY-V02 avoids entirely).

## 32-bit Arithmetic

32-bit operations expose the word-width cost directly: the 6502's 8-bit ALU requires four byte-at-a-time steps; RISCY-V02's 16-bit ALU cuts this to two. Convention: **6502** uses four zero-page bytes (a $00–$03, b $04–$07, r $08–$0B); **RISCY-V02** uses register pairs {high, low} (A = {R1, R0}, B = {R3, R2}, result = {R5, R4}).

### 32-bit ADD

```c
uint32_t add32(uint32_t a, uint32_t b);
```

**6502**

```
    CLC             ;  2 cy   1 B
    LDA a           ;  3 cy   2 B
    ADC b           ;  3 cy   2 B
    STA r           ;  3 cy   2 B
    LDA a+1         ;  3 cy   2 B
    ADC b+1         ;  3 cy   2 B
    STA r+1         ;  3 cy   2 B
    LDA a+2         ;  3 cy   2 B
    ADC b+2         ;  3 cy   2 B
    STA r+2         ;  3 cy   2 B
    LDA a+3         ;  3 cy   2 B
    ADC b+3         ;  3 cy   2 B
    STA r+3         ;  3 cy   2 B
```

13 instructions, **25 bytes, 38 cycles.** Carry chains automatically through all four ADC operations.

**RISCY-V02** — A = {R1, R0}, B = {R3, R2}, result = {R5, R4}

```
    ADD  R4, R0, R2     ;  2 cy   2 B    Rl = Al + Bl
    CLTU R4, R0         ;  2 cy   2 B    T = carry (result < input)
    ADD  R5, R1, R3     ;  2 cy   2 B    Rh = Ah + Bh
    BF   done           ;  3 cy   2 B    skip if no carry (T=0)
    ADDI R5, 1          ;  2 cy   2 B    Rh += carry
done:
```

5 instructions, **10 bytes, 9–10 cycles.** `CLTU` detects unsigned overflow (result < input), then a conditional `ADDI` propagates the carry. Constant-time variant: `SRR R0; ANDI R0, 1; ADD R5, R5, R0` (6 insns, 12 B, 12 cy).

| | 6502 | RISCY-V02 |
|---|---|---|
| Code size | 25 B | 10 B |
| Cycles | 38 | 9–10 |
| Speedup | 1.0× | 3.8–4.2× |

### 32-bit SUB

```c
uint32_t sub32(uint32_t a, uint32_t b);
```

**6502**

```
    SEC             ;  2 cy   1 B
    LDA a           ;  3 cy   2 B
    SBC b           ;  3 cy   2 B
    STA r           ;  3 cy   2 B
    LDA a+1         ;  3 cy   2 B
    SBC b+1         ;  3 cy   2 B
    STA r+1         ;  3 cy   2 B
    LDA a+2         ;  3 cy   2 B
    SBC b+2         ;  3 cy   2 B
    STA r+2         ;  3 cy   2 B
    LDA a+3         ;  3 cy   2 B
    SBC b+3         ;  3 cy   2 B
    STA r+3         ;  3 cy   2 B
```

13 instructions, **25 bytes, 38 cycles.** Mirror of ADD with SEC/SBC.

**RISCY-V02** — A = {R1, R0}, B = {R3, R2}, result = {R5, R4}

```
    CLTU R0, R2         ;  2 cy   2 B    T = borrow (Al < Bl)
    SUB  R4, R0, R2     ;  2 cy   2 B    Rl = Al - Bl
    SUB  R5, R1, R3     ;  2 cy   2 B    Rh = Ah - Bh
    BF   done           ;  3 cy   2 B    skip if no borrow (T=0)
    ADDI R5, -1         ;  2 cy   2 B    Rh -= borrow
done:
```

5 instructions, **10 bytes, 9–10 cycles.** `CLTU` must precede `SUB` to compare the original Al. Constant-time variant: `SRR R0; ANDI R0, 1; SUB R5, R5, R0` (6 insns, 12 B, 12 cy).

| | 6502 | RISCY-V02 |
|---|---|---|
| Code size | 25 B | 10 B |
| Cycles | 38 | 9–10 |
| Speedup | 1.0× | 3.8–4.2× |

### 32-bit AND / OR / XOR

```c
uint32_t and32(uint32_t a, uint32_t b);
uint32_t or32(uint32_t a, uint32_t b);
uint32_t xor32(uint32_t a, uint32_t b);
```

Identical structure for all three — no carry, no interaction between bytes/words.

**6502** (shown for AND; substitute ORA/EOR for OR/XOR)

```
    LDA a           ;  3 cy   2 B
    AND b           ;  3 cy   2 B
    STA r           ;  3 cy   2 B
    LDA a+1         ;  3 cy   2 B
    AND b+1         ;  3 cy   2 B
    STA r+1         ;  3 cy   2 B
    LDA a+2         ;  3 cy   2 B
    AND b+2         ;  3 cy   2 B
    STA r+2         ;  3 cy   2 B
    LDA a+3         ;  3 cy   2 B
    AND b+3         ;  3 cy   2 B
    STA r+3         ;  3 cy   2 B
```

12 instructions, **24 bytes, 36 cycles.**

**RISCY-V02** (shown for AND; substitute OR/XOR)

```
    AND  R4, R0, R2     ;  2 cy   2 B    Rl = Al & Bl
    AND  R5, R1, R3     ;  2 cy   2 B    Rh = Ah & Bh
```

2 instructions, **4 bytes, 4 cycles.**

| | 6502 | RISCY-V02 |
|---|---|---|
| Code size | 24 B | 4 B |
| Cycles | 36 | 4 |
| Speedup | 1.0× | 9.0× |

### 32-bit SLL (Shift Left Logical)

```c
uint32_t sll32(uint32_t a, unsigned shamt);  // shamt 0–31
```

The 6502 must loop one bit per iteration, chaining ASL+ROL across four bytes. RISCY-V02's barrel shifter enables an O(1) approach: split on N >= 16, shift both halves, merge the cross-word bits.

**6502** — val ($00–$03, modified in-place), shift count in X

```
    LDX shift       ;  3 cy   2 B
    BEQ done        ;  2 cy   2 B
loop:
    ASL val         ;  5 cy   2 B
    ROL val+1       ;  5 cy   2 B
    ROL val+2       ;  5 cy   2 B
    ROL val+3       ;  5 cy   2 B
    DEX             ;  2 cy   1 B
    BNE loop        ;  3 cy   2 B
done:
```

8 instructions, **15 bytes.** Per iteration: **25 cycles.** An 8-bit shift costs 204 cycles.

**RISCY-V02** — {R1, R0} shifted in-place, count in R2 (consumed), R3 scratch

```
    BZ   R2, done       ;  2 cy   2 B
    LI   R3, 16         ;  2 cy   2 B
    CLTU R2, R3         ;  2 cy   2 B    T = (N < 16)
    BT   small          ;  3 cy   2 B
    ; N >= 16: Rh = Rl << (N-16), Rl = 0
    SUB  R2, R2, R3     ;  2 cy   2 B
    SLL  R1, R0, R2     ;  2 cy   2 B
    LI   R0, 0          ;  2 cy   2 B
    J    done           ;  3 cy   2 B
small:
    ; N = 1..15: shift both halves, merge cross-word bits
    SUB  R3, R3, R2     ;  2 cy   2 B    R3 = 16-N
    SRL  R3, R0, R3     ;  2 cy   2 B    R3 = Rl >> (16-N)
    SLL  R1, R1, R2     ;  2 cy   2 B    Rh <<= N
    OR   R1, R1, R3     ;  2 cy   2 B    Rh |= cross bits
    SLL  R0, R0, R2     ;  2 cy   2 B    Rl <<= N
done:
```

13 instructions, **26 bytes, 17–19 cycles** (constant, regardless of shift amount). For compact code at the cost of O(N) time, a loop alternative using SLLT+RLT is 5 insns / 10 B / 9N cy.

| | 6502 | RISCY-V02 |
|---|---|---|
| Code size | 15 B | 26 B |
| 1-bit shift | 29 cy | 19 cy |
| 8-bit shift | 204 cy | 19 cy |
| 16-bit shift | 404 cy | 17 cy |
| Speedup (N=8) | 1.0× | 10.7× |

The 6502 is more compact but O(N). For typical shift amounts (4–12), the barrel version is 5–10× faster.

### 32-bit SRL (Shift Right Logical)

Mirror of SLL. The 6502 chains LSR+ROR from the MSB down; RISCY-V02 reverses the halves.

**6502** — val ($00–$03, modified in-place), shift count in X

```
    LDX shift       ;  3 cy   2 B
    BEQ done        ;  2 cy   2 B
loop:
    LSR val+3       ;  5 cy   2 B
    ROR val+2       ;  5 cy   2 B
    ROR val+1       ;  5 cy   2 B
    ROR val         ;  5 cy   2 B
    DEX             ;  2 cy   1 B
    BNE loop        ;  3 cy   2 B
done:
```

8 instructions, **15 bytes.** Per iteration: **25 cycles.**

**RISCY-V02** — {R1, R0} shifted in-place, count in R2 (consumed), R3 scratch

```
    BZ   R2, done       ;  2 cy   2 B
    LI   R3, 16         ;  2 cy   2 B
    CLTU R2, R3         ;  2 cy   2 B    T = (N < 16)
    BT   small          ;  3 cy   2 B
    ; N >= 16: Rl = Rh >> (N-16), Rh = 0
    SUB  R2, R2, R3     ;  2 cy   2 B
    SRL  R0, R1, R2     ;  2 cy   2 B
    LI   R1, 0          ;  2 cy   2 B
    J    done           ;  3 cy   2 B
small:
    ; N = 1..15: shift both halves, merge cross-word bits
    SUB  R3, R3, R2     ;  2 cy   2 B    R3 = 16-N
    SLL  R3, R1, R3     ;  2 cy   2 B    R3 = Rh << (16-N)
    SRL  R0, R0, R2     ;  2 cy   2 B    Rl >>= N
    OR   R0, R0, R3     ;  2 cy   2 B    Rl |= cross bits
    SRL  R1, R1, R2     ;  2 cy   2 B    Rh >>= N
done:
```

13 instructions, **26 bytes, 17–19 cycles** (constant). Loop alternative: SRLT+RRT, 5 insns / 10 B / 9N cy.

| | 6502 | RISCY-V02 |
|---|---|---|
| Code size | 15 B | 26 B |
| 1-bit shift | 29 cy | 19 cy |
| 8-bit shift | 204 cy | 19 cy |
| 16-bit shift | 404 cy | 17 cy |
| Speedup (N=8) | 1.0× | 10.7× |

### 32-bit SRA (Shift Right Arithmetic)

Arithmetic right shift preserves the sign bit. The 6502 uses `LDA; ASL A` to copy the sign into carry, then chains `ROR` — but must loop. RISCY-V02 handles it in O(1), with `SRAI R1, 15` to sign-fill the high word in the large-shift case.

**6502** — val ($00–$03, modified in-place), shift count in X

```
    LDX shift       ;  3 cy   2 B
    BEQ done        ;  2 cy   2 B
loop:
    LDA val+3       ;  3 cy   2 B    load MSB
    ASL A           ;  2 cy   1 B    sign bit → carry
    ROR val+3       ;  5 cy   2 B    sign-preserving shift
    ROR val+2       ;  5 cy   2 B
    ROR val+1       ;  5 cy   2 B
    ROR val         ;  5 cy   2 B
    DEX             ;  2 cy   1 B
    BNE loop        ;  3 cy   2 B
done:
```

10 instructions, **18 bytes.** Per iteration: **30 cycles.** The LDA+ASL A trick (5 cy, 3 B) is the price of not having a dedicated ASR instruction.

**RISCY-V02** — {R1, R0} shifted in-place, count in R2 (consumed), R3 scratch

```
    BZ   R2, done       ;  2 cy   2 B
    LI   R3, 16         ;  2 cy   2 B
    CLTU R2, R3         ;  2 cy   2 B    T = (N < 16)
    BT   small          ;  3 cy   2 B
    ; N >= 16: Rl = Rh >>s (N-16), Rh = sign-fill
    SUB  R2, R2, R3     ;  2 cy   2 B
    SRA  R0, R1, R2     ;  2 cy   2 B    Rl = Rh >>s (N-16)
    SRAI R1, 15         ;  2 cy   2 B    Rh = 0x0000 or 0xFFFF
    J    done           ;  3 cy   2 B
small:
    ; N = 1..15: shift both halves, merge cross-word bits
    SUB  R3, R3, R2     ;  2 cy   2 B    R3 = 16-N
    SLL  R3, R1, R3     ;  2 cy   2 B    R3 = Rh << (16-N)
    SRL  R0, R0, R2     ;  2 cy   2 B    Rl >>= N (logical)
    OR   R0, R0, R3     ;  2 cy   2 B    Rl |= cross bits
    SRA  R1, R1, R2     ;  2 cy   2 B    Rh >>= N (arithmetic)
done:
```

13 instructions, **26 bytes, 17–19 cycles** (constant).

| | 6502 | RISCY-V02 |
|---|---|---|
| Code size | 18 B | 26 B |
| 1-bit shift | 34 cy | 19 cy |
| 8-bit shift | 244 cy | 19 cy |
| 16-bit shift | 484 cy | 17 cy |
| Speedup (N=8) | 1.0× | 12.8× |

### 32-bit Summary

| Operation | 6502 | | RISCY-V02 | | Speedup |
|---|---|---|---|---|---|
| | Bytes | Cycles | Bytes | Cycles | |
| ADD | 25 | 38 | 10 | 9–10 | 3.8–4.2× |
| SUB | 25 | 38 | 10 | 9–10 | 3.8–4.2× |
| AND | 24 | 36 | 4 | 4 | 9.0× |
| OR | 24 | 36 | 4 | 4 | 9.0× |
| XOR | 24 | 36 | 4 | 4 | 9.0× |
| SLL (N=8) | 15 | 204 | 26 | 19 | 10.7× |
| SRL (N=8) | 15 | 204 | 26 | 19 | 10.7× |
| SRA (N=8) | 18 | 244 | 26 | 19 | 12.8× |

ADD/SUB collapse from 4 byte additions to 2 word additions plus a lightweight carry chain. Bitwise ops: 2 instructions vs 12. Shifts are the clearest architectural win — the barrel shifter transforms the 6502's weakest operation (O(N) loops) into constant-time 17–19 cycles, a 10–13× speedup. The 6502 wins on shift code size (15–18 B vs 26 B); for code-size-sensitive contexts, a compact loop using SLLT/RLT (10 B, 9N cy) is available.

## Packed BCD Arithmetic

The 6502's hardware decimal mode (`SED`) makes BCD trivial — `ADC`/`SBC` apply nibble correction automatically. RISCY-V02 must do it in software via the Jones algorithm: pre-inject 6 into each nibble, add, detect which nibbles carried, subtract 6 from those that didn't.

### 8-bit Packed BCD Addition

```c
// a, b: 2-digit packed BCD (0x00–0x99)
// Returns packed BCD sum, carry in C/T
uint8_t bcd_add8(uint8_t a, uint8_t b);
```

**6502** — a in A, b in memory, result in A

```
    SED                 ;  2 cy   1 B    decimal mode
    CLC                 ;  2 cy   1 B
    ADC b               ;  3 cy   2 B    BCD add
    CLD                 ;  2 cy   1 B    back to binary
```

4 instructions, **5 bytes, 9 cycles.**

**RISCY-V02** — a in R0, b in R1, result in R0, R2–R4 scratch

```
    LI   R2, 0x66       ;  2 cy   2 B    correction constant
    ADD  R3, R0, R2      ;  2 cy   2 B    t1 = a + 0x66
    ADD  R0, R3, R1      ;  2 cy   2 B    t2 = t1 + b
    XOR  R3, R3, R1      ;  2 cy   2 B    t3 = t1 ^ b
    XOR  R3, R0, R3      ;  2 cy   2 B    t4 = t2 ^ t3 (carry bits)
    LUI  R4, 0x01        ;  2 cy   2 B    \
    ADDI R4, 0x10        ;  2 cy   2 B    / R4 = 0x0110 (nibble mask)
    AND  R3, R3, R4      ;  2 cy   2 B    keep only nibble carry bits
    XOR  R3, R3, R4      ;  2 cy   2 B    invert: 1 = no carry (needs -6)
    OR   R4, R3, R3      ;  2 cy   2 B    R4 = copy of R3
    SRLI R4, 2           ;  2 cy   2 B    R4 = R3 >> 2
    SRLI R3, 3           ;  2 cy   2 B    R3 >>= 3
    OR   R3, R3, R4      ;  2 cy   2 B    correction = 6 per nibble
    SUB  R0, R0, R3      ;  2 cy   2 B    subtract excess 6
```

14 instructions, **28 bytes, 28 cycles.** Branchless; BCD carry in bit 8.

| | 6502 | RISCY-V02 |
|---|---|---|
| Code size | 5 B | 28 B |
| Cycles | 9 cy | 28 cy |
| Speedup | 1.0× | 0.3× |

### 16-bit Packed BCD Addition

```c
// a, b: 4-digit packed BCD (0x0000–0x9999)
// Returns packed BCD sum, carry in C/T
uint16_t bcd_add16(uint16_t a, uint16_t b);
```

**6502** — val at ($00–$01), addend at ($02–$03), result in-place

```
    SED                 ;  2 cy   1 B    decimal mode
    CLC                 ;  2 cy   1 B
    LDA val+0           ;  3 cy   2 B
    ADC addend+0        ;  3 cy   2 B    low byte BCD add
    STA val+0           ;  3 cy   2 B
    LDA val+1           ;  3 cy   2 B
    ADC addend+1        ;  3 cy   2 B    high byte + carry
    STA val+1           ;  3 cy   2 B
    CLD                 ;  2 cy   1 B
```

9 instructions, **15 bytes, 24 cycles.** Two 8-bit BCD adds chained through carry.

**RISCY-V02** — a in R0, b in R1, result in R0, R2–R4 scratch

```
    LUI  R2, 0x66        ;  2 cy   2 B    \
    ADDI R2, 0x66         ;  2 cy   2 B    / R2 = 0x6666
    ADD  R3, R0, R2       ;  2 cy   2 B    t1 = a + 0x6666
    ADD  R0, R3, R1       ;  2 cy   2 B    t2 = t1 + b
    XOR  R3, R3, R1       ;  2 cy   2 B    t3 = t1 ^ b
    XOR  R3, R0, R3       ;  2 cy   2 B    t4 = t2 ^ t3
    LUI  R4, 0x11         ;  2 cy   2 B    \
    ADDI R4, 0x10         ;  2 cy   2 B    / R4 = 0x1110
    AND  R3, R3, R4       ;  2 cy   2 B    keep nibble carry bits
    XOR  R3, R3, R4       ;  2 cy   2 B    invert: 1 = needs -6
    OR   R4, R3, R3       ;  2 cy   2 B    R4 = copy of R3
    SRLI R4, 2            ;  2 cy   2 B    R4 = R3 >> 2
    SRLI R3, 3            ;  2 cy   2 B    R3 >>= 3
    OR   R3, R3, R4       ;  2 cy   2 B    correction = 6 per nibble
    SUB  R0, R0, R3       ;  2 cy   2 B    subtract excess 6
```

15 instructions, **30 bytes, 30 cycles.** Same structure as 8-bit — the wider register handles all 4 digits in parallel.

| | 6502 | RISCY-V02 |
|---|---|---|
| Code size | 15 B | 30 B |
| Cycles | 24 cy | 30 cy |
| Speedup | 1.0× | 0.8× |

At 4 digits, the 6502's byte-serial approach starts to cost it. RISCY-V02's parallel nibble correction nearly closes the gap.

### 32-bit Packed BCD Addition

```c
// a, b: 8-digit packed BCD (0x00000000–0x99999999)
// Returns packed BCD sum, carry in C/T
uint32_t bcd_add32(uint32_t a, uint32_t b);
```

**6502** — val at ($00–$03), addend at ($04–$07), result in-place

```
    SED                 ;  2 cy   1 B    decimal mode
    CLC                 ;  2 cy   1 B
    LDA val+0           ;  3 cy   2 B
    ADC addend+0        ;  3 cy   2 B    byte 0
    STA val+0           ;  3 cy   2 B
    LDA val+1           ;  3 cy   2 B
    ADC addend+1        ;  3 cy   2 B    byte 1 + carry
    STA val+1           ;  3 cy   2 B
    LDA val+2           ;  3 cy   2 B
    ADC addend+2        ;  3 cy   2 B    byte 2 + carry
    STA val+2           ;  3 cy   2 B
    LDA val+3           ;  3 cy   2 B
    ADC addend+3        ;  3 cy   2 B    byte 3 + carry
    STA val+3           ;  3 cy   2 B
    CLD                 ;  2 cy   1 B
```

15 instructions, **25 bytes, 42 cycles.**

**RISCY-V02** — {R1, R0} + {R3, R2}, result in {R1, R0}, R4–R6 scratch

Two Jones corrections chained by a BCD carry detected via `CLTU` (unsigned overflow).

```
    ; --- low half: BCD(R0 + R2) ---
    LUI  R4, 0x66        ;  2 cy   2 B    \
    ADDI R4, 0x66         ;  2 cy   2 B    / R4 = 0x6666
    ADD  R5, R0, R4       ;  2 cy   2 B    t1 = a_lo + 0x6666
    ADD  R0, R5, R2       ;  2 cy   2 B    t2 = t1 + b_lo
    CLTU R0, R2           ;  2 cy   2 B    T = BCD carry (t2 < b_lo → overflow)
    XOR  R5, R5, R2       ;  2 cy   2 B    t3 = t1 ^ b_lo
    XOR  R5, R0, R5       ;  2 cy   2 B    t4 = t2 ^ t3
    LUI  R6, 0x11         ;  2 cy   2 B    \
    ADDI R6, 0x10         ;  2 cy   2 B    / R6 = 0x1110
    AND  R5, R5, R6       ;  2 cy   2 B    nibble carry bits
    XOR  R5, R5, R6       ;  2 cy   2 B    invert: 1 = needs -6
    OR   R6, R5, R5       ;  2 cy   2 B    copy
    SRLI R6, 2            ;  2 cy   2 B    R6 = R5 >> 2
    SRLI R5, 3            ;  2 cy   2 B    R5 >>= 3
    OR   R5, R5, R6       ;  2 cy   2 B    correction
    SUB  R0, R0, R5       ;  2 cy   2 B    corrected low result
    ; --- high half: BCD(R1 + R3 + carry) ---
    SRR  R5               ;  2 cy   2 B    \
    ANDI R5, 1            ;  2 cy   2 B    / R5 = carry (0 or 1)
    ADD  R1, R1, R5       ;  2 cy   2 B    a_hi' = a_hi + carry
    LUI  R4, 0x66         ;  2 cy   2 B    \
    ADDI R4, 0x66         ;  2 cy   2 B    / R4 = 0x6666
    ADD  R5, R1, R4       ;  2 cy   2 B    t1 = a_hi' + 0x6666
    ADD  R1, R5, R3       ;  2 cy   2 B    t2 = t1 + b_hi
    XOR  R5, R5, R3       ;  2 cy   2 B    t3 = t1 ^ b_hi
    XOR  R5, R1, R5       ;  2 cy   2 B    t4 = t2 ^ t3
    LUI  R6, 0x11         ;  2 cy   2 B    \
    ADDI R6, 0x10         ;  2 cy   2 B    / R6 = 0x1110
    AND  R5, R5, R6       ;  2 cy   2 B    nibble carry bits
    XOR  R5, R5, R6       ;  2 cy   2 B    invert
    OR   R6, R5, R5       ;  2 cy   2 B    copy
    SRLI R6, 2            ;  2 cy   2 B    R6 = R5 >> 2
    SRLI R5, 3            ;  2 cy   2 B    R5 >>= 3
    OR   R5, R5, R6       ;  2 cy   2 B    correction
    SUB  R1, R1, R5       ;  2 cy   2 B    corrected high result
```

34 instructions, **68 bytes, 68 cycles.** In a subroutine, the constant loads (0x6666, 0x1110) could be hoisted, saving 8 instructions per call.

| | 6502 | RISCY-V02 |
|---|---|---|
| Code size | 25 B | 68 B |
| Cycles | 42 cy | 68 cy |
| Speedup | 1.0× | 0.6× |

The 6502's advantage continues to erode: it scales at 9 cy per byte, while RISCY-V02's Jones algorithm handles 4 nibbles in parallel per 16-bit word.

### BCD Summary

| Operation | 6502 | | RISCY-V02 | | Speedup |
|---|---|---|---|---|---|
| | Bytes | Cycles | Bytes | Cycles | |
| 8-bit add (2 digits) | 5 | 9 | 28 | 28 | 0.3× |
| 16-bit add (4 digits) | 15 | 24 | 30 | 30 | 0.8× |
| 32-bit add (8 digits) | 25 | 42 | 68 | 68 | 0.6× |

Hardware BCD is the 6502's clearest architectural advantage. For 2-digit addition, `SED; CLC; ADC; CLD` is unbeatable. But the gap narrows with wider operands — the 6502 scales at 9 cy/byte while RISCY-V02's Jones algorithm handles 4 nibbles in parallel per word. At 4 digits the counts nearly converge.

The real question is whether BCD justifies the ~400 transistors the 6502 spends on decimal mode. In the 1970s context, BCD was used for scores, clocks, and financial calculations — common but not performance-critical. The transistor budget is better spent on features that accelerate hot loops (barrel shifter, wider ALU).

