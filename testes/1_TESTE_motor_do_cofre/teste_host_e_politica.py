"""RASTROS NO HOST (pasta temporária privada) e POLÍTICA OPCIONAL "EXIGIR NTFS".
- isolar_temporarios: TEMP/TMP/TMPDIR e tempfile passam a apontar para <base>/.tmp_cofre; um arquivo temporário criado
  ali some em limpar_temporarios; resto de queda anterior é apagado ao iniciar; atalho no lugar da pasta -> None e nada
  muda; pasta sem escrita -> None; limpar não mexe em nada fora da pasta;
- politica_exigir_ntfs: desligada por padrão; liga por variável de ambiente ou por arquivo marcador;
- aviso_sistema_de_arquivos continua só 'alerta' para FAT/exFAT e vazio para NTFS."""
import os, sys, tempfile, shutil, importlib.util
spec = importlib.util.spec_from_file_location("c", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "cofre_senhas.py"))
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
FAL = []


def ok(cond, msg):
    print(("  [OK]   " if cond else "  [FALHOU] ") + msg, flush=True)
    if not cond:
        FAL.append(msg)


env0 = {k: os.environ.get(k) for k in ("TEMP", "TMP", "TMPDIR", "COFRE_EXIGIR_NTFS")}
tmp0 = tempfile.tempdir
try:
    print("== 1) pasta temporária privada")
    base = tempfile.mkdtemp(prefix="base_")
    alheio = os.path.join(base, "alheio.txt"); open(alheio, "w").write("não mexer")
    pasta = os.path.join(base, c.NOME_PASTA_TEMP)
    os.makedirs(pasta); open(os.path.join(pasta, "resto_de_queda.tmp"), "w").write("x")
    r = c.isolar_temporarios(base)
    ok(r == pasta and os.path.isdir(pasta), "isolar_temporarios devolve a pasta e ela existe")
    ok(os.listdir(pasta) == [], "resto de uma queda anterior foi apagado ao iniciar")
    ok(all(os.environ.get(v) == pasta for v in ("TEMP", "TMP", "TMPDIR")), "TEMP/TMP/TMPDIR apontam para a pasta privada")
    ok(tempfile.gettempdir() == pasta, "tempfile.gettempdir() aponta para a pasta privada")
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"x"); criado = f.name
    ok(os.path.dirname(criado) == pasta, "arquivo temporário novo nasce na pasta privada")
    if os.name == "posix":
        ok((os.stat(pasta).st_mode & 0o777) == 0o700, "pasta privada com permissão 0700")
    c.limpar_temporarios()
    ok(not os.path.exists(pasta) and not os.path.exists(criado), "limpar_temporarios apaga a pasta e o que havia nela")
    ok(open(alheio).read() == "não mexer", "arquivo fora da pasta privada NÃO foi tocado")
    c.limpar_temporarios()
    ok(True, "limpar_temporarios duas vezes não dá erro")

    print("== 2) casos de falha: nada muda")
    for k in ("TEMP", "TMP", "TMPDIR"):
        os.environ[k] = "/ponto/original"
    tempfile.tempdir = None
    base2 = tempfile.mkdtemp(prefix="base2_"); alvo = tempfile.mkdtemp(prefix="alvo_")
    if os.name == "posix":
        os.symlink(alvo, os.path.join(base2, c.NOME_PASTA_TEMP))
        open(os.path.join(alvo, "importante.txt"), "w").write("i")
        ok(c.isolar_temporarios(base2) is None, "atalho no lugar da pasta: recusa (None)")
        ok(os.path.exists(os.path.join(alvo, "importante.txt")), "o destino do atalho NÃO foi apagado")
        ok(os.environ["TEMP"] == "/ponto/original", "variáveis de ambiente intactas após recusa")
    try:
        c.isolar_temporarios(os.path.join(base2, "nao", "existe", "mesmo"))
        ok(True, "base inexistente não derruba o programa")
    except Exception as ex:
        ok(False, f"base inexistente levantou {ex!r}")
    if os.name == "posix" and os.geteuid() != 0:
        ro = tempfile.mkdtemp(prefix="ro_"); os.chmod(ro, 0o500)
        ok(c.isolar_temporarios(ro) is None, "pasta base sem escrita: None")
        os.chmod(ro, 0o700)

    print("== 3) política exigir NTFS")
    os.environ.pop("COFRE_EXIGIR_NTFS", None)
    base3 = tempfile.mkdtemp(prefix="base3_")
    ok(c.politica_exigir_ntfs(base3) is False, "padrão: desligada")
    os.environ["COFRE_EXIGIR_NTFS"] = "1"
    ok(c.politica_exigir_ntfs(base3) is True, "COFRE_EXIGIR_NTFS=1 liga")
    os.environ["COFRE_EXIGIR_NTFS"] = "0"
    ok(c.politica_exigir_ntfs(base3) is False, "COFRE_EXIGIR_NTFS=0 não liga")
    os.environ.pop("COFRE_EXIGIR_NTFS")
    open(os.path.join(base3, c.NOME_MARCADOR_NTFS), "w").close()
    ok(c.politica_exigir_ntfs(base3) is True, "arquivo exigir_ntfs.txt liga")
    ok(c.aviso_sistema_de_arquivos("exFAT") != "" and c.aviso_sistema_de_arquivos("NTFS") == ""
       and c.aviso_sistema_de_arquivos("") == "", "aviso só para FAT/FAT32/exFAT (a política decide se recusa)")
finally:
    c.limpar_temporarios()
    for k, v in env0.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    tempfile.tempdir = tmp0
print("\nRESULTADO:", "TUDO OK" if not FAL else f"{len(FAL)} FALHA(S): {FAL}")
sys.exit(1 if FAL else 0)
