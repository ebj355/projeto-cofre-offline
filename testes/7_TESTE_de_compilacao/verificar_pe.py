"""Confere protecoes ASLR, DEP, High-Entropy ASLR e CFG; codigos: 0=ok, 1=protecao ausente, 2=exe nao encontrado, 9=pefile ausente."""
import os
import sys

OBRIGATORIAS = {0x0040: "DYNAMICBASE (ASLR)", 0x0100: "NX_COMPAT (DEP)"}
DESEJAVEIS = {0x0020: "HIGH_ENTROPY_VA (ASLR 64 bits)", 0x4000: "GUARD_CF (Control Flow Guard)"}


def main():
    if len(sys.argv) < 2 or not os.path.isfile(sys.argv[1]):
        print("Executavel nao encontrado.")
        return 2
    try:
        import pefile
    except ImportError:
        print("pefile nao instalado.")
        return 9
    pe = pefile.PE(sys.argv[1], fast_load=True)
    flags = pe.OPTIONAL_HEADER.DllCharacteristics
    falta = 0
    print(f"Arquivo: {sys.argv[1]}")
    for bit, nome in OBRIGATORIAS.items():
        ok = bool(flags & bit)
        falta += not ok
        print(f"  [{'OK' if ok else 'FALTA'}] {nome}")
    for bit, nome in DESEJAVEIS.items():
        print(f"  [{'OK' if flags & bit else 'aviso'}] {nome} (desejavel)")
    assinado = pe.OPTIONAL_HEADER.DATA_DIRECTORY[4].Size > 0
    print(f"  [{'OK' if assinado else 'aviso'}] assinatura Authenticode (o projeto declara que nao assina)")
    return 1 if falta else 0


if __name__ == "__main__":
    sys.exit(main())
